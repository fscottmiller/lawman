"""A work contract can come from the issue that ordered the work.

Every test here runs against a local stand-in for GitHub (`fake_github.py`),
so what is proven is Lawman's half of the contract: the one request it makes,
the single block it reads, the identity it reports, and the long list of
things it refuses. Nothing depends on a live, mutable issue.

The API origin is patched rather than passed, because there is no flag or
environment variable that redirects Lawman at a different GitHub — a caller
who could choose the server could choose the contract.
"""

import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from http.client import BadStatusLine
from pathlib import Path
from unittest import mock

import fake_github

from lawman import LawmanError, github, issue_contract
from lawman.__main__ import main
from lawman.github import BLOCK_TAG, TOKEN_VARIABLE, IssueReference

ROOT = Path(__file__).resolve().parent.parent
WORK_EXAMPLE = ROOT / "examples" / "work-contract"
ISSUE_URL = f"https://github.com/{fake_github.OWNER}/{fake_github.REPOSITORY}/issues/{fake_github.NUMBER}"
TOKEN = "ghs_a-token-that-must-never-be-printed"

CRITERIA = [
    {"id": "AC1", "description": "The issue supplies the acceptance criteria"},
    {"id": "AC2", "description": "Evidence names one traceable source"},
    {"id": "AC3", "description": "Silence is not proof"},
]

# The hash of CRITERIA, as a reader can recompute it: criteria in issue order,
# each reduced to id and description, sorted keys, compact separators, UTF-8.
CANONICAL_SHA256 = "sha256:c5d300a28bde0b9bd788f5b5ea90c4f02681416e76f045e7c57fa13954105433"

PROSE = f"""## Outcome

Lawman can fetch a work contract directly from a GitHub Issue.

This issue is mostly prose, and none of it is a contract.

- [x] AC9 looks finished
- [ ] AC4 is still open

```json
{{
  "criteria": [
    {{ "id": "AC99", "description": "A decoy block nobody agreed to" }}
  ]
}}
```

An inline mention of `{BLOCK_TAG}` is not a fence either.
"""

TRAILING = """
## Intentionally deferred

- Reading issue comments
- Inferring criteria from prose
"""


def block(contract, tag=BLOCK_TAG):
    return f"```{tag}\n{contract}\n```"


def contract_json(criteria=None, indent=2):
    return json.dumps({"criteria": CRITERIA if criteria is None else criteria}, indent=indent)


def body(contract=None, prose=PROSE, trailing=TRAILING, tag=BLOCK_TAG):
    """An issue body: prose, decoys, one tagged block, and more prose."""
    return f"{prose}\n{block(contract_json() if contract is None else contract, tag)}\n{trailing}"


def digest(criteria):
    normalized = {"criteria": [{"description": item["description"], "id": item["id"]} for item in criteria]}
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


@contextlib.contextmanager
def environment(token=TOKEN):
    """A deterministic environment: a known token, or none, and no proxy."""
    with mock.patch.dict(os.environ, {"no_proxy": "*", "NO_PROXY": "*"}):
        os.environ.pop(TOKEN_VARIABLE, None)
        if token is not None:
            os.environ[TOKEN_VARIABLE] = token
        yield


class Run:
    """One CLI invocation: what it printed, and what it exited with."""

    def __init__(self, exit_code, stdout, stderr):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr

    @property
    def document(self):
        return json.loads(self.stdout)


def run(argv, origin=None, token=TOKEN):
    """Run `python -m lawman` in process, against the stand-in GitHub."""
    stdout, stderr = io.StringIO(), io.StringIO()
    origin_patch = contextlib.nullcontext() if origin is None else mock.patch("lawman.github.API_ORIGIN", origin)
    with environment(token), origin_patch:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = main([str(argument) for argument in argv])
    return Run(exit_code, stdout.getvalue(), stderr.getvalue())


def work(origin, evidence, url=ISSUE_URL, token=TOKEN):
    return run(["work", "--issue", url, "--evidence", evidence], origin=origin, token=token)


def cli(*argv):
    """Run the real command in a real process, for what argument parsing does."""
    return subprocess.run(
        [sys.executable, "-m", "lawman", *[str(argument) for argument in argv]],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
    )


def evidence_file(directory, entries, name="evidence.json"):
    path = Path(directory) / name
    path.write_text(json.dumps({"evidence": entries}), encoding="utf-8")
    return path


def proving(*criterion_ids, failed=(), missing=()):
    return [
        {"criterion_id": item, "source": f"test_{item.lower()}", "passed": item not in failed}
        for item in criterion_ids
        if item not in missing
    ]


class GitHubIssueContractTest(unittest.TestCase):
    """Shared setup: a temporary directory, and evidence that proves everything."""

    def setUp(self):
        self.directory = self.enterContext(tempfile.TemporaryDirectory())
        self.evidence = evidence_file(self.directory, proving("AC1", "AC2", "AC3"))


class ReadsTheContractFromTheIssue(GitHubIssueContractTest):
    def test_issue_contract_uses_authenticated_read_only_get_without_leaking_token(self):
        """AC2. One authenticated GET of one issue, and the token stays in the environment."""
        with fake_github.serving(fake_github.issue(body())) as server:
            authenticated = work(server.origin, self.evidence)
            self.assertEqual(len(server.received), 1, server.received)
            request = server.received[0]

            anonymous = work(server.origin, self.evidence, token=None)
            headers = server.received[1]["headers"]

        self.assertEqual(authenticated.exit_code, 0, authenticated.stderr)
        self.assertEqual(request["method"], "GET")
        self.assertEqual(request["path"], f"/repos/{fake_github.OWNER}/{fake_github.REPOSITORY}/issues/8")
        self.assertEqual(request["headers"]["authorization"], f"Bearer {TOKEN}")
        self.assertEqual(request["headers"]["accept"], "application/vnd.github+json")
        self.assertIn("x-github-api-version", request["headers"])

        # No token, no Authorization header. A public issue still reads.
        self.assertEqual(anonymous.exit_code, 0, anonymous.stderr)
        self.assertNotIn("authorization", headers)

        # The token never reaches the output, on success or on refusal.
        with fake_github.serving({"message": "Not Found"}, status=404) as server:
            refused = work(server.origin, self.evidence)

        self.assertEqual(refused.exit_code, 2)
        for text in (authenticated.stdout, authenticated.stderr, refused.stdout, refused.stderr):
            self.assertNotIn(TOKEN, text)
        self.assertNotIn(TOKEN, json.dumps(authenticated.document))

        # And no argument accepts one, so it cannot reach a process list either.
        help_text = cli("work", "--help").stdout
        for flag in ("--token", "--github-token", "--auth", "--password"):
            with self.subTest(flag=flag):
                self.assertNotIn(flag, help_text)
                rejected = cli("work", "--issue", ISSUE_URL, "--evidence", self.evidence, flag, TOKEN)
                self.assertEqual(rejected.returncode, 2)
                self.assertIn("unrecognized arguments", rejected.stderr)
        self.assertIn(TOKEN_VARIABLE, help_text)

    def test_only_the_single_tagged_contract_block_is_parsed(self):
        """AC3. The tagged block is the contract. Everything else in the issue is not."""
        with fake_github.serving(fake_github.issue(body())) as server:
            result = work(server.origin, self.evidence)
            requested = [request["path"] for request in server.received]

        self.assertEqual(result.exit_code, 0, result.stderr)
        self.assertEqual([item["id"] for item in result.document["criteria"]], ["AC1", "AC2", "AC3"])
        self.assertEqual(
            [item["description"] for item in result.document["criteria"]],
            [item["description"] for item in CRITERIA],
        )

        # The decoy ```json block, the checklist, the headings, and the inline
        # mention of the tag supplied nothing.
        self.assertNotIn("AC99", result.stdout)
        self.assertNotIn("AC9 looks finished", result.stdout)

        # Labels, comment counts, titles, and state are read from nowhere, and
        # the comments endpoint is never requested.
        self.assertEqual(requested, [f"/repos/{fake_github.OWNER}/{fake_github.REPOSITORY}/issues/8"])

        # A CRLF body, an indented fence, and a block that is the whole body all read the same.
        bodies = {
            "crlf": body().replace("\n", "\r\n"),
            "indented fence": f"{PROSE}\n  {block(contract_json())}\n{TRAILING}",
            "nothing but the block": block(contract_json()),
            "compact json": body(contract=contract_json(indent=None)),
        }
        for situation, text in bodies.items():
            with self.subTest(situation=situation), fake_github.serving(fake_github.issue(text)) as server:
                accepted = work(server.origin, self.evidence)

            self.assertEqual(accepted.exit_code, 0, accepted.stderr)
            self.assertEqual([item["id"] for item in accepted.document["criteria"]], ["AC1", "AC2", "AC3"])

    def test_issue_contract_uses_existing_work_evaluation_semantics(self):
        """AC6. The same domain model decides it, so nothing about judging work moved."""
        entries = proving("AC1", "AC2", "AC3", failed=("AC2",), missing=("AC3",))
        evidence = evidence_file(self.directory, list(reversed(entries)), name="mixed.json")

        with fake_github.serving(fake_github.issue(body())) as server:
            result = work(server.origin, evidence)

        self.assertEqual(result.exit_code, 1)
        document = result.document
        self.assertFalse(document["satisfied"])

        # Contract order, not evidence order. Proven, failed, and unproven, with
        # the same keys and the same explanations a local contract produces.
        self.assertEqual([item["id"] for item in document["criteria"]], ["AC1", "AC2", "AC3"])
        self.assertEqual([item["status"] for item in document["criteria"]], ["proven", "failed", "unproven"])
        self.assertEqual(set(document["criteria"][0]), {"id", "description", "status", "source", "explanation"})
        self.assertEqual(document["criteria"][1]["explanation"], "Failed: test_ac2 reported failure.")
        self.assertEqual(document["criteria"][2]["explanation"], "Unproven: no evidence was provided.")
        self.assertIsNone(document["criteria"][2]["source"])

        # An issue-supplied contract is the same contract: byte for byte, the
        # criteria a local file produces.
        local = Path(self.directory) / "contract.json"
        local.write_text(contract_json(), encoding="utf-8")
        from_file = run(["work", "--contract", local, "--evidence", evidence])

        self.assertEqual(from_file.document["criteria"], document["criteria"])
        self.assertEqual(from_file.exit_code, result.exit_code)

        # Evidence for a criterion the issue does not name is still refused.
        unknown = evidence_file(self.directory, proving("AC1", "AC2", "AC3", "AC7"), name="unknown.json")
        with fake_github.serving(fake_github.issue(body())) as server:
            refused = work(server.origin, unknown)

        self.assertEqual(refused.exit_code, 2)
        self.assertEqual(refused.stdout, "")
        self.assertIn("unknown criteria: AC7", refused.stderr)


class SaysWhichContractItJudged(GitHubIssueContractTest):
    def test_issue_contract_source_has_content_bound_identity(self):
        """AC7. The issue says which one; the hash says which version."""
        with fake_github.serving(fake_github.issue(body())) as server:
            result = work(server.origin, self.evidence)

        self.assertEqual(
            result.document["contract_source"],
            {
                "type": "github_issue",
                "url": ISSUE_URL,
                "node_id": fake_github.NODE_ID,
                "updated_at": fake_github.UPDATED_AT,
                "contract_sha256": CANONICAL_SHA256,
            },
        )
        self.assertEqual(CANONICAL_SHA256, digest(CRITERIA))

        # Presentation is not identity. Rewording the prose around the block,
        # reindenting the JSON, reordering its keys, or touching the issue all
        # leave the contract, and its hash, alone.
        reordered = [{"description": item["description"], "id": item["id"]} for item in CRITERIA]
        unchanged = {
            "different prose": fake_github.issue(body(prose="# Nothing like the original prose\n")),
            "different indentation": fake_github.issue(body(contract=contract_json(indent=8))),
            "compact json": fake_github.issue(body(contract=contract_json(indent=None))),
            "reordered keys": fake_github.issue(body(contract=json.dumps({"criteria": reordered}))),
            "issue edited elsewhere": fake_github.issue(body(), updated_at="2026-12-25T09:00:00Z"),
        }
        for situation, payload in unchanged.items():
            with self.subTest(situation=situation), fake_github.serving(payload) as server:
                same = work(server.origin, self.evidence)

            self.assertEqual(same.exit_code, 0, same.stderr)
            self.assertEqual(same.document["contract_source"]["contract_sha256"], CANONICAL_SHA256)

        # Content is identity. A reworded criterion, a renumbered one, and a
        # reordered contract are each a different contract.
        rewritten = [dict(item) for item in CRITERIA]
        rewritten[1]["description"] = "Evidence names one traceable source, eventually"
        changed = {
            "a reworded criterion": rewritten,
            "a renamed criterion": [{**item, "id": item["id"].replace("AC3", "AC4")} for item in CRITERIA],
            "a reordered contract": list(reversed(CRITERIA)),
            "an added criterion": [*CRITERIA, {"id": "AC4", "description": "One more obligation"}],
        }
        for situation, criteria in changed.items():
            with self.subTest(situation=situation):
                payload = fake_github.issue(body(contract=contract_json(criteria)))
                evidence = evidence_file(
                    self.directory,
                    proving(*[item["id"] for item in criteria]),
                    name=f"{situation.replace(' ', '-')}.json",
                )
                with fake_github.serving(payload) as server:
                    different = work(server.origin, evidence)

                self.assertEqual(different.exit_code, 0, different.stderr)
                fingerprint = different.document["contract_source"]["contract_sha256"]
                self.assertEqual(fingerprint, digest(criteria))
                self.assertNotEqual(fingerprint, CANONICAL_SHA256)

        # GitHub does not distinguish owners and repositories by case, so
        # neither does Lawman. It is the same issue, and the same contract.
        shouted = f"https://github.com/{fake_github.OWNER.upper()}/{fake_github.REPOSITORY}/issues/8"
        with fake_github.serving(fake_github.issue(body())) as server:
            cased = work(server.origin, self.evidence, url=shouted)

        self.assertEqual(cased.exit_code, 0, cased.stderr)
        self.assertEqual(cased.document["contract_source"]["node_id"], fake_github.NODE_ID)
        self.assertEqual(cased.document["contract_source"]["contract_sha256"], CANONICAL_SHA256)

        # The node ID identifies the issue itself, whatever its URL says today.
        with fake_github.serving(fake_github.issue(body(), node_id="I_kwDOrenamed")) as server:
            renamed = work(server.origin, self.evidence)

        self.assertEqual(renamed.document["contract_source"]["node_id"], "I_kwDOrenamed")
        self.assertEqual(renamed.document["contract_source"]["url"], ISSUE_URL)

    def test_issue_contract_returns_satisfied_and_unsatisfied_results(self):
        """AC8. Exit 0 satisfied, exit 1 not, and both account for every criterion."""
        unsatisfied = evidence_file(
            self.directory, proving("AC1", "AC2", "AC3", failed=("AC3",)), name="unsatisfied.json"
        )

        with fake_github.serving(fake_github.issue(body())) as server:
            satisfied = work(server.origin, self.evidence)
        with fake_github.serving(fake_github.issue(body())) as server:
            denied = work(server.origin, unsatisfied)

        self.assertEqual(satisfied.exit_code, 0, satisfied.stderr)
        self.assertEqual(satisfied.stderr, "")
        self.assertTrue(satisfied.document["satisfied"])

        self.assertEqual(denied.exit_code, 1)
        self.assertFalse(denied.document["satisfied"])

        for name, result in (("satisfied", satisfied), ("unsatisfied", denied)):
            with self.subTest(result=name):
                document = result.document
                self.assertEqual(list(document), ["contract_source", "satisfied", "criteria"])
                self.assertEqual([item["id"] for item in document["criteria"]], ["AC1", "AC2", "AC3"])
                self.assertEqual(document["contract_source"]["contract_sha256"], CANONICAL_SHA256)
                self.assertEqual(document["contract_source"]["url"], ISSUE_URL)

    def test_issue_contract_output_is_byte_identical_across_runs(self):
        """AC9. Same issue, same evidence: the same bytes, source identity included."""
        with fake_github.serving(fake_github.issue(body())) as server:
            runs = [work(server.origin, self.evidence) for _ in range(3)]

        self.assertEqual({result.stdout for result in runs}, {runs[0].stdout})
        self.assertEqual({result.exit_code for result in runs}, {0})
        self.assertIn(CANONICAL_SHA256, runs[0].stdout)


class RefusesAnythingItCannotReadAsAContract(GitHubIssueContractTest):
    """Exit 2, nothing on stdout, one line on stderr. Never a work result."""

    def assertRefused(self, result, expected):
        self.assertEqual(result.exit_code, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(len(result.stderr.strip().splitlines()), 1, result.stderr)
        self.assertTrue(result.stderr.startswith("lawman: "), result.stderr)
        self.assertIn(expected, result.stderr)

    def test_missing_duplicate_or_malformed_contract_blocks_are_refused(self):
        """AC4. No block, two blocks, unreadable JSON, or a contract the domain refuses."""
        bodies = {
            "no tagged block": (body(tag="json"), f"no fenced {BLOCK_TAG} block"),
            "no body at all": ("", f"no fenced {BLOCK_TAG} block"),
            "only an inline mention": (f"`{BLOCK_TAG}` is mentioned but never fenced.", "no fenced"),
            "a near-miss tag": (body(tag=f"{BLOCK_TAG}-v2"), "no fenced"),
            "two tagged blocks": (
                f"{body()}\n{block(contract_json([{'id': 'AC9', 'description': 'A second answer'}]))}\n",
                f"has 2 fenced {BLOCK_TAG} blocks",
            ),
            "the same block twice": (f"{body()}\n{block(contract_json())}\n", "exactly one is the contract"),
            "invalid json": (body(contract='{"criteria": [}'), "is not valid JSON"),
            "empty block": (body(contract=""), "is not valid JSON"),
            "duplicate top-level keys": (
                body(contract='{"criteria": [{"id": "AC1", "description": "First"}], "criteria": []}'),
                "repeats the key(s): criteria",
            ),
            "duplicate criterion keys": (
                body(contract='{"criteria": [{"id": "AC1", "description": "First", "id": "AC2"}]}'),
                "repeats the key(s): id",
            ),
            "not an object": (body(contract='["AC1"]'), "work contract must be an object"),
            "no criteria": (body(contract='{"criteria": []}'), "at least one criterion"),
            "criteria is not a list": (body(contract='{"criteria": {"AC1": "First"}}'), "must be a list"),
            "duplicate criterion ids": (
                body(contract=contract_json([CRITERIA[0], {"id": "AC1", "description": "Again"}])),
                "criterion IDs must be unique",
            ),
            "a blank description": (
                body(contract=contract_json([{"id": "AC1", "description": "  "}])),
                "must be a non-empty string",
            ),
            "a criterion that is not an object": (
                body(contract='{"criteria": ["AC1"]}'),
                "work contract criterion must be an object",
            ),
        }
        for situation, (text, expected) in bodies.items():
            with self.subTest(situation=situation), fake_github.serving(fake_github.issue(text)) as server:
                result = work(server.origin, self.evidence)

            self.assertRefused(result, expected)

    def test_invalid_urls_and_github_failures_are_refused(self):
        """AC5. A URL Lawman will not accept, or a GitHub it cannot believe."""
        urls = {
            "not a URL at all": "issue 8",
            "shorthand": f"{fake_github.OWNER}/{fake_github.REPOSITORY}#8",
            "plain http": ISSUE_URL.replace("https://", "http://"),
            "another host": ISSUE_URL.replace("github.com", "gitlab.com"),
            "a lookalike host": ISSUE_URL.replace("github.com", "github.com.example.net"),
            "a pull request": ISSUE_URL.replace("/issues/", "/pull/"),
            "the API URL": f"https://api.github.com/repos/{fake_github.OWNER}/{fake_github.REPOSITORY}/issues/8",
            "a comment fragment": f"{ISSUE_URL}#issuecomment-1",
            "a query string": f"{ISSUE_URL}?raw=1",
            "a trailing slash": f"{ISSUE_URL}/",
            "no number": ISSUE_URL.rsplit("/", 1)[0],
            "not a number": ISSUE_URL.replace("/8", "/eight"),
            "issue zero": ISSUE_URL.replace("/8", "/0"),
            "a path climb": ISSUE_URL.replace("/issues/8", "/issues/../../other/repo/issues/8"),
            "no repository": f"https://github.com/{fake_github.OWNER}/issues/8",
            "an empty URL": "   ",
        }
        for situation, url in urls.items():
            with self.subTest(situation=situation), fake_github.serving(fake_github.issue(body())) as server:
                result = work(server.origin, self.evidence, url=url)

                # Nothing is requested: the URL is refused before any read.
                self.assertEqual(server.received, [])
            self.assertRefused(result, "canonical GitHub issue URL")

        failures = {
            "not found": ({"body": {"message": "Not Found"}, "status": 404}, "HTTP 404"),
            "forbidden": ({"body": {"message": "Bad credentials"}, "status": 403}, "HTTP 403"),
            "rate limited": ({"body": {"message": "rate limited"}, "status": 429}, "HTTP 429"),
            "server error": ({"body": {"message": "oops"}, "status": 500}, "HTTP 500"),
            "a redirect elsewhere": (
                {"body": "", "status": 301, "headers": (("Location", "https://example.invalid/issues/8"),)},
                "HTTP 301",
            ),
            "not JSON": ({"body": "<html>not json</html>"}, "is not readable JSON"),
            "not text": ({"body": b"\xff\xfe{}"}, "is not readable JSON"),
            "not an object": ({"body": [{"body": "..."}]}, "must be an object"),
            "a pull request in disguise": (
                {"body": fake_github.issue(body(), pull_request={"url": "..."})},
                "is a pull request, not an issue",
            ),
            "another issue": ({"body": fake_github.issue(body(), number=9)}, "a different issue"),
            "another repository": (
                {"body": fake_github.issue(body(), repository="other")},
                "a different issue",
            ),
            "no node ID": ({"body": fake_github.issue(body(), node_id="")}, "GitHub node_id"),
            "no updated_at": ({"body": fake_github.issue(body(), updated_at=None)}, "GitHub updated_at"),
            "no body": ({"body": fake_github.issue(None)}, "no issue body"),
            "a body that is not text": ({"body": fake_github.issue(["contract"])}, "no issue body"),
        }
        for situation, (response, expected) in failures.items():
            with self.subTest(situation=situation), fake_github.serving(**response) as server:
                result = work(server.origin, self.evidence)

            self.assertRefused(result, expected)

        # Nothing listening at all.
        self.assertRefused(work(fake_github.unreachable(), self.evidence), "cannot read")

        # An answer that is not HTTP is a refusal, not a traceback.
        with mock.patch.object(github._OPENER, "open", side_effect=BadStatusLine("not http at all")):
            garbled = work("http://127.0.0.1:1", self.evidence)

        self.assertRefused(garbled, "cannot read")

        # More than Lawman will read.
        with fake_github.serving(fake_github.issue(body())) as server:
            with mock.patch("lawman.github.MAXIMUM_RESPONSE_BYTES", 64):
                oversized = work(server.origin, self.evidence)

        self.assertRefused(oversized, "more than 64 bytes")

        # A GitHub that never answers cannot hold the gate open. Only the bound
        # is shortened here; the request really is made, and really times out.
        with fake_github.serving(fake_github.issue(body()), delay=2.0) as server:
            with mock.patch("lawman.github.TIMEOUT_SECONDS", 0.2):
                wedged = work(server.origin, self.evidence)

        self.assertRefused(wedged, "cannot read")

        # Interrupting Lawman mid-read is a refusal, not a traceback.
        with mock.patch("lawman.github._get", side_effect=KeyboardInterrupt):
            interrupted = work("http://127.0.0.1:1", self.evidence)

        self.assertRefused(interrupted, "interrupted before a work contract result")


class TheContractSourceIsTheOnlyThingItProves(GitHubIssueContractTest):
    def test_issue_contract_evaluation_does_not_invoke_transition_policy(self):
        """AC11. A satisfied issue contract is not a permit, and reaches no policy."""
        with fake_github.serving(fake_github.issue(body())) as server:
            with mock.patch("lawman.__main__.select_policy", side_effect=AssertionError("policy was selected")):
                with mock.patch("lawman.__main__.evaluate_policy", side_effect=AssertionError("OPA was asked")):
                    result = work(server.origin, self.evidence)

        self.assertEqual(result.exit_code, 0, result.stderr)
        self.assertTrue(result.document["satisfied"])

        # The result says what was proven and where the contract came from. It
        # says nothing about what is allowed.
        self.assertEqual(list(result.document), ["contract_source", "satisfied", "criteria"])
        for absent in ("allowed", "intent", "reasons", "transition", "governing", "work_satisfied"):
            with self.subTest(absent=absent):
                self.assertNotIn(absent, result.document)
                self.assertNotIn(absent, result.document["contract_source"])

        # An issue from anywhere reads the same way, because Lawman is not
        # claiming this issue governs anything. It only says which one it read.
        elsewhere = "https://github.com/another-owner/another-repo/issues/3"
        payload = fake_github.issue(body(), owner="another-owner", repository="another-repo", number=3)
        with fake_github.serving(payload) as server:
            other = work(server.origin, self.evidence, url=elsewhere)

        self.assertEqual(other.exit_code, 0, other.stderr)
        self.assertEqual(other.document["contract_source"]["url"], elsewhere)

        # And the transition command still takes no contract source at all.
        rejected = cli("--intent", "intent.json", "--evidence", "evidence.json", "--issue", ISSUE_URL)
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("unrecognized arguments", rejected.stderr)
        self.assertNotIn("--issue", cli("--help").stdout)

    def test_work_requires_exactly_one_contract_source(self):
        """AC1. One local file or one issue URL, never both, never neither."""
        local = WORK_EXAMPLE / "contract.json"
        evidence = WORK_EXAMPLE / "evidence.json"
        invocations = {
            "no source": (("work", "--evidence", evidence), "one of the arguments --contract --issue is required"),
            "both sources": (
                ("work", "--contract", local, "--issue", ISSUE_URL, "--evidence", evidence),
                "not allowed with argument",
            ),
            "no evidence, local": (("work", "--contract", local), "--evidence"),
            "no evidence, issue": (("work", "--issue", ISSUE_URL), "--evidence"),
            "nothing at all": (("work",), "required"),
        }
        for situation, (argv, expected) in invocations.items():
            with self.subTest(situation=situation):
                result = cli(*argv)

                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertEqual(result.stdout, "")
                self.assertIn(expected, result.stderr)

        # Both are advertised, and either one on its own runs.
        help_text = cli("work", "--help").stdout
        self.assertIn("--contract PATH", help_text)
        self.assertIn("--issue URL", help_text)
        self.assertEqual(cli("work", "--contract", local, "--evidence", evidence).returncode, 0)

        with fake_github.serving(fake_github.issue(body())) as server:
            self.assertEqual(work(server.origin, self.evidence).exit_code, 0)


class HoldsItsInvariantsWhenConstructedDirectly(unittest.TestCase):
    def test_direct_construction_cannot_bypass_domain_invariants(self):
        for url in ("", "   ", None, 8, "https://github.com/o/r/pull/1"):
            with self.subTest(url=url), self.assertRaises(LawmanError):
                IssueReference.from_url(url)

        reference = IssueReference.from_url(ISSUE_URL)
        self.assertEqual(reference.url, ISSUE_URL)
        self.assertEqual(reference.number, 8)
        self.assertTrue(reference.api_url.startswith("https://api.github.com/repos/"))

        with self.assertRaises(LawmanError):
            issue_contract("not a url")


if __name__ == "__main__":
    unittest.main()

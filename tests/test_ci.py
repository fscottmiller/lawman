"""Work evidence comes from the execution, not from whoever wants it to pass.

Every test here runs `python -m lawman work --issue ... --junit ...` against a
local stand-in for GitHub (`fake_github.py`) and a JUnit report written into a
temporary directory. Nothing depends on a live issue, and nothing depends on
being run inside a real GitHub Actions job: the execution context is patched
into the environment, because that is the only place Lawman reads it from.

What is proven here is Lawman's half of the CI contract — the execution it
insists on, the identities it will match, the evidence it derives, and the long
list of things it refuses. The verdict itself is still the work domain's, and
`test_ci_collection_delegates_to_existing_work_evaluator` is what pins that.
"""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fake_github

from lawman import ci
from lawman.__main__ import main
from lawman.ci import (
    ACTIONS_VARIABLE,
    ATTEMPT_VARIABLE,
    REPOSITORY_VARIABLE,
    REVISION_VARIABLE,
    RUN_VARIABLE,
    ExecutionContext,
    actions_evidence,
)
from lawman.github import BLOCK_TAG, TOKEN_VARIABLE
from lawman.work import CriterionEvidence, WorkContract, WorkEvidence, evaluate_work_contract

ROOT = Path(__file__).resolve().parent.parent
WORK_EXAMPLE = ROOT / "examples" / "work-contract"
ISSUE_URL = f"https://github.com/{fake_github.OWNER}/{fake_github.REPOSITORY}/issues/{fake_github.NUMBER}"

REVISION = "9f8e7d6c5b4a39281706f5e4d3c2b1a09f8e7d6c"
OTHER_REVISION = "1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d"
REPOSITORY = f"{fake_github.OWNER}/{fake_github.REPOSITORY}"
RUN_ID = "17285941003"
RUN_ATTEMPT = "1"

ACTIONS = {
    ACTIONS_VARIABLE: "true",
    REPOSITORY_VARIABLE: REPOSITORY,
    REVISION_VARIABLE: REVISION,
    RUN_VARIABLE: RUN_ID,
    ATTEMPT_VARIABLE: RUN_ATTEMPT,
}

EXECUTION = {
    "type": "github_actions",
    "repository": REPOSITORY,
    "revision": REVISION,
    "run_id": RUN_ID,
    "run_attempt": RUN_ATTEMPT,
}

# One criterion bound to a bare test name, one to another, and one to a fully
# qualified identity — the two forms a report states, and the only two.
BOUND = (
    ("AC1", "Evidence is derived from the execution", "test_evidence_is_derived"),
    ("AC2", "The revision is the one the tests ran against", "test_revision_is_bound"),
    ("AC3", "A qualified identity is matched exactly", "tests.test_suite.Bound.test_qualified"),
)

CLASS = "tests.test_suite.Bound"

PASSING = (
    (CLASS, "test_evidence_is_derived", "passed"),
    (CLASS, "test_revision_is_bound", "passed"),
    (CLASS, "test_qualified", "passed"),
)

OUTCOMES = {
    "passed": "",
    "failed": '<failure message="assertion failed">traceback</failure>',
    "errored": '<error message="exploded">traceback</error>',
    "skipped": '<skipped message="no reason given"/>',
}


def criteria(bound=BOUND):
    return [{"id": item, "description": description, "evidence_source": source} for item, description, source in bound]


def issue_body(bound=BOUND):
    """An issue that is mostly prose, and states its contract exactly once."""
    contract = json.dumps({"criteria": criteria(bound)}, indent=2)
    return f"## Outcome\n\nSome prose nobody reads.\n\n```{BLOCK_TAG}\n{contract}\n```\n\n## Deferred\n\n- Everything\n"


def report_xml(cases=PASSING, root="testsuites"):
    """A JUnit document, shaped the way test runners emit one."""
    written = "".join(
        f'<testcase{f" classname={classname!r}" if classname else ""} name={name!r}>{OUTCOMES[outcome]}</testcase>'
        for classname, name, outcome in cases
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<{root} name="suite" tests="{len(cases)}">{written}</{root}>'
    )


class Run:
    """One CLI invocation: what it printed, and what it exited with."""

    def __init__(self, exit_code, stdout, stderr):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr

    @property
    def document(self):
        return json.loads(self.stdout)

    @property
    def statuses(self):
        return [item["status"] for item in self.document["criteria"]]


@contextlib.contextmanager
def environment(actions=None):
    """A deterministic environment: one execution context, and nothing inherited.

    The suite may itself be running inside GitHub Actions, so every variable
    this path reads is removed before the wanted ones are set.
    """
    with mock.patch.dict(os.environ, {"no_proxy": "*", "NO_PROXY": "*"}):
        for name in (*ACTIONS, TOKEN_VARIABLE):
            os.environ.pop(name, None)
        os.environ.update(ACTIONS if actions is None else actions)
        yield


def run(argv, origin=None, actions=None):
    """Run `python -m lawman` in process, against the stand-in GitHub."""
    stdout, stderr = io.StringIO(), io.StringIO()
    origin_patch = contextlib.nullcontext() if origin is None else mock.patch("lawman.github.API_ORIGIN", origin)
    with environment(actions), origin_patch:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = main([str(argument) for argument in argv])
    return Run(exit_code, stdout.getvalue(), stderr.getvalue())


def verify(origin, junit, url=ISSUE_URL, actions=None):
    return run(["work", "--issue", url, "--junit", junit], origin=origin, actions=actions)


def cli(*argv):
    """Run the real command in a real process, for what argument parsing does."""
    return subprocess.run(
        [sys.executable, "-m", "lawman", *[str(argument) for argument in argv]],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
    )


class CiEvidenceTest(unittest.TestCase):
    """Shared setup: a temporary directory, and a report the criteria can be proven from."""

    def setUp(self):
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def report(self, cases=PASSING, root="testsuites", name="junit.xml"):
        return self.write(report_xml(cases, root), name=name)

    def write(self, text, name="junit.xml"):
        path = self.directory / name
        path.write_text(text, encoding="utf-8")
        return path

    def evidence_file(self, entries, name="evidence.json"):
        path = self.directory / name
        path.write_text(json.dumps({"evidence": entries}), encoding="utf-8")
        return path

    @contextlib.contextmanager
    def issue(self, bound=BOUND):
        with fake_github.serving(fake_github.issue(issue_body(bound))) as server:
            yield server

    def assertRefused(self, result, expected):
        """Exit 2, nothing on stdout, one line on stderr. Never a work result."""
        self.assertEqual(result.exit_code, 2, result.stdout)
        self.assertEqual(result.stdout, "")
        self.assertEqual(len(result.stderr.strip().splitlines()), 1, result.stderr)
        self.assertTrue(result.stderr.startswith("lawman: "), result.stderr)
        self.assertIn(expected, result.stderr)


class DerivesEvidenceFromTheExecution(CiEvidenceTest):
    def test_github_work_can_derive_evidence_from_junit(self):
        """AC1. The issue states the contract; the run's tests supply the proof."""
        junit = self.report()

        with self.issue() as server:
            # Nothing caller-authored is read: `_read_json` is the only door to
            # a local document, and it is nailed shut for this invocation.
            with mock.patch("lawman.__main__._read_json", side_effect=AssertionError("a local document was read")):
                result = verify(server.origin, junit)

        self.assertEqual(result.exit_code, 0, result.stderr)
        document = result.document
        self.assertTrue(document["satisfied"])
        self.assertEqual(result.statuses, ["proven", "proven", "proven"])
        self.assertEqual([item["source"] for item in document["criteria"]], [source for _, _, source in BOUND])
        self.assertEqual(list(document), ["contract_source", "execution", "satisfied", "criteria"])
        self.assertEqual(document["contract_source"]["url"], ISSUE_URL)

        # `--junit` replaces `--evidence`; asking for both is refused by the parser.
        evidence = self.evidence_file([{"criterion_id": "AC1", "source": "test_evidence_is_derived", "passed": True}])
        both = cli("work", "--issue", ISSUE_URL, "--evidence", evidence, "--junit", junit)

        self.assertEqual(both.returncode, 2, both.stdout)
        self.assertEqual(both.stdout, "")
        self.assertIn("not allowed with argument", both.stderr)

        # And the slice is exactly as narrow as it says: derived evidence
        # answers a contract the claimant did not write.
        local = run(["work", "--contract", WORK_EXAMPLE / "contract.json", "--junit", junit])

        self.assertRefused(local, "--junit derives evidence for the issue that ordered the work")

        help_text = cli("work", "--help").stdout
        self.assertIn("--junit PATH", help_text)
        self.assertIn("--evidence PATH", help_text)

    def test_ci_evidence_is_bound_to_actions_revision(self):
        """AC2. The execution is required, read from Actions, and reported."""
        junit = self.report()

        with self.issue() as server:
            proven = verify(server.origin, junit)
            elsewhere = verify(server.origin, junit, actions={**ACTIONS, REVISION_VARIABLE: OTHER_REVISION})

        self.assertEqual(proven.exit_code, 0, proven.stderr)
        self.assertEqual(proven.document["execution"], EXECUTION)

        # The revision is the execution's, not a constant Lawman carries.
        self.assertEqual(elsewhere.document["execution"]["revision"], OTHER_REVISION)
        self.assertEqual(elsewhere.document["criteria"], proven.document["criteria"])

        without = {name: value for name, value in ACTIONS.items()}
        refusals = {
            "no Actions execution at all": ({}, f"{ACTIONS_VARIABLE} is not 'true'"),
            "an execution claimed as something else": (
                {**without, ACTIONS_VARIABLE: "false"},
                f"{ACTIONS_VARIABLE} is not 'true'",
            ),
            "a truthy imitation": ({**without, ACTIONS_VARIABLE: "TRUE"}, f"{ACTIONS_VARIABLE} is not 'true'"),
            "no revision": (
                {name: value for name, value in without.items() if name != REVISION_VARIABLE},
                f"{REVISION_VARIABLE} must be a 40-character lowercase commit SHA",
            ),
            "an abbreviated revision": ({**without, REVISION_VARIABLE: REVISION[:7]}, REVISION_VARIABLE),
            "an uppercased revision": ({**without, REVISION_VARIABLE: REVISION.upper()}, REVISION_VARIABLE),
            "a revision with a newline": ({**without, REVISION_VARIABLE: f"{REVISION}\n"}, REVISION_VARIABLE),
            "a branch instead of a revision": ({**without, REVISION_VARIABLE: "refs/heads/main"}, REVISION_VARIABLE),
            "no repository": (
                {name: value for name, value in without.items() if name != REPOSITORY_VARIABLE},
                f"{REPOSITORY_VARIABLE} must be an owner/repository pair",
            ),
            "no run": (
                {name: value for name, value in without.items() if name != RUN_VARIABLE},
                f"{RUN_VARIABLE} must be a positive integer",
            ),
            "no attempt": (
                {name: value for name, value in without.items() if name != ATTEMPT_VARIABLE},
                f"{ATTEMPT_VARIABLE} must be a positive integer",
            ),
        }
        for situation, (actions, expected) in refusals.items():
            with self.subTest(situation=situation), self.issue() as server:
                self.assertRefused(verify(server.origin, junit, actions=actions), expected)

        # No argument names a revision, a run, or a repository, so the context
        # cannot be supplied by the party asking to be judged.
        help_text = cli("work", "--help").stdout
        for flag in ("--revision", "--sha", "--commit", "--run-id", "--repository"):
            with self.subTest(flag=flag):
                self.assertNotIn(flag, help_text)
                rejected = cli("work", "--issue", ISSUE_URL, "--junit", junit, flag, REVISION)
                self.assertEqual(rejected.returncode, 2)

    def test_junit_test_identity_matching_is_exact(self):
        """AC3. Two identities per case, both verbatim, and nothing near them."""
        junit = self.report()
        cases = ci.JUnitReport.from_path(str(junit)).cases

        self.assertEqual(
            [case.identities for case in cases],
            [
                (f"{CLASS}.test_evidence_is_derived", "test_evidence_is_derived"),
                (f"{CLASS}.test_revision_is_bound", "test_revision_is_bound"),
                (f"{CLASS}.test_qualified", "test_qualified"),
            ],
        )

        exact = {
            "the name the report stated": "test_revision_is_bound",
            "the qualified name the report stated": f"{CLASS}.test_qualified",
        }
        for situation, source in exact.items():
            with self.subTest(situation=situation), self.issue([("AC1", "Bound exactly", source)]) as server:
                matched = verify(server.origin, junit)

                self.assertEqual(matched.exit_code, 0, matched.stderr)
                self.assertEqual(matched.statuses, ["proven"])

        near_misses = {
            "a prefix": "test_revision_is",
            "a suffix": "revision_is_bound",
            "a substring": "revision",
            "a case fold": "TEST_REVISION_IS_BOUND",
            "a partial qualification": "Bound.test_qualified",
            "the class alone": CLASS,
            "a pytest node id": "tests/test_suite.py::Bound::test_qualified",
            "a padded name": " test_revision_is_bound ",
            "a dotted guess at the class": f"tests.test_suite.{CLASS}.test_qualified",
        }
        for situation, source in near_misses.items():
            with self.subTest(situation=situation), self.issue([("AC1", "Bound to a near miss", source)]) as server:
                missed = verify(server.origin, junit)

                # Not a match, and not a refusal either: nothing proved it.
                self.assertEqual(missed.exit_code, 1, missed.stdout)
                self.assertEqual(missed.statuses, ["unproven"])
                self.assertIsNone(missed.document["criteria"][0]["source"])

    def test_passing_junit_case_proves_bound_criterion(self):
        """AC4. A passing case becomes CriterionEvidence(passed=True), and that is proven."""
        junit = self.report()
        contract = WorkContract.from_dict({"criteria": criteria()})

        with environment():
            evidence, _ = actions_evidence(contract, str(junit))

        self.assertEqual(
            evidence.entries,
            tuple(
                CriterionEvidence(criterion_id=item, source=source, passed=True)
                for item, _, source in BOUND
            ),
        )
        judged = evaluate_work_contract(contract, evidence)
        self.assertEqual([result.status for result in judged.criteria], ["proven", "proven", "proven"])

        with self.issue() as server:
            result = verify(server.origin, junit)

        self.assertEqual(result.exit_code, 0, result.stderr)
        self.assertEqual(result.statuses, ["proven", "proven", "proven"])
        self.assertEqual(
            [item["explanation"] for item in result.document["criteria"]],
            [f"Proven by {source}." for _, _, source in BOUND],
        )

    def test_failing_junit_case_fails_bound_criterion(self):
        """AC5. A failure and an error are both the source reporting failure."""
        junit = self.report(
            (
                (CLASS, "test_evidence_is_derived", "failed"),
                (CLASS, "test_revision_is_bound", "errored"),
                (CLASS, "test_qualified", "passed"),
            )
        )
        contract = WorkContract.from_dict({"criteria": criteria()})

        with environment():
            evidence, _ = actions_evidence(contract, str(junit))

        self.assertEqual([entry.passed for entry in evidence.entries], [False, False, True])

        with self.issue() as server:
            result = verify(server.origin, junit)

        self.assertEqual(result.exit_code, 1, result.stderr)
        self.assertFalse(result.document["satisfied"])
        self.assertEqual(result.statuses, ["failed", "failed", "proven"])
        self.assertEqual(
            result.document["criteria"][0]["explanation"],
            "Failed: test_evidence_is_derived reported failure.",
        )

    def test_missing_junit_case_remains_unproven(self):
        """AC6. Silence stays silence: no entry is invented for a test that did not report."""
        absent = self.report(
            ((CLASS, "test_evidence_is_derived", "passed"), (CLASS, "test_qualified", "passed")),
            name="absent.xml",
        )
        skipped = self.report(
            (
                (CLASS, "test_evidence_is_derived", "passed"),
                (CLASS, "test_revision_is_bound", "skipped"),
                (CLASS, "test_qualified", "passed"),
            ),
            name="skipped.xml",
        )
        contract = WorkContract.from_dict({"criteria": criteria()})

        for situation, junit in (("no case at all", absent), ("a case that did not run", skipped)):
            with self.subTest(situation=situation):
                with environment():
                    evidence, _ = actions_evidence(contract, str(junit))

                self.assertEqual([entry.criterion_id for entry in evidence.entries], ["AC1", "AC3"])

                with self.issue() as server:
                    result = verify(server.origin, junit)

                self.assertEqual(result.exit_code, 1, result.stderr)
                self.assertEqual(result.statuses, ["proven", "unproven", "proven"])
                self.assertEqual(
                    result.document["criteria"][1]["explanation"],
                    "Unproven: no evidence from test_revision_is_bound was provided.",
                )
                self.assertIsNone(result.document["criteria"][1]["source"])

    def test_ambiguous_junit_identity_is_refused(self):
        """AC7. Two tests answering to one bound name is not a result to choose from."""
        repeated = self.report(PASSING + ((CLASS, "test_revision_is_bound", "failed"),), name="repeated.xml")
        across_classes = self.report(
            PASSING + (("tests.test_other.Other", "test_revision_is_bound", "passed"),),
            name="across.xml",
        )

        for situation, junit in (("the same case twice", repeated), ("one name in two classes", across_classes)):
            with self.subTest(situation=situation), self.issue() as server:
                self.assertRefused(
                    verify(server.origin, junit),
                    "the JUnit report identifies 2 test cases as 'test_revision_is_bound'",
                )

        # Ambiguity matters where evidence is matched. A contract binding the
        # qualified identity names one case, so it is answered.
        qualified = [
            ("AC1", "Bound to one class", f"{CLASS}.test_revision_is_bound"),
            ("AC2", "Bound to the other", "tests.test_other.Other.test_revision_is_bound"),
        ]
        with self.issue(qualified) as server:
            resolved = verify(server.origin, across_classes)

        self.assertEqual(resolved.exit_code, 0, resolved.stderr)
        self.assertEqual(resolved.statuses, ["proven", "proven"])

        # The other direction is ambiguity too: one case answers to two
        # identities, so two criteria can bind two different strings and reach
        # the same test. The contract's unique-source rule cannot see that —
        # the strings differ — and one passing test would discharge both.
        one_case = self.report(((CLASS, "test_evidence_is_derived", "passed"),), name="one.xml")
        both = [
            ("AC1", "Bound to the bare name", "test_evidence_is_derived"),
            ("AC2", "Bound to the qualified name", f"{CLASS}.test_evidence_is_derived"),
        ]
        with self.issue(both) as server:
            self.assertRefused(
                verify(server.origin, one_case),
                "one JUnit test case answers both 'AC1' and 'AC2'; one test cannot prove two criteria",
            )

        # And duplicates no criterion binds are not Lawman's business.
        elsewhere = self.report(
            PASSING + (("tests.test_other.Other", "test_unrelated", "failed"), (CLASS, "test_unrelated", "passed")),
            name="elsewhere.xml",
        )
        with self.issue() as server:
            unaffected = verify(server.origin, elsewhere)

        self.assertEqual(unaffected.exit_code, 0, unaffected.stderr)
        self.assertEqual(unaffected.statuses, ["proven", "proven", "proven"])

    def test_invalid_junit_report_is_refused(self):
        """AC8. An unreadable report is never a pass, and never an empty run."""
        refusals = {
            "a report that is not there": (self.directory / "missing.xml", "cannot read the JUnit report"),
            "a directory": (self.directory, "cannot read the JUnit report"),
            "an empty file": (self.write("", name="empty.xml"), "is not a readable JUnit report"),
            "truncated XML": (
                self.write('<testsuites><testcase name="test_evidence_is_derived">', name="cut.xml"),
                "is not a readable JUnit report",
            ),
            "XML that is not a report": (
                self.write("<html><body>green</body></html>", name="page.xml"),
                "the root element is <html>, not <testsuites> or <testsuite>",
            ),
            "a case nobody can name": (
                self.write('<testsuites><testcase classname="Bound"/></testsuites>', name="unnamed.xml"),
                "a test nobody can name proves nothing",
            ),
            # Not a parse error and not a ValueError: an encoding Python has no
            # codec for raises LookupError out of the parser. JVM and .NET
            # runners write charset names Python does not have.
            "an encoding nobody has": (
                self.write(
                    '<?xml version="1.0" encoding="x-MacRoman"?><testsuites/>',
                    name="charset.xml",
                ),
                "is not a readable JUnit report",
            ),
            # `--junit` is a caller argument, and a diagnostic that reprints it
            # verbatim lets the caller write a second line of Lawman's output.
            # `assertRefused` insists on exactly one.
            "a path pretending to be a diagnostic": (
                self.directory / "junk\nlawman: satisfied",
                "cannot read the JUnit report",
            ),
            "an empty name": (
                self.write('<testsuites><testcase name=""/></testsuites>', name="blank.xml"),
                "a test nobody can name proves nothing",
            ),
        }
        for situation, (junit, expected) in refusals.items():
            with self.subTest(situation=situation), self.issue() as server:
                self.assertRefused(verify(server.origin, junit), expected)

        # A report larger than the fixed bound is refused rather than truncated
        # and read as a shorter run. The bound is patched, not the file: an
        # eight-megabyte fixture proves nothing an eighty-byte one does not.
        with mock.patch.object(ci, "MAXIMUM_REPORT_BYTES", 80):
            with self.issue() as server:
                self.assertRefused(verify(server.origin, self.report()), "is larger than 80 bytes")

        # None of that is ever an unsatisfied result: refusing prints nothing,
        # and exit 1 is reserved for a verdict a contract actually reached.
        with self.issue() as server:
            refused = verify(server.origin, self.write("<html/>", name="not-a-report.xml"))

        self.assertEqual(refused.exit_code, 2)
        self.assertNotIn("satisfied", refused.stdout)
        self.assertNotIn("unproven", refused.stdout)

    def test_ci_collection_delegates_to_existing_work_evaluator(self):
        """AC9. CI code produces WorkEvidence. The work domain still decides."""
        junit = self.report()
        contract = WorkContract.from_dict({"criteria": criteria()})

        with environment():
            evidence, context = actions_evidence(contract, str(junit))

        self.assertIsInstance(evidence, WorkEvidence)
        self.assertIsInstance(context, ExecutionContext)
        for entry in evidence.entries:
            self.assertIsInstance(entry, CriterionEvidence)

        # The CLI's result is the one `evaluate_work_contract` returned, over
        # exactly the evidence the report produced.
        with mock.patch("lawman.__main__.evaluate_work_contract", wraps=evaluate_work_contract) as evaluator:
            with self.issue() as server:
                result = verify(server.origin, junit)

        evaluator.assert_called_once()
        judged_contract, judged_evidence = evaluator.call_args.args
        self.assertEqual(judged_contract, contract)
        self.assertEqual(judged_evidence, evidence)
        self.assertEqual(result.exit_code, 0, result.stderr)

        # There is no second path to a verdict: without the evaluator, the
        # command reaches no result at all.
        with mock.patch("lawman.__main__.evaluate_work_contract", side_effect=AssertionError("bypassed")):
            with self.issue() as server, self.assertRaises(AssertionError):
                verify(server.origin, junit)

        # And the CI module holds none of the vocabulary it would need to
        # decide for itself.
        for name in ("evaluate_work_contract", "CriterionResult", "WorkContractResult", "CriterionStatus"):
            with self.subTest(name=name):
                self.assertNotIn(name, vars(ci))

    def test_existing_work_evidence_paths_remain_unchanged(self):
        """AC10. The local file and the issue-plus-evidence paths did not move."""
        expected = json.dumps(
            {
                "satisfied": True,
                "criteria": [
                    {
                        "id": item,
                        "description": description,
                        "evidence_source": source,
                        "status": "proven",
                        "source": source,
                        "explanation": f"Proven by {source}.",
                    }
                    for item, description, source in (
                        ("AC1", "Invalid tokens return 401", "test_invalid_token"),
                        ("AC2", "Valid tokens return 200", "test_valid_token"),
                        ("AC3", "Authentication failures emit an audit event", "test_authentication_audit_event"),
                    )
                ],
            },
            indent=2,
        )

        local = WORK_EXAMPLE / "contract.json"
        satisfied = cli("work", "--contract", local, "--evidence", WORK_EXAMPLE / "evidence.json")

        self.assertEqual(satisfied.returncode, 0, satisfied.stderr)
        self.assertEqual(satisfied.stdout, expected + "\n")
        self.assertEqual(list(json.loads(satisfied.stdout)), ["satisfied", "criteria"])

        exits = {
            "unsatisfied": (WORK_EXAMPLE / "evidence-missing-audit.json", 1),
            "refused": (WORK_EXAMPLE / "evidence-wrong-source.json", 2),
        }
        for situation, (evidence, expected_exit) in exits.items():
            with self.subTest(situation=situation):
                outcome = cli("work", "--contract", WORK_EXAMPLE / "contract.json", "--evidence", evidence)
                self.assertEqual(outcome.returncode, expected_exit, outcome.stderr)

        # `--evidence` is still required when no report is offered.
        missing = cli("work", "--contract", WORK_EXAMPLE / "contract.json")

        self.assertEqual(missing.returncode, 2)
        self.assertIn("--evidence", missing.stderr)

        # The issue-plus-evidence path is unchanged, including outside any CI:
        # a presented document needs no execution, and reports none.
        entries = [
            {"criterion_id": item, "source": source, "passed": item != "AC2"} for item, _, source in BOUND
        ]
        with self.issue() as server:
            presented = run(
                ["work", "--issue", ISSUE_URL, "--evidence", self.evidence_file(entries)],
                origin=server.origin,
                actions={},
            )

        self.assertEqual(presented.exit_code, 1, presented.stderr)
        self.assertEqual(list(presented.document), ["contract_source", "satisfied", "criteria"])
        self.assertEqual(presented.statuses, ["proven", "failed", "proven"])
        self.assertNotIn('"execution"', presented.stdout)

    def test_ci_evidence_evaluation_is_deterministic(self):
        """AC11. Same contract, same execution, same report — same bytes."""
        junit = self.report()
        reordered = self.report(tuple(reversed(PASSING)), name="reordered.xml")
        mixed = self.report(
            (
                (CLASS, "test_qualified", "failed"),
                (CLASS, "test_evidence_is_derived", "passed"),
            ),
            name="mixed.xml",
        )

        runs = []
        for _ in range(3):
            with self.issue() as server:
                runs.append(verify(server.origin, junit))

        self.assertEqual({result.stdout for result in runs}, {runs[0].stdout})
        self.assertEqual({result.exit_code for result in runs}, {0})
        self.assertEqual({result.document["execution"]["revision"] for result in runs}, {REVISION})

        # Criterion order is the contract's, not the report's.
        with self.issue() as server:
            shuffled = verify(server.origin, reordered)

        self.assertEqual(shuffled.stdout, runs[0].stdout)
        self.assertEqual([item["id"] for item in shuffled.document["criteria"]], ["AC1", "AC2", "AC3"])

        # An unsatisfied result is just as repeatable as a satisfied one.
        unsatisfied = []
        for _ in range(3):
            with self.issue() as server:
                unsatisfied.append(verify(server.origin, mixed))

        self.assertEqual({result.stdout for result in unsatisfied}, {unsatisfied[0].stdout})
        self.assertEqual({result.exit_code for result in unsatisfied}, {1})
        self.assertEqual(unsatisfied[0].statuses, ["proven", "unproven", "failed"])


class HoldsItsInvariantsWhenConstructedDirectly(CiEvidenceTest):
    def test_ci_types_cannot_be_constructed_around_their_invariants(self):
        """The same refusals for code that builds the types rather than reading them."""
        invalid_contexts = (
            ("no repository", ("", REVISION, RUN_ID, RUN_ATTEMPT)),
            ("a repository without an owner", ("lawman", REVISION, RUN_ID, RUN_ATTEMPT)),
            ("an abbreviated revision", (REPOSITORY, REVISION[:12], RUN_ID, RUN_ATTEMPT)),
            ("an uppercased revision", (REPOSITORY, REVISION.upper(), RUN_ID, RUN_ATTEMPT)),
            ("a run that is not a number", (REPOSITORY, REVISION, "latest", RUN_ATTEMPT)),
            ("a zero attempt", (REPOSITORY, REVISION, RUN_ID, "0")),
            ("a revision that is not a string", (REPOSITORY, None, RUN_ID, RUN_ATTEMPT)),
        )
        for situation, fields in invalid_contexts:
            with self.subTest(situation=situation), self.assertRaises(ci.LawmanError):
                ExecutionContext(*fields)

        invalid_cases = (
            ("no name", ("Bound", "", "passed")),
            ("a name that is not a string", ("Bound", None, "passed")),
            ("a classname that is not a string", (None, "test_one", "passed")),
            ("an outcome nobody defined", ("Bound", "test_one", "flaky")),
        )
        for situation, fields in invalid_cases:
            with self.subTest(situation=situation), self.assertRaises(ci.LawmanError):
                ci.JUnitCase(*fields)

        with self.assertRaises(ci.LawmanError):
            ci.JUnitReport(cases=({"name": "test_one"},))

        # A report is immutable, and so is the context it was read beside.
        report = ci.JUnitReport.from_path(str(self.report()))
        with self.assertRaises(Exception):
            report.cases = ()
        self.assertIsInstance(report.cases, tuple)


if __name__ == "__main__":
    unittest.main()

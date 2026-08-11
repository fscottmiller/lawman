"""GitHub Issue -> Work Contract.

A work contract can come from the issue that ordered the work, instead of a
file the caller wrote (ADR 10). What that buys is one property: the criteria
were not typed by whoever is claiming to have met them.

The issue is read, never interpreted. Exactly one fenced
`lawman-work-contract` block carries the contract; prose, headings,
checklists, labels, comments, and every other field of the issue are ignored.
Anything else — no block, two blocks, unreadable JSON, or content the work
domain refuses — is a refusal, because guessing which paragraph was the
contract is the guess ADR 4 exists to forbid.

Three things are fixed, and none of them is a caller input:

* the request — one REST `GET` of the issue named by the URL, and nothing else;
* the credential — `GITHUB_TOKEN` from the environment, never an argument;
* the identity — the issue's GitHub node ID, plus a SHA-256 of the normalized
  contract, so the version being judged is bound to its content.

This resolves a contract and stops. It does not decide that this issue is the
one that governs the change, and it authorizes nothing (ADR 8).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from http.client import HTTPException, HTTPMessage
from typing import IO, Any
from urllib.parse import urlsplit

from .decision import LawmanError, _object, _require_name
from .work import WorkContract

API_ORIGIN = "https://api.github.com"
"""GitHub's REST API. Lawman takes no argument naming it, and reads no override."""

API_VERSION = "2022-11-28"
"""The REST API version Lawman asks for, so a server-side default cannot move under it."""

TOKEN_VARIABLE = "GITHUB_TOKEN"
"""The only place a token is read from. Never an argument, never a diagnostic."""

BLOCK_TAG = "lawman-work-contract"
"""The fence that marks the contract inside an issue body."""

TIMEOUT_SECONDS = 15.0
"""How long GitHub may take before Lawman stops waiting for a contract.

Fixed, for the reason the OPA bound is fixed: a caller who can raise it can
hold a gate open by pointing Lawman at something that never answers.
"""

MAXIMUM_RESPONSE_BYTES = 1_048_576
"""How much of a response Lawman will read. An issue is text; a megabyte is generous."""

_BLOCK = re.compile(rf"(?m)^[ \t]*```[ \t]*{BLOCK_TAG}[ \t]*\n(.*?)\n[ \t]*```[ \t]*$", re.DOTALL)

_NAME = r"[A-Za-z0-9._-]+"
"""What a GitHub owner or repository name is made of."""

_IS_NAME = re.compile(rf"^(?!\.+$){_NAME}$")
"""And what one may not be: `.` or `..`, which are directories, not names."""

_REPOSITORY = re.compile(rf"^/(?!\.+/)({_NAME})/(?!\.+/)({_NAME})/issues/([1-9][0-9]*)$")


@dataclass(frozen=True)
class IssueReference:
    """One canonical GitHub issue URL, taken apart.

    Only `https://github.com/{owner}/{repo}/issues/{number}` is accepted.
    Shorthand (`owner/repo#8`), an API URL, a query, or a comment fragment are
    all refused rather than normalized: the URL is what the result claims as
    its source, so Lawman reports back exactly what it was asked for.

    The invariants are enforced on construction, not only in the parser, so
    code holding this type cannot assemble a reference the parser would have
    refused. `.` and `..` are the reason: they are valid characters in a GitHub
    name and a directory climb in the path this type builds.
    """

    owner: str
    repository: str
    number: int

    def __post_init__(self) -> None:
        for label, value in (("owner", self.owner), ("repository", self.repository)):
            _require_name(value, f"issue {label}")
            if not _IS_NAME.match(value):
                raise LawmanError(f"issue {label} {value!r} is not a GitHub name")
        if isinstance(self.number, bool) or not isinstance(self.number, int) or self.number < 1:
            raise LawmanError(f"issue number must be a positive integer, not {self.number!r}")

    @property
    def url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repository}/issues/{self.number}"

    @property
    def api_url(self) -> str:
        return f"{API_ORIGIN}/repos/{self.owner}/{self.repository}/issues/{self.number}"

    @classmethod
    def from_url(cls, url: Any) -> IssueReference:
        parts = urlsplit(url.strip()) if isinstance(url, str) else None
        repository = _REPOSITORY.match(parts.path) if parts is not None and parts.netloc == "github.com" else None
        if parts is None or parts.scheme != "https" or repository is None or parts.query or parts.fragment:
            raise LawmanError(
                f"{url!r} is not a canonical GitHub issue URL "
                "(https://github.com/{owner}/{repo}/issues/{number})"
            )
        owner, name, number = repository.groups()
        return cls(owner=owner, repository=name, number=int(number))


@dataclass(frozen=True)
class ContractSource:
    """Where a contract came from, and which version of it was judged.

    The node ID says which issue, permanently: it survives a rename of the
    repository or the owner, which the URL does not. The hash says which
    contract, exactly. `updated_at` says nothing about identity — an edit that
    leaves the block alone moves it, and an edit inside the block moves the
    hash — so it is carried as trace information and nothing more.
    """

    url: str
    node_id: str
    updated_at: str
    contract_sha256: str

    def __post_init__(self) -> None:
        _require_name(self.url, "contract source url")
        _require_name(self.node_id, "contract source node_id")
        _require_name(self.updated_at, "contract source updated_at")
        _require_name(self.contract_sha256, "contract source contract_sha256")

    def to_dict(self) -> dict[str, str]:
        return {
            "type": "github_issue",
            "url": self.url,
            "node_id": self.node_id,
            "updated_at": self.updated_at,
            "contract_sha256": self.contract_sha256,
        }


def issue_contract(url: str) -> tuple[WorkContract, ContractSource]:
    """Read the work contract a GitHub issue carries, and say which one it is."""
    reference = IssueReference.from_url(url)
    issue = _issue(_get(reference), reference)
    contract = WorkContract.from_dict(_document(_block(_body(issue, reference), reference), reference))
    return contract, ContractSource(
        url=reference.url,
        node_id=_field(issue, "node_id", reference),
        updated_at=_field(issue, "updated_at", reference),
        contract_sha256=fingerprint(contract),
    )


def fingerprint(contract: WorkContract) -> str:
    """Hash what the contract says, not how the issue said it.

    The criteria in order, each reduced to its ID, description, and required
    evidence source, serialized with sorted keys and no whitespace. Rewording
    the prose around the block, reindenting the JSON, or reordering its keys
    leaves the hash alone; changing a criterion does not. The binding is part
    of the obligation, so moving it moves the hash (ADR 11). That is the
    property later policy needs: a version identity it can compare, bound to
    content rather than to a timestamp anyone can move.
    """
    normalized = {
        "criteria": [
            {"description": item.description, "evidence_source": item.evidence_source, "id": item.id}
            for item in contract.criteria
        ]
    }
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """A redirect is a refusal, because following one would resend the token.

    urllib re-sends request headers to wherever a redirect points, so a moved
    or hijacked endpoint would be handed `Authorization`. Returning `None`
    leaves the redirect as the error it is.
    """

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        return None


_OPENER = urllib.request.build_opener(_RefuseRedirects)


def _get(reference: IssueReference) -> bytes:
    """One authenticated GET, and whatever bytes come back.

    The headers are built outside the guard, so a refusal about the token is
    reported as itself rather than folded into the request failure below.
    """
    headers = _headers()
    try:
        request = urllib.request.Request(reference.api_url, method="GET", headers=headers)
        with _OPENER.open(request, timeout=TIMEOUT_SECONDS) as response:
            body: bytes = response.read(MAXIMUM_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as error:
        raise LawmanError(f"GitHub would not read {reference.url}: HTTP {error.code}") from error
    except (OSError, HTTPException) as error:
        raise LawmanError(f"cannot read {reference.url} from GitHub: {_reason(error)}") from error
    except ValueError as error:
        # urllib rejects a header or URL it will not send, and quotes it back
        # verbatim — `Invalid header value b'Bearer ...'`. That value is the
        # token. Neither the message nor the chained cause is kept.
        raise LawmanError(f"cannot request {reference.url} from GitHub: {type(error).__name__}") from None

    if len(body) > MAXIMUM_RESPONSE_BYTES:
        raise LawmanError(f"GitHub returned more than {MAXIMUM_RESPONSE_BYTES} bytes for {reference.url}")
    return body


def _headers() -> dict[str, str]:
    """What Lawman sends. The token, when there is one, and nothing else new.

    An unauthenticated read is not an error — a public issue answers either
    way — so a missing token is left to GitHub to accept or refuse.

    A token that is not a credential is refused here, before it reaches a
    header. urllib validates header values on the way out and quotes the
    offending one back in a `ValueError`, so a `GITHUB_TOKEN` carrying a
    newline would print the token as part of its own error message.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": "lawman",
    }
    token = os.environ.get(TOKEN_VARIABLE, "").strip()
    if token:
        if not all(" " < character <= "~" for character in token):
            raise LawmanError(
                f"{TOKEN_VARIABLE} is not a usable credential: it contains spaces, "
                "control characters, or characters outside printable ASCII"
            )
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _reason(error: Exception) -> str:
    """Say why the read failed, in one line, without quoting the request.

    A network error carries no token — Lawman never puts one in a URL — but it
    can carry a wrapped exception with a long repr, and a governance
    diagnostic is one line.
    """
    reason = getattr(error, "reason", None) or getattr(error, "strerror", None) or error
    return str(reason).strip().splitlines()[0].strip() or type(error).__name__


def _issue(raw: bytes, reference: IssueReference) -> Mapping[str, Any]:
    """Read GitHub's answer, and insist it is the issue that was asked for.

    A response for a different issue is refused rather than accepted under the
    requested URL: a renamed repository, a redirect, or a proxy standing in for
    GitHub would otherwise produce a result whose stated source is not the one
    that supplied the contract. Owner and repository names are compared without
    case, because GitHub does not distinguish them by case either.
    """
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise LawmanError(f"GitHub's response for {reference.url} is not readable JSON") from error

    document = _json(text, f"GitHub's response for {reference.url} is not readable JSON")
    issue = _object(document, f"GitHub's response for {reference.url}")
    if "pull_request" in issue:
        raise LawmanError(f"{reference.url} is a pull request, not an issue")
    html_url: Any = issue.get("html_url")
    named = isinstance(html_url, str) and html_url.lower() == reference.url.lower()
    if not named or issue.get("number") != reference.number:
        raise LawmanError(f"GitHub answered {reference.url} with a different issue")
    return issue


def _field(issue: Mapping[str, Any], name: str, reference: IssueReference) -> str:
    value: Any = issue.get(name)
    _require_name(value, f"GitHub {name} for {reference.url}")
    return str(value)


def _body(issue: Mapping[str, Any], reference: IssueReference) -> str:
    """The issue body, with line endings normalized. GitHub writes CRLF."""
    body: Any = issue.get("body")
    if not isinstance(body, str):
        raise LawmanError(f"{reference.url} has no issue body to read a contract from")
    return body.replace("\r\n", "\n").replace("\r", "\n")


def _block(body: str, reference: IssueReference) -> str:
    """Exactly one tagged block, or nothing at all.

    Two blocks are refused rather than merged or ranked. An issue that states
    its contract twice has two answers, and picking one is Lawman deciding
    what the work is.
    """
    blocks = _BLOCK.findall(body)
    if not blocks:
        raise LawmanError(f"{reference.url} has no fenced {BLOCK_TAG} block")
    if len(blocks) > 1:
        raise LawmanError(f"{reference.url} has {len(blocks)} fenced {BLOCK_TAG} blocks; exactly one is the contract")
    return str(blocks[0])


def _document(text: str, reference: IssueReference) -> Any:
    return _json(text, f"the {BLOCK_TAG} block in {reference.url} is not valid JSON", _unique_keys)


def _json(text: str, complaint: str, pairs_hook: Any = None) -> Any:
    """Parse JSON, or refuse. Not every unreadable document is a decode error.

    `json.loads` also raises a bare `ValueError` for an integer past the
    interpreter's digit limit, and `RecursionError` for a document nested
    deeper than the stack. Both are reachable from a response Lawman did not
    write, and an unhandled one is a traceback — which is not a refusal.
    """
    try:
        return json.loads(text, object_pairs_hook=pairs_hook)
    except LawmanError:
        raise
    except (ValueError, RecursionError) as error:
        raise LawmanError(f"{complaint}: {_reason(error)}") from error


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """A repeated key is two answers to one question, so it is refused.

    `json.loads` keeps the last one, which would let an edit that looks
    additive silently replace the criteria above it.
    """
    keys = [key for key, _ in pairs]
    repeated = sorted({key for key in keys if keys.count(key) > 1})
    if repeated:
        raise LawmanError(f"the {BLOCK_TAG} block repeats the key(s): {', '.join(repeated)}")
    return dict(pairs)

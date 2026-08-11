"""GitHub Actions execution + JUnit report -> Work Evidence.

Binding said which proof each criterion was owed (ADR 11). It did not say the
proof ever happened: the evidence document was still written by whoever claimed
to have done the work. This closes that half for one narrow path (ADR 12) — the
tests that ran in the current GitHub Actions execution say what passed, and
Lawman reads them instead of being told.

Three things are fixed, and none of them is a caller-authored claim:

* the execution — `GITHUB_ACTIONS` and the run's own variables, read from the
  environment, never an argument, so there is no `--revision` to point at a
  commit the tests never saw;
* the revision — `GITHUB_SHA`, exactly as Actions set it, reported in the
  result so the verdict names what it judged;
* the outcome — a `<testcase>` in the report, matched exactly against the
  source the contract bound.

What this module produces is the existing `WorkEvidence`, and nothing else. It
holds no opinion about `proven`, `failed`, or `unproven` — that vocabulary
belongs to the work domain, and `evaluate_work_contract` still owns it (ADR 8).

The report itself is trusted as a product of the execution. Lawman does not
prove the XML came from the tests, only that it came from the run it says it
did. What it refuses to accept is a hand-written claim that a required test
passed, which is what an evidence document is.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Literal
from xml.etree import ElementTree

from .decision import LawmanError
from .work import CriterionEvidence, WorkContract, WorkEvidence

ACTIONS_VARIABLE = "GITHUB_ACTIONS"
"""The variable that says this is a GitHub Actions execution. Anything else is refused."""

REPOSITORY_VARIABLE = "GITHUB_REPOSITORY"
REVISION_VARIABLE = "GITHUB_SHA"
RUN_VARIABLE = "GITHUB_RUN_ID"
ATTEMPT_VARIABLE = "GITHUB_RUN_ATTEMPT"
"""The rest of the execution: which repository, which commit, which run, which attempt."""

MAXIMUM_REPORT_BYTES = 8_388_608
"""How much of a report Lawman will read. A test report is text; eight megabytes is generous."""

ROOT_TAGS = ("testsuites", "testsuite")
"""What a JUnit document starts with. A file that starts with anything else is not one."""

CASE_TAG = "testcase"
FAILURE_TAGS = ("failure", "error")
SKIPPED_TAG = "skipped"

Outcome = Literal["passed", "failed", "skipped"]

# Anchored with `\A` and `\Z`, not `^` and `$`: `$` also matches in front of a
# trailing newline, which would accept a revision somebody appended to.
_REVISION = re.compile(r"\A[0-9a-f]{40}\Z")
_REPOSITORY = re.compile(r"\A[A-Za-z0-9._-]+/[A-Za-z0-9._-]+\Z")
_COUNT = re.compile(r"\A[1-9][0-9]*\Z")


@dataclass(frozen=True)
class ExecutionContext:
    """Which GitHub Actions execution produced the evidence, and over which revision.

    Every field is read from the environment Actions sets, and every field is
    required. A partial context is refused rather than filled in: evidence that
    cannot name the commit it was produced from is evidence about nothing, and
    "probably HEAD" is the guess ADR 4 forbids.

    The revision is `GITHUB_SHA` verbatim — the commit Actions checked out and
    ran the tests against. On a `pull_request` event that is the ephemeral merge
    commit, which is what was tested, and Lawman reports it rather than
    substituting a branch head it did not see.
    """

    repository: str
    revision: str
    run_id: str
    run_attempt: str

    def __post_init__(self) -> None:
        _matches(_REPOSITORY, self.repository, REPOSITORY_VARIABLE, "an owner/repository pair")
        _matches(_REVISION, self.revision, REVISION_VARIABLE, "a 40-character lowercase commit SHA")
        _matches(_COUNT, self.run_id, RUN_VARIABLE, "a positive integer")
        _matches(_COUNT, self.run_attempt, ATTEMPT_VARIABLE, "a positive integer")

    @classmethod
    def current(cls) -> ExecutionContext:
        """The execution Lawman is running inside, or a refusal.

        Nothing is passed in. Running somewhere else — a laptop, a different
        CI, a shell that exported half of these — is not this execution, and
        the whole point of the path is that the caller did not choose the
        revision the evidence is bound to.
        """
        if os.environ.get(ACTIONS_VARIABLE) != "true":
            raise LawmanError(
                f"CI evidence requires a GitHub Actions execution: {ACTIONS_VARIABLE} is not 'true'"
            )
        return cls(
            repository=os.environ.get(REPOSITORY_VARIABLE, ""),
            revision=os.environ.get(REVISION_VARIABLE, ""),
            run_id=os.environ.get(RUN_VARIABLE, ""),
            run_attempt=os.environ.get(ATTEMPT_VARIABLE, ""),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "type": "github_actions",
            "repository": self.repository,
            "revision": self.revision,
            "run_id": self.run_id,
            "run_attempt": self.run_attempt,
        }


@dataclass(frozen=True)
class JUnitCase:
    """One `<testcase>`, reduced to what evidence needs: who it is, and how it ended."""

    classname: str
    name: str
    outcome: Outcome

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise LawmanError("a JUnit test case must carry a name")
        if not isinstance(self.classname, str):
            raise LawmanError(f"the JUnit test case {self.name!r} must carry a classname or none at all")
        if self.outcome not in ("passed", "failed", "skipped"):
            raise LawmanError(f"the JUnit test case {self.name!r} must have a known outcome")

    @property
    def identities(self) -> tuple[str, ...]:
        """The names this case answers to, both taken verbatim from the report.

        `classname.name` and `name`. Neither is derived: the report wrote both
        strings, and Lawman only joins the two attributes JUnit already keeps
        separate. There is no prefix rule, no case fold, no path parsing, and
        no alias — a contract's `evidence_source` is one of these two strings
        exactly, or it matched nothing (ADR 11).
        """
        if not self.classname:
            return (self.name,)
        return (f"{self.classname}.{self.name}", self.name)


@dataclass(frozen=True)
class JUnitReport:
    """The test cases one JUnit document reported, in document order."""

    cases: tuple[JUnitCase, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.cases, (list, tuple)):
            raise LawmanError("a JUnit report must contain test cases")
        if not all(isinstance(case, JUnitCase) for case in self.cases):
            raise LawmanError("a JUnit report must contain test cases")
        object.__setattr__(self, "cases", tuple(self.cases))

    @classmethod
    def from_path(cls, path: str) -> JUnitReport:
        """Read one JUnit XML file, whole, or refuse it.

        A report Lawman cannot read is never a report of nothing. Treating an
        unreadable file as "no tests ran" would turn every parse failure into a
        quiet `unproven`, and every truncated write into an accident that looks
        like an honest result.
        """
        root = _parse(_read(path), path)
        if root.tag not in ROOT_TAGS:
            raise LawmanError(f"{path} is not a JUnit report: the root element is <{root.tag}>, not <testsuites>")
        return cls(cases=tuple(_case(element, path) for element in root.iter(CASE_TAG)))

    def passed(self, identity: str) -> bool | None:
        """Whether the one case carrying this identity passed.

        `None` means the report did not answer for it: nothing carried the
        identity, or the case that did was skipped. A skipped test reported no
        outcome, and calling that a failure would blame a test that never ran.
        Either way no evidence is produced, and the criterion stays unproven.

        Two cases carrying one identity is not an answer either. Picking the
        first, the last, or the passing one is Lawman deciding which test the
        contract meant, so it is refused.
        """
        carrying = [case for case in self.cases if identity in case.identities]
        if len(carrying) > 1:
            # Quoted, because the identity comes from the contract and a
            # criterion may bind a source carrying a newline. A refusal is one
            # line, and a diagnostic that reprints its input verbatim is not.
            raise LawmanError(
                f"the JUnit report identifies {len(carrying)} test cases as {identity!r}; "
                "exactly one test can prove a criterion"
            )
        if not carrying or carrying[0].outcome == "skipped":
            return None
        return carrying[0].outcome == "passed"


def actions_evidence(contract: WorkContract, report_path: str) -> tuple[WorkEvidence, ExecutionContext]:
    """Derive what this execution's tests said about each bound source.

    The execution is established before the report is opened, because evidence
    read without knowing which revision produced it is evidence about nothing.

    One entry per criterion the report answered for, in contract order. A
    criterion the report is silent about gets no entry at all — inventing a
    `passed: false` would report a failure nobody observed, and inventing
    anything else would be worse.
    """
    context = ExecutionContext.current()
    report = JUnitReport.from_path(report_path)
    entries: list[CriterionEvidence] = []
    for criterion in contract.criteria:
        passed = report.passed(criterion.evidence_source)
        if passed is None:
            continue
        entries.append(
            CriterionEvidence(criterion_id=criterion.id, source=criterion.evidence_source, passed=passed)
        )
    return WorkEvidence(entries=tuple(entries)), context


def _matches(pattern: re.Pattern[str], value: Any, variable: str, expected: str) -> None:
    """Insist on the exact shape Actions produces, without repairing anything.

    No trimming and no case folding. A value carrying a newline or an
    abbreviated SHA is not what Actions set, so it is somebody's edit, and
    quietly accepting an edited revision defeats the binding.
    """
    if not isinstance(value, str) or not pattern.match(value):
        raise LawmanError(f"{variable} must be {expected}, not {value!r}")


def _read(path: str) -> bytes:
    try:
        with open(path, "rb") as handle:
            raw = handle.read(MAXIMUM_REPORT_BYTES + 1)
    except OSError as error:
        raise LawmanError(f"cannot read the JUnit report {path}: {_reason(error)}") from error
    if len(raw) > MAXIMUM_REPORT_BYTES:
        raise LawmanError(f"the JUnit report {path} is larger than {MAXIMUM_REPORT_BYTES} bytes")
    return raw


def _parse(raw: bytes, path: str) -> ElementTree.Element:
    """Parse XML, or refuse. Not every unreadable document is a parse error.

    A declared encoding Python has no codec for raises `LookupError`, which is
    neither a `ParseError` nor a `ValueError` — and JVM and .NET runners write
    charset names (`x-MacRoman`, `x-windows-949`) that Python does not have. A
    document nested deeper than the stack raises `RecursionError`. Both are
    reachable from a report Lawman did not write, and an unhandled one is a
    traceback and exit 1 — which is a verdict, not the refusal this is.
    """
    try:
        return ElementTree.fromstring(raw)
    except (ElementTree.ParseError, LookupError, ValueError, RecursionError) as error:
        raise LawmanError(f"{path} is not a readable JUnit report: {_reason(error)}") from error


def _case(element: ElementTree.Element, path: str) -> JUnitCase:
    """One case, read verbatim. A failure outranks a skip; nothing outranks either.

    JUnit says a passing case by saying nothing: no `<failure>`, `<error>`, or
    `<skipped>` child. So an unrecognized child is not refused — `<system-out>`,
    `<system-err>`, and `<properties>` are ordinary, and refusing them would
    reject most real reports. Only direct children are read, which is where
    every runner in the guide puts them; a failure buried inside a wrapper
    element reads as a pass, and that is the known edge of this reading.
    """
    name = element.get("name")
    if not isinstance(name, str) or not name:
        raise LawmanError(f"{path} has a <{CASE_TAG}> with no name; a test nobody can name proves nothing")
    outcome: Outcome = "passed"
    if any(child.tag in FAILURE_TAGS for child in element):
        outcome = "failed"
    elif any(child.tag == SKIPPED_TAG for child in element):
        outcome = "skipped"
    return JUnitCase(classname=element.get("classname") or "", name=name, outcome=outcome)


def _reason(error: Exception) -> str:
    """Say why, in one line. A governance diagnostic is not a stack of detail."""
    detail = getattr(error, "strerror", None) or str(error)
    lines = [line.strip() for line in str(detail).strip().splitlines() if line.strip()]
    return lines[0] if lines else type(error).__name__

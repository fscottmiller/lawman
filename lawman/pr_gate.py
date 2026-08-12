"""Run Lawman's narrow pull-request gate.

The revision under test runs the canonical suite once. Only afterwards is the
pinned evaluator fetched, verified, and run from its own checkout. This
resists ordinary evaluator substitution, not hostile code on the same runner.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .decision import LawmanError
from .github import TOKEN_VARIABLE, IssueReference

EVALUATOR_SHA = "0b59edbe91b5cb5e1be8d7fd14fd4244ec9b2fe1"
EVALUATOR_ORIGIN = "https://github.com/fscottmiller/lawman.git"
SUITE_ARGUMENTS = ("-m", "unittest", "discover", "-s", "tests")
REPORT_VARIABLE = "LAWMAN_JUNIT_REPORT"
EVENT_NAME_VARIABLE = "GITHUB_EVENT_NAME"
EVENT_PATH_VARIABLE = "GITHUB_EVENT_PATH"
REPOSITORY_VARIABLE = "GITHUB_REPOSITORY"
REVISION_VARIABLE = "GITHUB_SHA"
RUNNER_TEMP_VARIABLE = "RUNNER_TEMP"
STATE_DIRECTORY = "lawman-pr-gate"
REPORT_NAME = "junit.xml"
EVALUATOR_DIRECTORY = "evaluator"

_MARKER = re.compile(r"\ACloses #([1-9][0-9]*)\Z")
_PYTHON_BOOTSTRAP = (
    "import runpy,sys; root=sys.argv.pop(1); sys.path.insert(0, root); "
    "runpy.run_module('lawman', run_name='__main__')"
)
Runner = Callable[..., subprocess.CompletedProcess[str]]


def governing_issue() -> str:
    """Select exactly one issue from exact, standalone PR-body markers."""
    if os.environ.get(EVENT_NAME_VARIABLE) != "pull_request":
        raise LawmanError(f"{EVENT_NAME_VARIABLE} must be 'pull_request'")
    path = os.environ.get(EVENT_PATH_VARIABLE, "")
    if not path:
        raise LawmanError(f"{EVENT_PATH_VARIABLE} must name the pull request event payload")
    payload = _event(path)
    pull_request = payload.get("pull_request")
    if not isinstance(pull_request, Mapping):
        raise LawmanError("the GitHub event payload has no pull_request object")
    body: Any = pull_request.get("body")
    if body is None:
        body = ""
    if not isinstance(body, str):
        raise LawmanError("the GitHub event payload has no readable pull request body")
    numbers = [int(match.group(1)) for line in body.splitlines() if (match := _MARKER.match(line))]
    if len(numbers) != 1:
        raise LawmanError(
            f"the pull request body has {len(numbers)} exact 'Closes #N' governing markers; exactly one is required"
        )
    repository = os.environ.get(REPOSITORY_VARIABLE, "")
    names = repository.split("/")
    if len(names) != 2:
        raise LawmanError(f"{REPOSITORY_VARIABLE} must be an owner/repository pair, not {repository!r}")
    return IssueReference(owner=names[0], repository=names[1], number=numbers[0]).url


def run_gate(runner: Runner | None = None) -> int:
    """Run the suite, fetch the evaluator, and combine both outcomes."""
    process = subprocess.run if runner is None else runner
    issue_url = governing_issue()
    state = _fresh_state()
    report = (state / REPORT_NAME).resolve()
    suite_exit = _run_suite(process, report)
    print(f"lawman gate: canonical suite exit {suite_exit}", file=sys.stderr)
    evaluator = _checkout_evaluator(process, state)
    outcome = _run_evaluator(process, evaluator, issue_url, report)
    _emit(outcome)
    return _combine(suite_exit, outcome, issue_url)


def main() -> int:
    try:
        return run_gate()
    except LawmanError as error:
        print(f"lawman gate: refused: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("lawman gate: refused: interrupted before a gate result was reached", file=sys.stderr)
        return 2


def _event(path: str) -> Mapping[str, Any]:
    try:
        raw = Path(path).read_text(encoding="utf-8")
        payload: Any = json.loads(raw)
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        raise LawmanError(f"cannot read the pull request event payload {path!r}: {_reason(error)}") from error
    if not isinstance(payload, Mapping):
        raise LawmanError("the GitHub event payload must be a JSON object")
    return payload


def _fresh_state() -> Path:
    parent = os.environ.get(RUNNER_TEMP_VARIABLE, "")
    if not parent or not Path(parent).is_absolute():
        raise LawmanError(f"{RUNNER_TEMP_VARIABLE} must be an absolute runner-owned directory")
    state = Path(parent) / STATE_DIRECTORY
    try:
        if state.is_symlink() or state.is_file():
            state.unlink()
        elif state.exists():
            shutil.rmtree(state)
        state.mkdir(parents=True)
    except OSError as error:
        raise LawmanError(f"cannot prepare gate state {str(state)!r}: {_reason(error)}") from error
    return state


def _run_suite(runner: Runner, report: Path) -> int:
    adapter = (Path(__file__).resolve().parent / "_junit_adapter").resolve()
    revision = Path.cwd().resolve()
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join((str(adapter), str(revision)))
    environment["PYTHONSAFEPATH"] = "1"
    environment[REPORT_VARIABLE] = str(report)
    environment.pop(TOKEN_VARIABLE, None)
    command = (str(Path(sys.executable).absolute()), *SUITE_ARGUMENTS)
    try:
        completed = runner(command, cwd=revision, env=environment, check=False)
    except OSError as error:
        raise LawmanError(f"cannot run the canonical suite: {_reason(error)}") from error
    return int(completed.returncode)


def _checkout_evaluator(runner: Runner, state: Path) -> Path:
    checkout = (state / EVALUATOR_DIRECTORY).resolve()
    try:
        checkout.mkdir()
    except OSError as error:
        raise LawmanError(f"cannot prepare the evaluator checkout: {_reason(error)}") from error
    environment = _git_environment(state)
    commands: tuple[tuple[str, ...], ...] = (
        ("git", "init", "--quiet"),
        ("git", "remote", "add", "origin", EVALUATOR_ORIGIN),
        ("git", "fetch", "--quiet", "--depth=1", "origin", EVALUATOR_SHA),
        ("git", "checkout", "--quiet", "--detach", "FETCH_HEAD"),
    )
    for command in commands:
        _checked(runner, command, checkout, environment)
    head = _checked(runner, ("git", "rev-parse", "HEAD"), checkout, environment)
    if head.stdout.splitlines() != [EVALUATOR_SHA]:
        raise LawmanError(f"the evaluator checkout HEAD is not the pinned revision {EVALUATOR_SHA}")
    print(f"lawman gate: evaluator revision {EVALUATOR_SHA} verified", file=sys.stderr)
    return checkout


def _git_environment(state: Path) -> dict[str, str]:
    token = os.environ.get(TOKEN_VARIABLE, "")
    if not token or token != token.strip() or not all(" " < character <= "~" for character in token):
        raise LawmanError(f"{TOKEN_VARIABLE} must be a usable Actions credential")
    askpass = state / "git-askpass.py"
    try:
        askpass.write_text(
            f"#!{Path(sys.executable).absolute()}\n"
            "import os, sys\n"
            "prompt = sys.argv[1] if len(sys.argv) > 1 else ''\n"
            "print('x-access-token' if 'Username' in prompt else os.environ['LAWMAN_GIT_TOKEN'])\n",
            encoding="utf-8",
        )
        askpass.chmod(0o700)
    except OSError as error:
        raise LawmanError(f"cannot prepare the evaluator checkout credential helper: {_reason(error)}") from error
    environment = dict(os.environ)
    environment.update(
        {"GIT_ASKPASS": str(askpass), "GIT_TERMINAL_PROMPT": "0", "LAWMAN_GIT_TOKEN": token}
    )
    return environment


def _checked(
    runner: Runner,
    command: Sequence[str],
    cwd: Path,
    environment: Mapping[str, str],
) -> subprocess.CompletedProcess[str]:
    try:
        completed = runner(
            tuple(command), cwd=cwd, env=dict(environment), check=False, capture_output=True, text=True
        )
    except OSError as error:
        raise LawmanError(f"cannot run the evaluator checkout command: {_reason(error)}") from error
    if completed.returncode != 0:
        raise LawmanError(f"evaluator checkout command failed: {_reason_text(completed.stderr)}")
    return completed


def _run_evaluator(
    runner: Runner,
    evaluator: Path,
    issue_url: str,
    report: Path,
) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    for name in tuple(environment):
        if name.startswith("PYTHON") or name in {"VIRTUAL_ENV", "__PYVENV_LAUNCHER__", "LAWMAN_GIT_TOKEN"}:
            environment.pop(name, None)
    command = (
        str(Path(sys.executable).absolute()),
        "-I",
        "-c",
        _PYTHON_BOOTSTRAP,
        str(evaluator),
        "work",
        "--issue",
        issue_url,
        "--junit",
        str(report),
    )
    try:
        return runner(
            command, cwd=evaluator, env=environment, check=False, capture_output=True, text=True
        )
    except OSError as error:
        raise LawmanError(f"cannot run the pinned evaluator: {_reason(error)}") from error


def _emit(outcome: subprocess.CompletedProcess[str]) -> None:
    if outcome.stdout:
        print(outcome.stdout, end="")
    if outcome.stderr:
        print(outcome.stderr, end="", file=sys.stderr)


def _combine(suite_exit: int, outcome: subprocess.CompletedProcess[str], issue_url: str) -> int:
    if outcome.returncode == 2:
        print("lawman gate: evaluation refused (Lawman exit 2)", file=sys.stderr)
        return 2
    if outcome.returncode not in (0, 1):
        print(f"lawman gate: evaluation refused (unexpected Lawman exit {outcome.returncode})", file=sys.stderr)
        return 2
    try:
        document: Any = json.loads(outcome.stdout)
    except (ValueError, RecursionError) as error:
        print(f"lawman gate: evaluation refused (unreadable Lawman result: {_reason(error)})", file=sys.stderr)
        return 2
    if not isinstance(document, Mapping):
        print("lawman gate: evaluation refused (Lawman result is not an object)", file=sys.stderr)
        return 2
    expected_satisfied = outcome.returncode == 0
    if document.get("satisfied") is not expected_satisfied:
        print("lawman gate: evaluation refused (Lawman exit contradicts its result)", file=sys.stderr)
        return 2
    execution = document.get("execution")
    revision = execution.get("revision") if isinstance(execution, Mapping) else None
    if revision != os.environ.get(REVISION_VARIABLE):
        print("lawman gate: evaluation refused (Lawman result does not name GITHUB_SHA)", file=sys.stderr)
        return 2
    source = document.get("contract_source")
    source_url = source.get("url") if isinstance(source, Mapping) else None
    if source_url != issue_url:
        print("lawman gate: evaluation refused (Lawman result does not name the governing issue)", file=sys.stderr)
        return 2
    if outcome.returncode == 1:
        print("lawman gate: work contract unsatisfied (Lawman exit 1)", file=sys.stderr)
        return 1
    if suite_exit != 0:
        print(f"lawman gate: canonical suite failed (exit {suite_exit})", file=sys.stderr)
        return 1
    print("lawman gate: work contract satisfied and canonical suite passed", file=sys.stderr)
    return 0


def _reason(error: BaseException) -> str:
    detail = getattr(error, "strerror", None) or str(error)
    return _reason_text(str(detail))


def _reason_text(detail: str | None) -> str:
    lines = [line.strip() for line in str(detail or "").splitlines() if line.strip()]
    return lines[0] if lines else "unknown error"


if __name__ == "__main__":
    sys.exit(main())

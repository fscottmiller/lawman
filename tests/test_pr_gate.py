"""Behavioral evidence for the self-governing pull-request gate."""

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

from lawman.ci import JUnitReport
from lawman.decision import LawmanError
from lawman.pr_gate import (
    EVALUATOR_DIRECTORY,
    EVALUATOR_ORIGIN,
    EVALUATOR_SHA,
    EVENT_NAME_VARIABLE,
    EVENT_PATH_VARIABLE,
    REPORT_NAME,
    REPORT_VARIABLE,
    REPOSITORY_VARIABLE,
    REVISION_VARIABLE,
    RUNNER_TEMP_VARIABLE,
    STATE_DIRECTORY,
    SUITE_ARGUMENTS,
    run_gate,
)

ROOT = Path(__file__).resolve().parent.parent
REVISION = "1234567890abcdef1234567890abcdef12345678"
ISSUE_URL = "https://github.com/fscottmiller/lawman/issues/18"


class FakeProcesses:
    """A runner boundary that behaves like unittest, git, and pinned Lawman."""

    def __init__(
        self,
        suite_exit=0,
        lawman_exit=0,
        checkout_sha=EVALUATOR_SHA,
        result_satisfied=None,
        result_revision=REVISION,
    ):
        self.suite_exit = suite_exit
        self.lawman_exit = lawman_exit
        self.checkout_sha = checkout_sha
        self.result_satisfied = lawman_exit == 0 if result_satisfied is None else result_satisfied
        self.result_revision = result_revision
        self.calls = []
        self.preexisting_report = None
        self.evaluated_report = None

    def __call__(self, arguments, **options):
        command = tuple(str(item) for item in arguments)
        call = {
            "command": command,
            "cwd": Path(options["cwd"]),
            "env": dict(options["env"]),
            "capture_output": options.get("capture_output", False),
        }
        self.calls.append(call)
        if command[1:] == SUITE_ARGUMENTS:
            report = Path(call["env"][REPORT_VARIABLE])
            self.preexisting_report = report.exists()
            report.write_text(
                '<testsuites><testcase classname="Gate" name="test_required"/></testsuites>',
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, self.suite_exit, "", "")
        if command[:3] == ("git", "rev-parse", "HEAD"):
            return subprocess.CompletedProcess(command, 0, f"{self.checkout_sha}\n", "")
        if command[0] == "git":
            return subprocess.CompletedProcess(command, 0, "", "")
        if len(command) > 2 and command[1:3] == ("-I", "-c"):
            issue = command[command.index("--issue") + 1]
            report = Path(command[command.index("--junit") + 1])
            self.evaluated_report = report.read_text(encoding="utf-8")
            if self.lawman_exit == 2:
                return subprocess.CompletedProcess(command, 2, "", "lawman: refused evidence\n")
            document = {
                "contract_source": {"url": issue},
                "execution": {"revision": self.result_revision},
                "satisfied": self.result_satisfied,
                "criteria": [],
            }
            return subprocess.CompletedProcess(command, self.lawman_exit, json.dumps(document) + "\n", "")
        raise AssertionError(f"unexpected command: {command}")


class GateTest(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.runner_temp = self.directory / "runner"
        self.runner_temp.mkdir()
        self.event = self.directory / "event.json"

    def environment(self, body="Closes #18", repository="fscottmiller/lawman"):
        self.event.write_text(json.dumps({"pull_request": {"body": body}}), encoding="utf-8")
        return {
            EVENT_NAME_VARIABLE: "pull_request",
            EVENT_PATH_VARIABLE: str(self.event),
            REPOSITORY_VARIABLE: repository,
            REVISION_VARIABLE: REVISION,
            RUNNER_TEMP_VARIABLE: str(self.runner_temp),
            "GITHUB_ACTIONS": "true",
            "GITHUB_RUN_ID": "42",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_TOKEN": "test-token",
            "PYTHONPATH": "/revision-under-test",
            "PYTHONHOME": "/untrusted-python",
            "PYTHONUSERBASE": "/untrusted-user",
            "PYTHONSTARTUP": "/untrusted-startup.py",
            "VIRTUAL_ENV": "/untrusted-venv",
        }

    def execute(self, fake, body="Closes #18", repository="fscottmiller/lawman"):
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, self.environment(body, repository), clear=True):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = run_gate(fake)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def evaluator_call(self, fake):
        return next(call for call in fake.calls if call["command"][1:3] == ("-I", "-c"))

    def suite_calls(self, fake):
        return [call for call in fake.calls if call["command"][1:] == SUITE_ARGUMENTS]

    def test_governing_issue_requires_one_exact_closes_marker(self):
        """AC1. Exactly one exact line selects the canonical issue; everything near it is ignored."""
        fake = FakeProcesses()
        body = (
            "Closes #0\nCloses #18.\n Closes #18\ntext Closes #18\n"
            "Closes  #18\nFixes #18\nCloses #0018\nCloses #18\r\n"
        )
        exit_code, _, _ = self.execute(fake, body=body, repository="owner-name/repo.name")

        self.assertEqual(exit_code, 0)
        evaluator = self.evaluator_call(fake)["command"]
        self.assertIn("https://github.com/owner-name/repo.name/issues/18", evaluator)

        invalid = {
            "no marker": "Issue 18",
            "only malformed markers": "Closes #0\nCloses #-1\nCloses #18.",
            "two exact markers": "Closes #18\nprose\nCloses #19",
            "a missing body": None,
        }
        for situation, candidate in invalid.items():
            with self.subTest(situation=situation):
                stopped = FakeProcesses()
                environment = self.environment(candidate)
                with mock.patch.dict(os.environ, environment, clear=True):
                    with self.assertRaises(LawmanError):
                        run_gate(stopped)
                self.assertEqual(stopped.calls, [], "selection must fail before suite or Lawman execution")

        self.event.write_text("{not json", encoding="utf-8")
        environment = self.environment()
        self.event.write_text("{not json", encoding="utf-8")
        with mock.patch.dict(os.environ, environment, clear=True), self.assertRaises(LawmanError):
            run_gate(FakeProcesses())

    def test_pr_gate_runs_suite_once_then_verifies_same_junit(self):
        """AC2. One exact suite execution creates the only report the evaluator receives."""
        forged = self.runner_temp / STATE_DIRECTORY / REPORT_NAME
        forged.parent.mkdir()
        forged.write_text("caller-authored", encoding="utf-8")
        fake = FakeProcesses()

        exit_code, stdout, _ = self.execute(fake)

        self.assertEqual(exit_code, 0)
        suites = self.suite_calls(fake)
        self.assertEqual(len(suites), 1)
        self.assertEqual(suites[0]["command"], (str(Path(sys.executable).absolute()), *SUITE_ARGUMENTS))
        self.assertNotIn("GITHUB_TOKEN", suites[0]["env"])
        self.assertFalse(fake.preexisting_report, "the designated report must start fresh")
        report = Path(suites[0]["env"][REPORT_VARIABLE])
        evaluator = self.evaluator_call(fake)["command"]
        self.assertEqual(Path(evaluator[evaluator.index("--junit") + 1]), report)
        self.assertEqual(fake.evaluated_report, report.read_text(encoding="utf-8"))
        self.assertNotIn("--evidence", evaluator)
        self.assertNotIn("--revision", evaluator)
        self.assertNotIn(REVISION, evaluator)
        self.assertEqual(json.loads(stdout)["execution"]["revision"], REVISION)
        self.assertTrue(report.is_file(), "the report remains available after evaluation")

        commands = [call["command"] for call in fake.calls]
        suite_index = commands.index(suites[0]["command"])
        evaluator_index = commands.index(evaluator)
        self.assertLess(suite_index, evaluator_index)

    def test_pr_gate_runs_pinned_lawman_outside_revision_under_test(self):
        """AC3. Checkout follows the suite, verifies the pin, and isolates Python import resolution."""
        fake = FakeProcesses()
        exit_code, _, _ = self.execute(fake)

        self.assertEqual(exit_code, 0)
        commands = [call["command"] for call in fake.calls]
        fetch = ("git", "fetch", "--quiet", "--depth=1", "origin", EVALUATOR_SHA)
        self.assertIn(("git", "remote", "add", "origin", EVALUATOR_ORIGIN), commands)
        self.assertIn(fetch, commands)
        self.assertLess(commands.index(self.suite_calls(fake)[0]["command"]), commands.index(fetch))
        self.assertLess(commands.index(fetch), commands.index(("git", "rev-parse", "HEAD")))

        evaluator = self.evaluator_call(fake)
        checkout = (self.runner_temp / STATE_DIRECTORY / EVALUATOR_DIRECTORY).resolve()
        self.assertEqual(evaluator["cwd"], checkout)
        self.assertEqual(Path(evaluator["command"][4]), checkout)
        self.assertEqual(evaluator["command"][1], "-I")
        self.assertTrue(Path(evaluator["command"][-1]).is_absolute())
        for name in evaluator["env"]:
            self.assertFalse(name.startswith("PYTHON"), name)
        self.assertNotIn("VIRTUAL_ENV", evaluator["env"])
        self.assertEqual(evaluator["env"]["GITHUB_TOKEN"], "test-token")

        wrong = FakeProcesses(checkout_sha="f" * 40)
        with mock.patch.dict(os.environ, self.environment(), clear=True):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(LawmanError):
                run_gate(wrong)
        self.assertFalse(
            any(call["command"][1:3] == ("-I", "-c") for call in wrong.calls),
            "a mismatched evaluator must never execute",
        )

    def test_pr_gate_propagates_satisfied_unsatisfied_and_refused_outcomes(self):
        """AC4. Only suite 0 plus a satisfied Lawman 0 is green; every other named outcome is red."""
        cases = (
            ("both pass", 0, 0, 0, "work contract satisfied and canonical suite passed"),
            ("unrelated suite failure", 7, 0, 1, "canonical suite failed (exit 7)"),
            ("unsatisfied work", 0, 1, 1, "work contract unsatisfied (Lawman exit 1)"),
            ("refused evaluation", 0, 2, 2, "evaluation refused (Lawman exit 2)"),
            ("suite failure and unsatisfied work", 9, 1, 1, "work contract unsatisfied (Lawman exit 1)"),
        )
        for situation, suite_exit, lawman_exit, expected, message in cases:
            with self.subTest(situation=situation):
                fake = FakeProcesses(suite_exit=suite_exit, lawman_exit=lawman_exit)
                exit_code, _, stderr = self.execute(fake)
                self.assertEqual(exit_code, expected)
                self.assertIn(f"canonical suite exit {suite_exit}", stderr)
                self.assertIn(message, stderr)
                self.assertIsNotNone(fake.evaluated_report, "a readable failing report must still reach Lawman")

        contradiction = FakeProcesses(lawman_exit=0, result_satisfied=False)
        exit_code, _, stderr = self.execute(contradiction)
        self.assertEqual(exit_code, 2)
        self.assertIn("Lawman exit contradicts its result", stderr)

        missing_revision = FakeProcesses(result_revision=None)
        environment = self.environment()
        environment.pop(REVISION_VARIABLE)
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, environment, clear=True):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = run_gate(missing_revision)
        self.assertEqual(exit_code, 2)
        self.assertIn("Lawman result does not name GITHUB_SHA", stderr.getvalue())


class JUnitAdapterTest(unittest.TestCase):
    def test_adapter_preserves_a_report_when_unittest_fails(self):
        """The real adapter leaves readable pass/fail identities after the exact command."""
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            tests = directory / "tests"
            tests.mkdir()
            (tests / "test_sample.py").write_text(
                "import unittest\n"
                "class Sample(unittest.TestCase):\n"
                "    def test_passes(self): self.assertTrue(True)\n"
                "    def test_fails(self): self.assertTrue(False)\n",
                encoding="utf-8",
            )
            report = directory / REPORT_NAME
            environment = dict(os.environ)
            environment.update(
                {
                    "PYTHONPATH": str((ROOT / "lawman" / "_junit_adapter").resolve()),
                    "PYTHONSAFEPATH": "1",
                    REPORT_VARIABLE: str(report),
                }
            )
            result = subprocess.run(
                (str(Path(sys.executable).absolute()), *SUITE_ARGUMENTS),
                cwd=directory,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(report.is_file(), result.stderr)
            parsed = JUnitReport.from_path(str(report))
            outcomes = {case.name: case.outcome for case in parsed.cases}
            self.assertEqual(outcomes, {"test_fails": "failed", "test_passes": "passed"})


if __name__ == "__main__":
    unittest.main()

"""The CLI is the only interface, so it is tested the way it is used.

Lawman's own half of the transition contract — exit codes, output bytes, and
what the caller may say — is pinned here with a stand-in OPA, so it holds
whatever a policy decides. `tests/test_opa.py` runs the real one.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import fake_opa

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "deploy-to-production"
WORK_EXAMPLE = ROOT / "examples" / "work-contract"
POLICY = ROOT / ".lawman" / "policies" / "deploy-production.rego"

ALLOWED = {"allowed": True, "reasons": ["Tests passed.", "A human approved this deploy."]}
DENIED = {
    "allowed": False,
    "reasons": ["Tests did not pass.", "The change window is closed.", "No human approval was presented."],
}


def run(*argv, cwd=ROOT, path=None):
    """Run Lawman as a governed repository would: from the repository root.

    `cwd` is the repository being governed. Lawman itself stays importable from
    anywhere, so a test can govern a temporary repository without installing.
    `path` replaces PATH, which is how a test chooses the `opa` Lawman finds.
    """
    return subprocess.run(
        [sys.executable, "-m", "lawman", *[str(argument) for argument in argv]],
        cwd=cwd,
        env={**os.environ, "PYTHONPATH": str(ROOT), **({} if path is None else {"PATH": path})},
        capture_output=True,
        text=True,
    )


def transition(intent=EXAMPLE / "intent.json", evidence=EXAMPLE / "evidence.json", cwd=ROOT, path=None, extra=()):
    return run("--intent", intent, "--evidence", evidence, *extra, cwd=cwd, path=path)


def write(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document if isinstance(document, str) else json.dumps(document), encoding="utf-8")
    return path


class ReportsWhatThePolicyDecided(unittest.TestCase):
    def test_opa_allow_returns_decision_and_exit_0(self):
        """AC4. A defined allow is a decision on stdout and exit 0."""
        with tempfile.TemporaryDirectory() as directory:
            result = transition(path=fake_opa.deciding(directory, ALLOWED))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(
            result.stdout,
            json.dumps(
                {
                    "allowed": True,
                    "intent": {"action": "deploy", "target": "production"},
                    "reasons": ["Tests passed.", "A human approved this deploy."],
                },
                indent=2,
            )
            + "\n",
        )

    def test_opa_deny_returns_ordered_reasons_and_exit_1(self):
        """AC5. A defined deny reports every reason, in policy order, and exits 1."""
        with tempfile.TemporaryDirectory() as directory:
            result = transition(path=fake_opa.deciding(directory, DENIED))

        self.assertEqual(result.returncode, 1)
        decision = json.loads(result.stdout)
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["reasons"], DENIED["reasons"])
        self.assertEqual(decision["intent"], {"action": "deploy", "target": "production"})

    def test_transition_output_is_byte_identical_across_runs(self):
        """AC11. Same intent, evidence, policy, and OPA output: same bytes."""
        with tempfile.TemporaryDirectory() as directory:
            path = fake_opa.deciding(directory, DENIED)
            runs = [transition(path=path) for _ in range(3)]

        self.assertEqual({result.stdout for result in runs}, {runs[0].stdout})
        self.assertEqual({result.returncode for result in runs}, {1})
        self.assertEqual(json.loads(runs[0].stdout)["reasons"], DENIED["reasons"])


class TheCallerCannotChooseTheRules(unittest.TestCase):
    """The requester picks what it wants to do, not the rules it is judged by."""

    def test_the_caller_cannot_choose_policy_or_query(self):
        """AC9. No flag names a policy, a contract, data, or a query."""
        with tempfile.TemporaryDirectory() as directory:
            weaker = write(Path(directory) / "weak.rego", "package lawman\n")
            path = fake_opa.deciding(directory, ALLOWED)
            for flag, value in (
                ("--policy", weaker),
                ("--contract", weaker),
                ("--data", weaker),
                ("--query", "data.weak.decision"),
                ("--package", "weak"),
                ("--input", weaker),
            ):
                with self.subTest(flag=flag):
                    result = transition(path=path, extra=(flag, str(value)))
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, "")
                    self.assertIn("unrecognized arguments", result.stderr)

            help_text = run("--help").stdout
            self.assertNotIn("--policy", help_text)
            self.assertNotIn("--contract", help_text)
            self.assertNotIn("--query", help_text)
            self.assertIn("lawman work --help", help_text)

            # A policy sitting beside the requester's own files does not
            # govern: OPA is handed the repository's policy, and nothing else.
            record = Path(directory) / "received.json"
            transition(
                intent=write(Path(directory) / "intent.json", {"action": "deploy", "target": "production"}),
                evidence=write(Path(directory) / "evidence.json", {"tests_passed": True}),
                path=fake_opa.deciding(directory, ALLOWED, record=record),
            )
            argv = json.loads(record.read_text(encoding="utf-8"))["argv"]

        self.assertIn(str(POLICY), argv)
        self.assertNotIn(str(weaker), argv)
        self.assertIn("data.lawman.decision", argv)


class FailsClosedWhenItCannotFindTheRules(unittest.TestCase):
    """Exit 2, not exit 1. Lawman did not reach a verdict; it could not."""

    def test_an_intent_with_no_configured_policy_exits_2(self):
        with tempfile.TemporaryDirectory() as directory:
            result = transition(intent=write(Path(directory) / "intent.json", {"action": "deploy", "target": "qa"}))

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("no policy is configured for deploy -> qa", result.stderr)

    def test_a_repository_with_no_policy_directory_exits_2(self):
        with tempfile.TemporaryDirectory() as directory:
            result = transition(cwd=directory)

        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot read policy registry", result.stderr)


class RefusesToGuess(unittest.TestCase):
    def test_unreadable_input_exits_2_and_explains(self):
        result = transition(evidence=EXAMPLE / "nope.json")

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("cannot read evidence", result.stderr)

    def test_invalid_json_exits_2_and_explains(self):
        with tempfile.TemporaryDirectory() as directory:
            result = transition(evidence=write(Path(directory) / "evidence.json", "{ not json"))

        self.assertEqual(result.returncode, 2)
        self.assertIn("not valid JSON", result.stderr)

    def test_evidence_that_is_not_an_object_exits_2_and_explains(self):
        with tempfile.TemporaryDirectory() as directory:
            result = transition(evidence=write(Path(directory) / "evidence.json", ["tests_passed"]))

        self.assertEqual(result.returncode, 2)
        self.assertIn("evidence must be an object", result.stderr)

    def test_a_malformed_intent_is_refused_before_a_policy_is_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            result = transition(intent=write(Path(directory) / "intent.json", {"action": "deploy"}))

        self.assertEqual(result.returncode, 2)
        self.assertIn("intent.target", result.stderr)


class TheWorkCommandIsUntouched(unittest.TestCase):
    def test_work_contract_command_remains_unchanged(self):
        """AC12. Same command, same schema, same exit codes — and no OPA."""
        with tempfile.TemporaryDirectory() as directory:
            without_opa = fake_opa.missing(directory)
            satisfied = run(
                "work",
                "--contract",
                WORK_EXAMPLE / "contract.json",
                "--evidence",
                WORK_EXAMPLE / "evidence.json",
                path=without_opa,
            )
            unsatisfied = run(
                "work",
                "--contract",
                WORK_EXAMPLE / "contract.json",
                "--evidence",
                WORK_EXAMPLE / "evidence-missing-audit.json",
                path=without_opa,
            )
            refused = run(
                "work",
                "--contract",
                WORK_EXAMPLE / "contract.json",
                "--evidence",
                write(Path(directory) / "evidence.json", {"evidence": "AC1"}),
                path=without_opa,
            )

        self.assertEqual(satisfied.returncode, 0, satisfied.stderr)
        result = json.loads(satisfied.stdout)
        self.assertTrue(result["satisfied"])
        self.assertEqual(
            set(result["criteria"][0]), {"id", "description", "status", "source", "explanation"}
        )
        self.assertEqual(result["criteria"][0]["status"], "proven")

        self.assertEqual(unsatisfied.returncode, 1)
        self.assertFalse(json.loads(unsatisfied.stdout)["satisfied"])

        self.assertEqual(refused.returncode, 2)
        self.assertEqual(refused.stdout, "")


if __name__ == "__main__":
    unittest.main()

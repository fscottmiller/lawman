"""The CLI is the only interface, so it is tested the way it is used."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "deploy-to-production"


def run(intent=EXAMPLE / "intent.json", evidence=EXAMPLE / "evidence.json", cwd=ROOT, extra=()):
    """Run Lawman as a governed repository would: from the repository root.

    `cwd` is the repository being governed. Lawman itself stays importable from
    anywhere, so a test can govern a temporary repository without installing.
    """
    return subprocess.run(
        [sys.executable, "-m", "lawman", "--intent", str(intent), "--evidence", str(evidence), *extra],
        cwd=cwd,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
    )


def write(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document if isinstance(document, str) else json.dumps(document), encoding="utf-8")
    return path


def governed_repository(directory, registry, contracts=()):
    """A directory with a policy directory in it, ready to be run from."""
    repository = Path(directory)
    write(repository / ".lawman" / "contracts.json", registry)
    for relative, contract in dict(contracts).items():
        write(repository / ".lawman" / relative, contract)
    return repository


class CanonicalExample(unittest.TestCase):
    def test_readme_command_allows_the_deploy(self):
        result = run()

        self.assertEqual(result.returncode, 0, result.stderr)
        decision = json.loads(result.stdout)
        self.assertTrue(decision["allowed"])
        self.assertEqual(decision["intent"], {"action": "deploy", "target": "production"})
        self.assertEqual(decision["satisfied"], ["tests_passed", "human_approved"])
        self.assertIn("Allowed", decision["explanation"])

    def test_failed_tests_deny_with_exit_code_1(self):
        result = run(evidence=EXAMPLE / "evidence-tests-failed.json")

        self.assertEqual(result.returncode, 1)
        decision = json.loads(result.stdout)
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["failed"], ["tests_passed"])

    def test_missing_evidence_denies_with_exit_code_1(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run(evidence=write(Path(directory) / "evidence.json", {"tests_passed": True}))

        self.assertEqual(result.returncode, 1)
        decision = json.loads(result.stdout)
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["unproven"], ["human_approved"])

    def test_output_is_byte_identical_across_runs(self):
        first, second = run(), run()

        self.assertEqual(first.stdout, second.stdout)


class TheCallerCannotChooseTheContract(unittest.TestCase):
    """The requester picks what it wants to do, not the rules it is judged by."""

    def test_there_is_no_contract_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            weaker = write(Path(directory) / "weak.json", {"requires": ["tests_passed"]})
            result = run(extra=("--contract", str(weaker)))

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("unrecognized arguments", result.stderr)

    def test_a_weaker_contract_beside_the_intent_does_not_govern(self):
        with tempfile.TemporaryDirectory() as directory:
            requested = Path(directory)
            write(requested / "contract.json", {"requires": ["tests_passed"]})
            result = run(
                intent=write(requested / "intent.json", {"action": "deploy", "target": "production"}),
                evidence=write(requested / "evidence.json", {"tests_passed": True}),
            )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["unproven"], ["human_approved"])


class FailsClosedWhenItCannotFindTheRules(unittest.TestCase):
    """Exit 2, not exit 1. Lawman did not reach a verdict; it could not."""

    def test_an_intent_with_no_configured_contract_exits_2(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run(
                intent=write(Path(directory) / "intent.json", {"action": "deploy", "target": "staging"}),
            )

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("no contract is configured for deploy -> staging", result.stderr)

    def test_a_repository_with_no_policy_directory_exits_2(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run(cwd=directory)

        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot read contract registry", result.stderr)

    def test_a_malformed_registry_exits_2(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run(cwd=governed_repository(directory, "{ not json"))

        self.assertEqual(result.returncode, 2)
        self.assertIn("not valid JSON", result.stderr)

    def test_a_registry_that_is_not_nested_by_action_and_target_exits_2(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run(cwd=governed_repository(directory, {"deploy": "contracts/deploy-production.json"}))

        self.assertEqual(result.returncode, 2)
        self.assertIn("contract registry action 'deploy' must be an object", result.stderr)

    def test_a_configured_contract_that_is_missing_exits_2(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = governed_repository(directory, {"deploy": {"production": "contracts/deploy-production.json"}})
            result = run(cwd=repository)

        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot read contract for deploy -> production", result.stderr)

    def test_a_contract_outside_the_policy_directory_exits_2(self):
        with tempfile.TemporaryDirectory() as directory:
            write(Path(directory) / "weak.json", {"requires": ["tests_passed"]})
            repository = governed_repository(directory, {"deploy": {"production": "../weak.json"}})
            result = run(cwd=repository)

        self.assertEqual(result.returncode, 2)
        self.assertIn("outside the policy directory", result.stderr)


class RefusesToGuess(unittest.TestCase):
    def test_unreadable_input_exits_2_and_explains(self):
        result = run(evidence=EXAMPLE / "nope.json")

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("cannot read evidence", result.stderr)

    def test_invalid_json_exits_2_and_explains(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run(evidence=write(Path(directory) / "evidence.json", "{ not json"))

        self.assertEqual(result.returncode, 2)
        self.assertIn("not valid JSON", result.stderr)

    def test_non_boolean_evidence_exits_2_and_explains(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run(evidence=write(Path(directory) / "evidence.json", {"tests_passed": "yes"}))

        self.assertEqual(result.returncode, 2)
        self.assertIn("must be true or false", result.stderr)

    def test_a_malformed_intent_is_refused_before_a_contract_is_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run(intent=write(Path(directory) / "intent.json", {"action": "deploy"}))

        self.assertEqual(result.returncode, 2)
        self.assertIn("intent.target", result.stderr)


if __name__ == "__main__":
    unittest.main()

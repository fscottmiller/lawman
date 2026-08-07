"""The CLI is the only interface, so it is tested the way it is used."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "deploy-to-production"


def run(intent=EXAMPLE / "intent.json", contract=EXAMPLE / "contract.json", evidence=EXAMPLE / "evidence.json"):
    return subprocess.run(
        [sys.executable, "-m", "lawman", "--intent", str(intent), "--contract", str(contract), "--evidence", str(evidence)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def evidence_file(directory, facts):
    path = Path(directory) / "evidence.json"
    path.write_text(json.dumps(facts), encoding="utf-8")
    return path


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
            result = run(evidence=evidence_file(directory, {"tests_passed": True}))

        self.assertEqual(result.returncode, 1)
        decision = json.loads(result.stdout)
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["unproven"], ["human_approved"])

    def test_output_is_byte_identical_across_runs(self):
        first, second = run(), run()

        self.assertEqual(first.stdout, second.stdout)


class RefusesToGuess(unittest.TestCase):
    def test_unreadable_input_exits_2_and_explains(self):
        result = run(evidence=EXAMPLE / "nope.json")

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("cannot read evidence", result.stderr)

    def test_invalid_json_exits_2_and_explains(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            path.write_text("{ not json", encoding="utf-8")
            result = run(evidence=path)

        self.assertEqual(result.returncode, 2)
        self.assertIn("not valid JSON", result.stderr)

    def test_non_boolean_evidence_exits_2_and_explains(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run(evidence=evidence_file(directory, {"tests_passed": "yes"}))

        self.assertEqual(result.returncode, 2)
        self.assertIn("must be true or false", result.stderr)


if __name__ == "__main__":
    unittest.main()

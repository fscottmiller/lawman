"""The work-contract path is narrow, structured, and fail-closed."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "work-contract"


def run(contract=EXAMPLE / "contract.json", evidence=EXAMPLE / "evidence.json"):
    return subprocess.run(
        [sys.executable, "-m", "lawman", "work", "--contract", str(contract), "--evidence", str(evidence)],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
    )


class WorkContractCommand(unittest.TestCase):
    def test_the_canonical_work_contract_is_satisfied(self):
        result = run()

        self.assertEqual(result.returncode, 0, result.stderr)
        document = json.loads(result.stdout)
        self.assertTrue(document["satisfied"])
        self.assertEqual([item["id"] for item in document["criteria"]], ["AC1", "AC2", "AC3"])
        self.assertEqual([item["status"] for item in document["criteria"]], ["proven", "proven", "proven"])
        self.assertEqual(document["criteria"][0]["source"], "test_invalid_token")

    def test_missing_evidence_returns_an_explained_unsatisfied_result(self):
        result = run(evidence=EXAMPLE / "evidence-missing-audit.json")

        self.assertEqual(result.returncode, 1, result.stderr)
        document = json.loads(result.stdout)
        self.assertFalse(document["satisfied"])
        self.assertEqual(document["criteria"][2]["status"], "unproven")
        self.assertIn("no evidence", document["criteria"][2]["explanation"])

    def test_malformed_input_is_refused_with_exit_2(self):
        with tempfile.TemporaryDirectory() as directory:
            malformed = Path(directory) / "evidence.json"
            malformed.write_text('{"evidence": [{"criterion_id": "AC1"}]}', encoding="utf-8")
            result = run(evidence=malformed)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("work evidence", result.stderr)

    def test_output_is_byte_identical_across_runs(self):
        first, second = run(), run()

        self.assertEqual(first.stdout, second.stdout)

    def test_local_work_contract_command_remains_byte_identical(self):
        """AC10 of #8. A local contract reads exactly as it did before issues existed."""
        expected = json.dumps(
            {
                "satisfied": True,
                "criteria": [
                    {
                        "id": criterion_id,
                        "description": description,
                        "status": "proven",
                        "source": source,
                        "explanation": f"Proven by {source}.",
                    }
                    for criterion_id, description, source in (
                        ("AC1", "Invalid tokens return 401", "test_invalid_token"),
                        ("AC2", "Valid tokens return 200", "test_valid_token"),
                        (
                            "AC3",
                            "Authentication failures emit an audit event",
                            "test_authentication_audit_event",
                        ),
                    )
                ],
            },
            indent=2,
        )

        result = run()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, expected + "\n")

        # A local contract identifies itself, so nothing is added to say where
        # it came from. `contract_source` belongs to a GitHub-backed result.
        self.assertEqual(list(json.loads(result.stdout)), ["satisfied", "criteria"])
        self.assertNotIn("contract_source", result.stdout)

        unsatisfied = run(evidence=EXAMPLE / "evidence-missing-audit.json")

        self.assertEqual(unsatisfied.returncode, 1)
        self.assertEqual(list(json.loads(unsatisfied.stdout)), ["satisfied", "criteria"])


if __name__ == "__main__":
    unittest.main()

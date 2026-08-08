"""The work-contract path is narrow, structured, and fail-closed."""

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

from lawman.__main__ import main

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "work-contract"

BOUND = (
    ("AC1", "Invalid tokens return 401", "test_invalid_token"),
    ("AC2", "Valid tokens return 200", "test_valid_token"),
    ("AC3", "Authentication failures emit an audit event", "test_authentication_audit_event"),
)


def run(contract=EXAMPLE / "contract.json", evidence=EXAMPLE / "evidence.json"):
    return subprocess.run(
        [sys.executable, "-m", "lawman", "work", "--contract", str(contract), "--evidence", str(evidence)],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
    )


def evidence_file(directory, entries, name="evidence.json"):
    path = Path(directory) / name
    path.write_text(json.dumps({"evidence": entries}), encoding="utf-8")
    return path


class WorkContractCommand(unittest.TestCase):
    def test_the_canonical_work_contract_is_satisfied(self):
        result = run()

        self.assertEqual(result.returncode, 0, result.stderr)
        document = json.loads(result.stdout)
        self.assertTrue(document["satisfied"])
        self.assertEqual([item["id"] for item in document["criteria"]], ["AC1", "AC2", "AC3"])
        self.assertEqual([item["status"] for item in document["criteria"]], ["proven", "proven", "proven"])
        self.assertEqual(document["criteria"][0]["evidence_source"], "test_invalid_token")
        self.assertEqual(document["criteria"][0]["source"], "test_invalid_token")

    def test_missing_evidence_returns_an_explained_unsatisfied_result(self):
        result = run(evidence=EXAMPLE / "evidence-missing-audit.json")

        self.assertEqual(result.returncode, 1, result.stderr)
        document = json.loads(result.stdout)
        self.assertFalse(document["satisfied"])
        self.assertEqual(document["criteria"][2]["status"], "unproven")
        self.assertIn("no evidence from test_authentication_audit_event", document["criteria"][2]["explanation"])

    def test_malformed_input_is_refused_with_exit_2(self):
        with tempfile.TemporaryDirectory() as directory:
            malformed = Path(directory) / "evidence.json"
            malformed.write_text('{"evidence": [{"criterion_id": "AC1"}]}', encoding="utf-8")
            result = run(evidence=malformed)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("work evidence", result.stderr)

    def test_unknown_duplicate_or_misbound_evidence_is_refused(self):
        """AC6. Not a result: exit 2, nothing on stdout, one line on stderr."""
        refusals = {
            "an unknown criterion": (
                [{"criterion_id": "AC9", "source": "test_invalid_token", "passed": True}],
                "unknown criteria: AC9",
            ),
            "a repeated criterion": (
                [
                    {"criterion_id": "AC1", "source": "test_invalid_token", "passed": True},
                    {"criterion_id": "AC1", "source": "test_invalid_token", "passed": False},
                ],
                "must not repeat a criterion",
            ),
            "a source the contract did not bind": (
                [{"criterion_id": "AC1", "source": "test_something_convenient", "passed": True}],
                "AC1 requires test_invalid_token, not test_something_convenient",
            ),
            "another criterion's source": (
                [{"criterion_id": "AC1", "source": "test_valid_token", "passed": True}],
                "AC1 requires test_invalid_token, not test_valid_token",
            ),
        }
        with tempfile.TemporaryDirectory() as directory:
            results = {
                situation: run(evidence=evidence_file(directory, entries, name=f"{index}.json"))
                for index, (situation, (entries, _)) in enumerate(refusals.items())
            }
            # The repository-owned example of a misbound claim refuses too.
            results["the wrong-source example"] = run(evidence=EXAMPLE / "evidence-wrong-source.json")

        expected = {situation: complaint for situation, (_, complaint) in refusals.items()}
        expected["the wrong-source example"] = (
            "AC3 requires test_authentication_audit_event, not test_valid_token_again"
        )

        for situation, result in results.items():
            with self.subTest(situation=situation):
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertEqual(result.stdout, "")
                self.assertEqual(len(result.stderr.strip().splitlines()), 1, result.stderr)
                self.assertTrue(result.stderr.startswith("lawman: "), result.stderr)
                self.assertIn(expected[situation], result.stderr)

    def test_output_is_byte_identical_across_runs(self):
        first, second = run(), run()

        self.assertEqual(first.stdout, second.stdout)

    def test_binding_is_deterministic_and_transition_policy_is_untouched(self):
        """AC11. Same inputs, same bytes; and binding evidence reaches no policy."""
        runs = [run() for _ in range(3)]

        self.assertEqual({result.stdout for result in runs}, {runs[0].stdout})
        self.assertEqual({result.returncode for result in runs}, {0})

        # Exit semantics are unchanged: satisfied 0, unsatisfied 1, refused 2.
        self.assertEqual(run(evidence=EXAMPLE / "evidence-missing-audit.json").returncode, 1)
        self.assertEqual(run(evidence=EXAMPLE / "evidence-wrong-source.json").returncode, 2)

        # No policy is selected and no OPA is asked, on any of those outcomes.
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch("lawman.__main__.select_policy", side_effect=AssertionError("policy was selected")):
            with mock.patch("lawman.__main__.evaluate_policy", side_effect=AssertionError("OPA was asked")):
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    exits = [
                        main(["work", "--contract", str(EXAMPLE / "contract.json"), "--evidence", str(evidence)])
                        for evidence in (
                            EXAMPLE / "evidence.json",
                            EXAMPLE / "evidence-missing-audit.json",
                            EXAMPLE / "evidence-wrong-source.json",
                        )
                    ]

        self.assertEqual(exits, [0, 1, 2])

        # And the transition command's surface did not move: it takes no
        # contract, no evidence binding, and still names its own two arguments.
        transition_help = subprocess.run(
            [sys.executable, "-m", "lawman", "--help"],
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
            capture_output=True,
            text=True,
        ).stdout

        self.assertIn("--intent PATH", transition_help)
        self.assertIn("--evidence PATH", transition_help)
        for absent in ("--contract", "--issue", "--evidence-source", "--policy"):
            with self.subTest(absent=absent):
                self.assertNotIn(absent, transition_help)

    def test_local_work_contract_command_remains_byte_identical(self):
        """AC10 of #8, plus #12's additive field. The local result's exact bytes."""
        expected = json.dumps(
            {
                "satisfied": True,
                "criteria": [
                    {
                        "id": criterion_id,
                        "description": description,
                        "evidence_source": source,
                        "status": "proven",
                        "source": source,
                        "explanation": f"Proven by {source}.",
                    }
                    for criterion_id, description, source in BOUND
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

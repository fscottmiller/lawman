"""Work completion is decided criterion by criterion, against the bound source.

A criterion names the one source that can prove it. Passing evidence attached
to the right ID is no longer enough: it must come from the source the contract
asked for, and no source may cover two obligations.
"""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from lawman import (
    AcceptanceCriterion,
    CriterionEvidence,
    CriterionResult,
    LawmanError,
    WorkContract,
    WorkContractResult,
    WorkEvidence,
    evaluate_work_contract,
)
from lawman.__main__ import main

CRITERIA = (
    AcceptanceCriterion("AC1", "Invalid tokens return 401", "test_invalid_token"),
    AcceptanceCriterion("AC2", "Valid tokens return 200", "test_valid_token"),
    AcceptanceCriterion("AC3", "Authentication failures emit an audit event", "test_authentication_audit_event"),
)
CONTRACT = WorkContract(CRITERIA)

CONTRACT_DOCUMENT = {
    "criteria": [
        {"id": item.id, "description": item.description, "evidence_source": item.evidence_source}
        for item in CRITERIA
    ]
}

RESULT_FIELDS = ["id", "description", "evidence_source", "status", "source", "explanation"]


def evidence(ac1=True, ac2=True, ac3=True, missing=(), sources=None):
    """Evidence from each criterion's bound source, unless a test says otherwise."""
    passed = {"AC1": ac1, "AC2": ac2, "AC3": ac3}
    presented = sources or {}
    entries = tuple(
        CriterionEvidence(item.id, presented.get(item.id, item.evidence_source), passed[item.id])
        for item in CRITERIA
        if item.id not in missing
    )
    return WorkEvidence(entries)


def evidence_document(**kwargs):
    return {
        "evidence": [
            {"criterion_id": entry.criterion_id, "source": entry.source, "passed": entry.passed}
            for entry in evidence(**kwargs).entries
        ]
    }


def command(contract, evidence_):
    """Run `lawman work` over two documents, and report what the command did."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with tempfile.TemporaryDirectory() as directory:
        written = []
        for name, document in (("contract.json", contract), ("evidence.json", evidence_)):
            path = Path(directory) / name
            path.write_text(json.dumps(document), encoding="utf-8")
            written.append(str(path))
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = main(["work", "--contract", written[0], "--evidence", written[1]])
    return exit_code, stdout.getvalue(), stderr.getvalue()


class BindsEveryCriterionToOneSource(unittest.TestCase):
    def test_every_criterion_requires_one_evidence_source(self):
        """AC1. No binding, no criterion — parsed or constructed, and exit 2 either way."""
        unbound = (
            {"id": "AC1", "description": "Invalid tokens return 401"},
            {"id": "AC1", "description": "Invalid tokens return 401", "evidence_source": ""},
            {"id": "AC1", "description": "Invalid tokens return 401", "evidence_source": "   "},
            {"id": "AC1", "description": "Invalid tokens return 401", "evidence_source": None},
            {"id": "AC1", "description": "Invalid tokens return 401", "evidence_source": 1},
            {"id": "AC1", "description": "Invalid tokens return 401", "evidence_source": ["test_invalid_token"]},
            {"id": "AC1", "description": "Invalid tokens return 401", "evidence_source": {"test": "invalid_token"}},
        )
        for criterion in unbound:
            with self.subTest(criterion=criterion):
                with self.assertRaises(LawmanError) as refusal:
                    WorkContract.from_dict({"criteria": [criterion]})
                self.assertIn("evidence_source", str(refusal.exception))

                exit_code, stdout, stderr = command({"criteria": [criterion]}, evidence_document())
                self.assertEqual(exit_code, 2)
                self.assertEqual(stdout, "")
                self.assertIn("evidence_source", stderr)

        # One criterion in a contract is enough to refuse the whole contract.
        partly_bound = {"criteria": [CONTRACT_DOCUMENT["criteria"][0], {"id": "AC2", "description": "Unbound"}]}
        with self.assertRaises(LawmanError):
            WorkContract.from_dict(partly_bound)

        # Direct construction cannot skip the field or blank it out.
        with self.assertRaises(TypeError):
            AcceptanceCriterion("AC1", "Invalid tokens return 401")
        for source in ("", "   ", None, 7, ["test_invalid_token"]):
            with self.subTest(source=source), self.assertRaises(LawmanError):
                AcceptanceCriterion("AC1", "Invalid tokens return 401", source)

        # Exactly one source per criterion, kept as the contract wrote it.
        contract = WorkContract.from_dict(CONTRACT_DOCUMENT)
        self.assertEqual(
            [item.evidence_source for item in contract.criteria],
            ["test_invalid_token", "test_valid_token", "test_authentication_audit_event"],
        )
        self.assertEqual(contract, CONTRACT)

    def test_contract_requires_unique_evidence_sources(self):
        """AC2. One source proves one obligation, so a shared binding is refused."""
        shared = {
            "criteria": [
                {"id": "AC1", "description": "Invalid tokens return 401", "evidence_source": "test_auth"},
                {"id": "AC2", "description": "Valid tokens return 200", "evidence_source": "test_auth"},
            ]
        }

        with self.assertRaises(LawmanError) as refusal:
            WorkContract.from_dict(shared)
        self.assertIn("evidence sources must be unique", str(refusal.exception))

        exit_code, stdout, stderr = command(shared, {"evidence": []})
        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("evidence sources must be unique", stderr)

        # The same rule holds for code that builds the contract directly.
        with self.assertRaises(LawmanError):
            WorkContract((CRITERIA[0], AcceptanceCriterion("AC2", "Something else", CRITERIA[0].evidence_source)))

        # Identifiers are opaque, so nothing is folded together: these differ.
        distinct = WorkContract.from_dict(
            {
                "criteria": [
                    {"id": "AC1", "description": "Invalid tokens return 401", "evidence_source": "test_auth"},
                    {"id": "AC2", "description": "Valid tokens return 200", "evidence_source": "TEST_AUTH"},
                    {"id": "AC3", "description": "Failures are audited", "evidence_source": "test_auth "},
                ]
            }
        )
        self.assertEqual(len(distinct.criteria), 3)


class AcceptsOnlyTheSourceTheContractBound(unittest.TestCase):
    def test_evidence_must_match_the_bound_source_exactly(self):
        """AC3. The evidence schema is unchanged; matching is exact and case-sensitive."""
        document = {"evidence": [{"criterion_id": "AC1", "source": "test_invalid_token", "passed": True}]}
        entry = WorkEvidence.from_dict(document).entries[0]

        self.assertEqual((entry.criterion_id, entry.source, entry.passed), ("AC1", "test_invalid_token", True))
        self.assertTrue(evaluate_work_contract(CONTRACT, evidence()).satisfied)

        near_misses = {
            "another criterion's source": "test_valid_token",
            "different case": "TEST_INVALID_TOKEN",
            "a prefix of the binding": "test_invalid",
            "a longer name": "test_invalid_token_v2",
            "a path Lawman does not parse": "tests/test_auth.py::test_invalid_token",
            "leading whitespace": " test_invalid_token",
        }
        for situation, source in near_misses.items():
            with self.subTest(situation=situation):
                with self.assertRaises(LawmanError) as refusal:
                    evaluate_work_contract(CONTRACT, evidence(sources={"AC1": source}))
                self.assertIn("AC1 requires test_invalid_token", str(refusal.exception))

        # A result cannot be assembled around a mismatch either.
        with self.assertRaises(LawmanError):
            CriterionResult(CRITERIA[0], CriterionEvidence("AC1", "test_something_else", True))

    def test_bound_evidence_determines_proven_and_failed(self):
        """AC4. The bound source's verdict is the criterion's status, and the exit code."""
        proven = evaluate_work_contract(CONTRACT, evidence())

        self.assertTrue(proven.satisfied)
        self.assertEqual(tuple(item.status for item in proven.criteria), ("proven", "proven", "proven"))
        self.assertEqual(proven.criteria[0].source, "test_invalid_token")
        self.assertEqual(proven.criteria[0].explanation, "Proven by test_invalid_token.")

        failed = evaluate_work_contract(CONTRACT, evidence(ac2=False))

        self.assertFalse(failed.satisfied)
        self.assertEqual(tuple(item.status for item in failed.criteria), ("proven", "failed", "proven"))
        self.assertEqual(failed.criteria[1].source, "test_valid_token")
        self.assertEqual(failed.criteria[1].explanation, "Failed: test_valid_token reported failure.")

        satisfied_run = command(CONTRACT_DOCUMENT, evidence_document())
        unsatisfied_run = command(CONTRACT_DOCUMENT, evidence_document(ac2=False))

        self.assertEqual(satisfied_run[0], 0, satisfied_run[2])
        self.assertTrue(json.loads(satisfied_run[1])["satisfied"])
        self.assertEqual(unsatisfied_run[0], 1, unsatisfied_run[2])
        self.assertFalse(json.loads(unsatisfied_run[1])["satisfied"])
        self.assertEqual(unsatisfied_run[2], "")

    def test_missing_bound_evidence_is_explicitly_unproven(self):
        """AC5. Silence about the bound source is unproven, and says which source is owed."""
        result = evaluate_work_contract(CONTRACT, evidence(missing=("AC3",)))
        audit = result.criteria[2]

        self.assertFalse(result.satisfied)
        self.assertEqual(audit.status, "unproven")
        self.assertIsNone(audit.source)
        self.assertEqual(audit.to_dict()["evidence_source"], "test_authentication_audit_event")
        self.assertEqual(
            audit.explanation,
            "Unproven: no evidence from test_authentication_audit_event was provided.",
        )

        silent = evaluate_work_contract(CONTRACT, WorkEvidence(()))

        self.assertEqual(tuple(item.status for item in silent.criteria), ("unproven", "unproven", "unproven"))
        self.assertEqual(
            [item.explanation for item in silent.criteria],
            [f"Unproven: no evidence from {item.evidence_source} was provided." for item in CRITERIA],
        )

        # Another criterion's evidence cannot reach it. Naming AC3 with AC1's
        # source is a refusal, and proving AC1 twice is not proof of AC3.
        with self.assertRaises(LawmanError):
            evaluate_work_contract(CONTRACT, WorkEvidence((CriterionEvidence("AC3", "test_invalid_token", True),)))

        exit_code, stdout, stderr = command(CONTRACT_DOCUMENT, evidence_document(missing=("AC3",)))

        self.assertEqual(exit_code, 1)
        self.assertEqual(stderr, "")
        self.assertEqual(json.loads(stdout)["criteria"][2]["status"], "unproven")

    def test_results_account_for_every_binding_in_contract_order(self):
        """AC7. Every criterion, in the contract's order, with both sources reported."""
        presented = WorkEvidence(tuple(reversed(evidence(ac2=False, missing=("AC3",)).entries)))

        document = evaluate_work_contract(CONTRACT, presented).to_dict()

        self.assertEqual([item["id"] for item in document["criteria"]], ["AC1", "AC2", "AC3"])
        for item in document["criteria"]:
            with self.subTest(criterion=item["id"]):
                self.assertEqual(list(item), RESULT_FIELDS)
        self.assertEqual(
            document["criteria"],
            [
                {
                    "id": "AC1",
                    "description": "Invalid tokens return 401",
                    "evidence_source": "test_invalid_token",
                    "status": "proven",
                    "source": "test_invalid_token",
                    "explanation": "Proven by test_invalid_token.",
                },
                {
                    "id": "AC2",
                    "description": "Valid tokens return 200",
                    "evidence_source": "test_valid_token",
                    "status": "failed",
                    "source": "test_valid_token",
                    "explanation": "Failed: test_valid_token reported failure.",
                },
                {
                    "id": "AC3",
                    "description": "Authentication failures emit an audit event",
                    "evidence_source": "test_authentication_audit_event",
                    "status": "unproven",
                    "source": None,
                    "explanation": "Unproven: no evidence from test_authentication_audit_event was provided.",
                },
            ],
        )

        # The command prints the same account, in the same order.
        exit_code, stdout, _ = command(CONTRACT_DOCUMENT, evidence_document(ac2=False, missing=("AC3",)))
        printed = json.loads(stdout)

        self.assertEqual(exit_code, 1)
        self.assertEqual(printed["criteria"], document["criteria"])
        self.assertEqual(list(printed), ["satisfied", "criteria"])


class RefusesMalformedOrAmbiguousInput(unittest.TestCase):
    def test_duplicate_criterion_ids_are_refused(self):
        with self.assertRaises(LawmanError):
            WorkContract.from_dict(
                {
                    "criteria": [
                        {"id": "AC1", "description": "First", "evidence_source": "test_first"},
                        {"id": "AC1", "description": "Second", "evidence_source": "test_second"},
                    ]
                }
            )

    def test_an_empty_contract_is_refused(self):
        with self.assertRaises(LawmanError):
            WorkContract.from_dict({"criteria": []})

    def test_a_malformed_criterion_is_refused(self):
        malformed = (
            {},
            {"id": "", "description": "Returns 401", "evidence_source": "test_invalid_token"},
            {"id": "AC1", "description": "", "evidence_source": "test_invalid_token"},
            {"id": 1, "description": "Returns 401", "evidence_source": "test_invalid_token"},
            "AC1",
        )
        for criterion in malformed:
            with self.subTest(criterion=criterion), self.assertRaises(LawmanError):
                WorkContract.from_dict({"criteria": [criterion]})

    def test_evidence_for_an_unknown_criterion_is_refused(self):
        unknown = WorkEvidence((CriterionEvidence("AC4", "test_other", True),))

        with self.assertRaises(LawmanError) as refusal:
            evaluate_work_contract(CONTRACT, unknown)

        self.assertIn("unknown criteria: AC4", str(refusal.exception))

    def test_malformed_evidence_is_refused(self):
        malformed = (
            {},
            {"evidence": {}},
            {"evidence": [{}]},
            {"evidence": [{"criterion_id": "AC1", "source": "", "passed": True}]},
            {"evidence": [{"criterion_id": "AC1", "source": "test_invalid_token", "passed": "true"}]},
        )
        for document in malformed:
            with self.subTest(document=document), self.assertRaises(LawmanError):
                WorkEvidence.from_dict(document)

    def test_duplicate_evidence_for_one_criterion_is_refused(self):
        with self.assertRaises(LawmanError):
            WorkEvidence.from_dict(
                {
                    "evidence": [
                        {"criterion_id": "AC1", "source": "test_invalid_token", "passed": True},
                        {"criterion_id": "AC1", "source": "test_invalid_token", "passed": False},
                    ]
                }
            )


class HoldsItsInvariantsWhenConstructedDirectly(unittest.TestCase):
    def test_bound_work_domain_is_immutable_and_cannot_bypass_invariants(self):
        """AC10. The binding is an invariant of the types, not a check in the parser."""
        invalid_constructions = (
            lambda: AcceptanceCriterion("", "Description", "test_source"),
            lambda: AcceptanceCriterion("AC1", "", "test_source"),
            lambda: AcceptanceCriterion("AC1", "Description", ""),
            lambda: WorkContract(()),
            lambda: WorkContract((CRITERIA[0], CRITERIA[0])),
            lambda: WorkContract((CRITERIA[0], AcceptanceCriterion("AC9", "Another", CRITERIA[0].evidence_source))),
            lambda: WorkContract(({"id": "AC1", "description": "Description", "evidence_source": "test"},)),
            lambda: CriterionEvidence("AC1", "test", "true"),
            lambda: WorkEvidence((evidence().entries[0], evidence().entries[0])),
            lambda: CriterionResult(CRITERIA[0], CriterionEvidence("AC2", "test_valid_token", True)),
            lambda: CriterionResult(CRITERIA[0], CriterionEvidence("AC1", "test_valid_token", True)),
            lambda: WorkContractResult(()),
        )
        for construct in invalid_constructions:
            with self.subTest(construct=construct), self.assertRaises(LawmanError):
                construct()

        result = evaluate_work_contract(CONTRACT, evidence())

        with self.assertRaises(AttributeError):
            result.satisfied = False
        with self.assertRaises(TypeError):
            result.criteria[0] = CriterionResult(CRITERIA[0], None)
        with self.assertRaises(AttributeError):
            result.criteria[0].evidence = None
        with self.assertRaises(AttributeError):
            result.criteria[0].criterion.evidence_source = "test_something_else"
        with self.assertRaises(TypeError):
            CONTRACT.criteria[0] = CRITERIA[1]

        self.assertEqual(CONTRACT.criteria[0].evidence_source, "test_invalid_token")


if __name__ == "__main__":
    unittest.main()

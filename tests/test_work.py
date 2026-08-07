"""Work completion is decided criterion by criterion, never by assertion."""

import unittest

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

CRITERIA = (
    AcceptanceCriterion("AC1", "Invalid tokens return 401"),
    AcceptanceCriterion("AC2", "Valid tokens return 200"),
    AcceptanceCriterion("AC3", "Authentication failures emit an audit event"),
)
CONTRACT = WorkContract(CRITERIA)


def evidence(ac1=True, ac2=True, ac3=True):
    values = {"AC1": ac1, "AC2": ac2, "AC3": ac3}
    entries = (
        CriterionEvidence(criterion_id, f"test_{criterion_id.lower()}", passed)
        for criterion_id, passed in values.items()
    )
    return WorkEvidence(tuple(entries))


class AccountsForEveryCriterion(unittest.TestCase):
    def test_all_criteria_proven_satisfies_the_contract(self):
        result = evaluate_work_contract(CONTRACT, evidence())

        self.assertTrue(result.satisfied)
        self.assertEqual(tuple(item.status for item in result.criteria), ("proven", "proven", "proven"))

    def test_one_failed_criterion_does_not_satisfy_the_contract(self):
        result = evaluate_work_contract(CONTRACT, evidence(ac2=False))

        self.assertFalse(result.satisfied)
        self.assertEqual(result.criteria[1].status, "failed")
        self.assertEqual(result.criteria[1].source, "test_ac2")
        self.assertEqual(result.criteria[1].explanation, "Failed: test_ac2 reported failure.")

    def test_one_missing_criterion_is_unproven_and_does_not_satisfy(self):
        partial = WorkEvidence(evidence().entries[:2])

        result = evaluate_work_contract(CONTRACT, partial)

        self.assertFalse(result.satisfied)
        self.assertEqual(result.criteria[2].status, "unproven")
        self.assertIsNone(result.criteria[2].source)
        self.assertEqual(result.criteria[2].explanation, "Unproven: no evidence was provided.")

    def test_no_evidence_leaves_every_criterion_unproven(self):
        result = evaluate_work_contract(CONTRACT, WorkEvidence(()))

        self.assertFalse(result.satisfied)
        self.assertEqual(tuple(item.status for item in result.criteria), ("unproven", "unproven", "unproven"))

    def test_result_order_follows_the_contract_not_the_evidence(self):
        reversed_evidence = WorkEvidence(tuple(reversed(evidence().entries)))

        result = evaluate_work_contract(CONTRACT, reversed_evidence)

        self.assertEqual(tuple(item.criterion.id for item in result.criteria), ("AC1", "AC2", "AC3"))

    def test_identical_inputs_produce_identical_results(self):
        results = [evaluate_work_contract(CONTRACT, evidence(ac2=False)) for _ in range(5)]

        self.assertEqual(len(set(results)), 1)
        self.assertEqual(len({repr(result.to_dict()) for result in results}), 1)


class RefusesMalformedOrAmbiguousInput(unittest.TestCase):
    def test_duplicate_criterion_ids_are_refused(self):
        with self.assertRaises(LawmanError):
            WorkContract.from_dict(
                {"criteria": [{"id": "AC1", "description": "First"}, {"id": "AC1", "description": "Second"}]}
            )

    def test_an_empty_contract_is_refused(self):
        with self.assertRaises(LawmanError):
            WorkContract.from_dict({"criteria": []})

    def test_a_malformed_criterion_is_refused(self):
        malformed = (
            {},
            {"id": "", "description": "Returns 401"},
            {"id": "AC1", "description": ""},
            {"id": 1, "description": "Returns 401"},
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
            {"evidence": [{"criterion_id": "AC1", "source": "test_ac1", "passed": "true"}]},
        )
        for document in malformed:
            with self.subTest(document=document), self.assertRaises(LawmanError):
                WorkEvidence.from_dict(document)

    def test_duplicate_evidence_for_one_criterion_is_refused(self):
        with self.assertRaises(LawmanError):
            WorkEvidence.from_dict(
                {
                    "evidence": [
                        {"criterion_id": "AC1", "source": "first", "passed": True},
                        {"criterion_id": "AC1", "source": "second", "passed": False},
                    ]
                }
            )


class HoldsItsInvariantsWhenConstructedDirectly(unittest.TestCase):
    def test_direct_construction_cannot_bypass_domain_invariants(self):
        invalid_constructions = (
            lambda: AcceptanceCriterion("", "Description"),
            lambda: AcceptanceCriterion("AC1", ""),
            lambda: WorkContract(()),
            lambda: WorkContract((CRITERIA[0], CRITERIA[0])),
            lambda: WorkContract(({"id": "AC1", "description": "Description"},)),
            lambda: CriterionEvidence("AC1", "test", "true"),
            lambda: WorkEvidence((evidence().entries[0], evidence().entries[0])),
            lambda: CriterionResult(CRITERIA[0], CriterionEvidence("AC2", "test", True)),
            lambda: WorkContractResult(()),
        )
        for construct in invalid_constructions:
            with self.subTest(construct=construct), self.assertRaises(LawmanError):
                construct()

    def test_results_are_immutable_after_construction(self):
        result = evaluate_work_contract(CONTRACT, evidence())

        with self.assertRaises(AttributeError):
            result.satisfied = False
        with self.assertRaises(TypeError):
            result.criteria[0] = CriterionResult(CRITERIA[0], None)
        with self.assertRaises(AttributeError):
            result.criteria[0].evidence = None


if __name__ == "__main__":
    unittest.main()

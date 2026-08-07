"""Canonical scenario: deploy to production requires passing tests and human approval."""

import unittest

from lawman import Contract, Evidence, Intent, LawmanError, decide

DEPLOY = Intent(action="deploy", target="production")
PRODUCTION_CONTRACT = Contract(requires=("tests_passed", "human_approved"))


def verdict(**facts):
    return decide(DEPLOY, PRODUCTION_CONTRACT, Evidence(facts))


class AllowsWhenEveryRequirementIsProven(unittest.TestCase):
    def test_tests_passed_and_human_approved_allows(self):
        decision = verdict(tests_passed=True, human_approved=True)

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.satisfied, ("tests_passed", "human_approved"))
        self.assertEqual(decision.failed, ())
        self.assertEqual(decision.unproven, ())
        self.assertEqual(
            decision.explanation,
            "Allowed: deploy -> production. Satisfied: tests_passed, human_approved.",
        )

    def test_evidence_beyond_the_contract_is_ignored(self):
        decision = verdict(tests_passed=True, human_approved=True, coverage_reported=False)

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.satisfied, ("tests_passed", "human_approved"))


class DeniesWhenEvidenceRefutesARequirement(unittest.TestCase):
    def test_tests_failed_denies_even_with_human_approval(self):
        decision = verdict(tests_passed=False, human_approved=True)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.failed, ("tests_passed",))
        self.assertEqual(decision.satisfied, ("human_approved",))
        self.assertEqual(
            decision.explanation,
            "Denied: deploy -> production. Failed: tests_passed. Satisfied: human_approved.",
        )

    def test_human_refusal_denies_even_with_passing_tests(self):
        decision = verdict(tests_passed=True, human_approved=False)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.failed, ("human_approved",))


class DeniesWhenEvidenceIsMissing(unittest.TestCase):
    """Silence is never proof."""

    def test_no_human_approval_evidence_denies(self):
        decision = verdict(tests_passed=True)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.unproven, ("human_approved",))
        self.assertEqual(decision.satisfied, ("tests_passed",))
        self.assertEqual(
            decision.explanation,
            "Denied: deploy -> production. Unproven: human_approved. Satisfied: tests_passed.",
        )

    def test_no_evidence_at_all_denies(self):
        decision = verdict()

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.unproven, ("tests_passed", "human_approved"))
        self.assertEqual(decision.satisfied, ())
        self.assertEqual(
            decision.explanation,
            "Denied: deploy -> production. Unproven: tests_passed, human_approved.",
        )

    def test_failed_and_unproven_are_reported_separately(self):
        decision = verdict(tests_passed=False)

        self.assertEqual(decision.failed, ("tests_passed",))
        self.assertEqual(decision.unproven, ("human_approved",))
        self.assertEqual(
            decision.explanation,
            "Denied: deploy -> production. Failed: tests_passed. Unproven: human_approved.",
        )


class DecidesDeterministically(unittest.TestCase):
    def test_identical_inputs_produce_identical_decisions(self):
        for facts in (
            {"tests_passed": True, "human_approved": True},
            {"tests_passed": False, "human_approved": True},
            {"tests_passed": True},
            {},
        ):
            with self.subTest(facts=facts):
                decisions = [verdict(**facts) for _ in range(5)]

                self.assertEqual(len(set(decisions)), 1)
                self.assertEqual(len({repr(d.to_dict()) for d in decisions}), 1)

    def test_requirement_order_follows_the_contract_not_the_evidence(self):
        reversed_evidence = Evidence({"human_approved": True, "tests_passed": True})

        decision = decide(DEPLOY, PRODUCTION_CONTRACT, reversed_evidence)

        self.assertEqual(decision.satisfied, ("tests_passed", "human_approved"))


class RejectsMalformedInput(unittest.TestCase):
    def test_intent_requires_action_and_target(self):
        for data in ({}, {"action": "deploy"}, {"target": "production"}, {"action": "", "target": "production"}):
            with self.subTest(data=data):
                with self.assertRaises(LawmanError):
                    Intent.from_dict(data)

    def test_intent_must_be_an_object(self):
        with self.assertRaises(LawmanError):
            Intent.from_dict(["deploy", "production"])

    def test_empty_contract_is_a_misconfiguration_not_a_permit(self):
        with self.assertRaises(LawmanError):
            Contract.from_dict({"requires": []})

    def test_contract_requires_a_list_of_names(self):
        for data in ({}, {"requires": "tests_passed"}, {"requires": [1]}, {"requires": [""]}):
            with self.subTest(data=data):
                with self.assertRaises(LawmanError):
                    Contract.from_dict(data)

    def test_evidence_must_be_explicit_booleans(self):
        for data in (
            {"tests_passed": "true"},
            {"tests_passed": 1},
            {"tests_passed": None},
            {"tests_passed": ["passed"]},
        ):
            with self.subTest(data=data):
                with self.assertRaises(LawmanError):
                    Evidence.from_dict(data)

    def test_duplicate_requirements_are_evaluated_once(self):
        contract = Contract.from_dict({"requires": ["tests_passed", "human_approved", "tests_passed"]})

        self.assertEqual(contract.requires, ("tests_passed", "human_approved"))


if __name__ == "__main__":
    unittest.main()

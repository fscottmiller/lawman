"""The transition domain: what Lawman sends to policy, and what it accepts back."""

import unittest

from lawman import Decision, Evidence, Intent, LawmanError

DEPLOY = Intent(action="deploy", target="production")


class CarriesEvidenceWithoutReadingIt(unittest.TestCase):
    """A fact's meaning belongs to the policy. Lawman only checks the shape."""

    def test_any_json_value_is_carried_through(self):
        evidence = Evidence.from_dict(
            {
                "tests_passed": True,
                "coverage": 87.5,
                "reviewers": ["ada", "grace"],
                "release": {"tag": "v2.1.0"},
                "rollback_plan": None,
                "environment": "production",
            }
        )

        self.assertEqual(evidence.facts["coverage"], 87.5)
        self.assertEqual(evidence.facts["release"], {"tag": "v2.1.0"})
        self.assertIsNone(evidence.facts["rollback_plan"])

    def test_evidence_must_be_an_object_with_named_keys(self):
        for document in (None, 7, "tests_passed", ["tests_passed"], {"": True}, {"   ": True}):
            with self.subTest(document=document):
                with self.assertRaises(LawmanError):
                    Evidence.from_dict(document)

    def test_evidence_cannot_change_after_it_is_presented(self):
        facts = {"tests_passed": False}
        evidence = Evidence.from_dict(facts)

        facts["tests_passed"] = True

        self.assertIs(evidence.facts["tests_passed"], False)
        with self.assertRaises(TypeError):
            evidence.facts["tests_passed"] = True


class ReadsOnlyAWellFormedDecision(unittest.TestCase):
    def test_a_decision_reports_allowed_the_intent_and_the_policy_reasons(self):
        decision = Decision.from_dict({"allowed": True, "reasons": ["Tests passed.", "A human approved."]}, DEPLOY)

        self.assertEqual(
            decision.to_dict(),
            {
                "allowed": True,
                "intent": {"action": "deploy", "target": "production"},
                "reasons": ["Tests passed.", "A human approved."],
            },
        )

    def test_reasons_keep_the_order_and_the_repetition_the_policy_gave_them(self):
        reasons = ["Third.", "First.", "Third.", "Second."]

        self.assertEqual(Decision.from_dict({"allowed": False, "reasons": reasons}, DEPLOY).reasons, tuple(reasons))

    def test_a_decision_lawman_cannot_read_is_refused(self):
        for document in (
            None,
            7,
            "allowed",
            [],
            {},
            {"allowed": True},
            {"reasons": ["Tests passed."]},
            {"allowed": "true", "reasons": ["Tests passed."]},
            {"allowed": 1, "reasons": ["Tests passed."]},
            {"allowed": None, "reasons": ["Tests passed."]},
            {"allowed": True, "reasons": []},
            {"allowed": True, "reasons": "Tests passed."},
            {"allowed": True, "reasons": {"why": "Tests passed."}},
            {"allowed": True, "reasons": [""]},
            {"allowed": True, "reasons": ["   "]},
            {"allowed": True, "reasons": [7]},
            {"allowed": True, "reasons": ["Tests passed.", None]},
            {"allowed": True, "reasons": ["Tests passed."], "deny": ["oops"]},
        ):
            with self.subTest(document=document):
                with self.assertRaises(LawmanError):
                    Decision.from_dict(document, DEPLOY)


class HoldsItsInvariantsWhenConstructedDirectly(unittest.TestCase):
    """Parsing is one way in, not the only way. The invariants belong to the type."""

    def test_a_decision_without_a_reason_cannot_exist(self):
        for reasons in ((), [], None, "Tests passed."):
            with self.subTest(reasons=reasons):
                with self.assertRaises(LawmanError):
                    Decision(allowed=True, intent=DEPLOY, reasons=reasons)

    def test_a_decision_must_name_the_intent_it_decided(self):
        for intent in (None, "deploy -> production", {"action": "deploy", "target": "production"}):
            with self.subTest(intent=intent):
                with self.assertRaises(LawmanError):
                    Decision(allowed=True, intent=intent, reasons=("Tests passed.",))

    def test_an_intent_must_name_an_action_and_a_target(self):
        malformed = (None, 7, [], {}, {"action": "deploy"}, {"target": "production"}, {"action": "", "target": "p"})

        for document in malformed:
            with self.subTest(document=document):
                with self.assertRaises(LawmanError):
                    Intent.from_dict(document)

    def test_decisions_are_immutable_after_construction(self):
        decision = Decision(allowed=False, intent=DEPLOY, reasons=("Tests did not pass.",))

        with self.assertRaises(AttributeError):
            decision.allowed = True
        with self.assertRaises(AttributeError):
            decision.reasons = ("Fine, then.",)


if __name__ == "__main__":
    unittest.main()

"""Documentation should make claims that can be checked.

These are not prose reviews. Each assertion names something a reader has to be
told to use Lawman, or something the code would silently contradict.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / "docs" / "running-lawman.md"
ADR = ROOT / "docs" / "decisions" / "0009-delegate-transition-policy-to-opa.md"
README = ROOT / "README.md"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


class DocumentsThePublicContract(unittest.TestCase):
    def test_opa_documentation_and_adr_cover_the_public_contract(self):
        """AC14. Installation, layout, schemas, exit codes, boundary, and the ADR."""
        guide = GUIDE.read_text(encoding="utf-8")
        pinned = re.findall(r'OPA_VERSION:\s*"([^"]+)"', WORKFLOW.read_text(encoding="utf-8"))

        self.assertEqual(len(pinned), 1, "CI must pin exactly one OPA version")

        installation = {
            "names the OPA version CI installs": pinned[0],
            "shows how to get the executable": "releases/download/v",
            "says it is found on PATH": "found on `PATH`",
        }
        layout = {
            "registry": ".lawman/policies.json",
            "policy directory": "policies/deploy-production.rego",
            "paths stay inside the policy directory": "it must stay inside `.lawman/`",
        }
        schemas = {
            "the decision document": "data.lawman.decision",
            "input carries the intent": '"intent": { "action": "deploy", "target": "production" }',
            "input carries the evidence": '"evidence": { "tests_passed": true, "human_approved": true }',
            "evidence is uninterpreted": "Lawman does not know which keys matter",
            "result names allowed": '"allowed": true',
            "result names reasons": '"reasons": ["Tests passed and human approval was recorded."]',
            "an allowed decision still explains itself": "including for an allowed decision",
            "unknown result fields are refused": "Any other field is refused, not ignored",
        }
        exit_codes = {
            "allowed, denied, and refused": "`0` allowed, `1` denied, `2` Lawman never reached a policy decision",
            "a missing executable refuses": "`opa` is not installed, or exits non-zero",
            "an unreadable decision refuses": "is undefined, empty, or not exactly one decision",
            "refusing is not denying": "Refusing is not denying",
        }
        boundary = {
            "work contracts need no OPA": "This command needs no OPA",
            "the two models do not mix": "a work-contract result is not policy input",
            "satisfaction is not authorization": "A satisfied work contract does not authorize a transition",
        }

        for section, claims in (
            ("installation", installation),
            ("policy layout", layout),
            ("schemas", schemas),
            ("exit codes", exit_codes),
            ("work-contract boundary", boundary),
        ):
            for claim, expected in claims.items():
                with self.subTest(section=section, claim=claim):
                    self.assertIn(expected, guide)

        adr = ADR.read_text(encoding="utf-8")
        for claim, expected in {
            "is accepted": "Status: Accepted",
            "records the new flow": "Intent → Policy Selection → OPA → Decision",
            "fixes the decision document": "data.lawman.decision",
            "delegates rather than embeds": "Lawman does not evaluate transition policy. OPA does.",
            "records the breaking rename": "No compatibility layer for `.lawman/contracts.json`",
        }.items():
            with self.subTest(claim=claim):
                self.assertIn(expected, adr)

        # The README advertises the flow the code actually runs.
        readme = README.read_text(encoding="utf-8")
        self.assertIn("**Intent → Policy Selection → OPA → Decision**", readme)
        self.assertNotIn("contracts.json", readme)

    def test_the_guide_does_not_advertise_a_retired_transition_contract(self):
        guide = GUIDE.read_text(encoding="utf-8")

        for retired in (".lawman/contracts.json", "contracts/deploy-production.json", '{ "requires":'):
            with self.subTest(retired=retired):
                self.assertNotIn(retired, guide)


if __name__ == "__main__":
    unittest.main()

"""Selection decides which policy applies. The requester does not."""

import json
import tempfile
import unittest
from pathlib import Path

from lawman import Intent, LawmanError, PolicyRegistry, select_policy

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = Intent(action="deploy", target="production")
DEPLOY_PRODUCTION = {"deploy": {"production": "policies/deploy-production.rego"}}
ALLOW_ANYTHING = 'package lawman\n\ndecision := {"allowed": true, "reasons": ["Anything goes."]}\n'


def write(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document if isinstance(document, str) else json.dumps(document), encoding="utf-8")
    return path


def policy_directory(directory, registry, policies=()):
    """Build a policy directory: a registry, plus policies it can point at."""
    configured = Path(directory) / ".lawman"
    write(configured / "policies.json", registry)
    for relative, policy in dict(policies).items():
        write(configured / relative, policy)
    return configured


class SelectsThePolicyTheRepositoryConfigured(unittest.TestCase):
    def test_repository_selects_policy_for_the_intent(self):
        """AC1. The registry names the policy, and it is the only thing that does."""
        selected = select_policy(DEPLOY, ROOT / ".lawman")

        self.assertEqual(selected, (ROOT / ".lawman" / "policies" / "deploy-production.rego").resolve())
        self.assertTrue(selected.is_file())

        # The same intent always resolves to the same file.
        self.assertEqual({select_policy(DEPLOY, ROOT / ".lawman") for _ in range(5)}, {selected})

        # A repository carrying only the retired contract registry is refused:
        # .lawman/contracts.json no longer selects transition policy.
        with tempfile.TemporaryDirectory() as directory:
            retired = Path(directory) / ".lawman"
            write(retired / "contracts.json", DEPLOY_PRODUCTION)
            write(retired / "contracts" / "deploy-production.json", {"requires": ["tests_passed"]})

            with self.assertRaises(LawmanError) as refusal:
                select_policy(DEPLOY, retired)

        self.assertIn("cannot read policy registry", str(refusal.exception))

        # And where both exist, only policies.json is read.
        with tempfile.TemporaryDirectory() as directory:
            configured = policy_directory(
                directory, DEPLOY_PRODUCTION, {"policies/deploy-production.rego": ALLOW_ANYTHING}
            )
            write(configured / "contracts.json", {"deploy": {"production": "contracts/other.json"}})

            self.assertEqual(select_policy(DEPLOY, configured).name, "deploy-production.rego")

    def test_a_policy_is_read_from_the_policy_directory_not_from_beside_the_intent(self):
        with tempfile.TemporaryDirectory() as directory:
            write(Path(directory) / "policy.rego", ALLOW_ANYTHING)
            selected = select_policy(
                DEPLOY,
                policy_directory(directory, DEPLOY_PRODUCTION, {"policies/deploy-production.rego": ALLOW_ANYTHING}),
            )

        self.assertEqual(selected.parent.name, "policies")

    def test_one_action_can_govern_several_targets_independently(self):
        registry = PolicyRegistry(
            {"deploy": {"production": "policies/production.rego", "staging": "policies/staging.rego"}}
        )

        self.assertEqual(registry.path_for(DEPLOY), "policies/production.rego")
        self.assertEqual(registry.path_for(Intent(action="deploy", target="staging")), "policies/staging.rego")


class FailsClosedWhenItCannotFindTheRules(unittest.TestCase):
    """Not knowing the rules is not the same as applying them."""

    def test_invalid_or_escaping_policy_selection_is_refused(self):
        """AC8. Every way selection can fail refuses, and none of them denies."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root / "escaped.rego", ALLOW_ANYTHING)
            configured = policy_directory(
                root / "configured", DEPLOY_PRODUCTION, {"policies/deploy-production.rego": ALLOW_ANYTHING}
            )
            symlinked = policy_directory(root / "symlinked", DEPLOY_PRODUCTION)
            (symlinked / "policies").mkdir(parents=True, exist_ok=True)
            (symlinked / "policies" / "deploy-production.rego").symlink_to(root / "escaped.rego")

            refusals = {
                "missing registry": (DEPLOY, root / "absent" / ".lawman", "cannot read policy registry"),
                "malformed registry": (DEPLOY, policy_directory(root / "a", "{ not json"), "not valid JSON"),
                "registry that is not an object": (
                    DEPLOY,
                    policy_directory(root / "b", ["deploy"]),
                    "policy registry must be an object",
                ),
                "registry naming no policies": (DEPLOY, policy_directory(root / "c", {}), "names no policies"),
                "registry not nested by target": (
                    DEPLOY,
                    policy_directory(root / "d", {"deploy": "policies/deploy-production.rego"}),
                    "policy registry action 'deploy' must be an object",
                ),
                "unconfigured target": (
                    Intent(action="deploy", target="staging"),
                    configured,
                    "no policy is configured",
                ),
                "unconfigured action": (
                    Intent(action="rollback", target="production"),
                    configured,
                    "no policy is configured",
                ),
                "missing policy file": (DEPLOY, policy_directory(root / "e", DEPLOY_PRODUCTION), "cannot read policy"),
                "absolute policy path": (
                    DEPLOY,
                    policy_directory(root / "f", {"deploy": {"production": str(root / "escaped.rego")}}),
                    "outside the policy directory",
                ),
                "parent directory escape": (
                    DEPLOY,
                    policy_directory(root / "g", {"deploy": {"production": "../../escaped.rego"}}),
                    "outside the policy directory",
                ),
                "symlink escape": (DEPLOY, symlinked, "outside the policy directory"),
            }

            for situation, (intent, configured_directory, expected) in refusals.items():
                with self.subTest(situation=situation):
                    with self.assertRaises(LawmanError) as refusal:
                        select_policy(intent, configured_directory)
                    self.assertIn(expected, str(refusal.exception))


class HoldsItsInvariantsWhenConstructedDirectly(unittest.TestCase):
    """Parsing is one way in, not the only way. The invariants belong to the type."""

    def test_a_registry_that_names_no_policies_cannot_exist(self):
        for policies in ({}, []):
            with self.subTest(policies=policies):
                with self.assertRaises(LawmanError):
                    PolicyRegistry(policies=policies)

    def test_registry_must_be_a_map(self):
        for policies in (None, "deploy", ["deploy"]):
            with self.subTest(policies=policies):
                with self.assertRaises(LawmanError):
                    PolicyRegistry(policies=policies)

    def test_every_action_names_a_map_of_targets(self):
        for targets in ("policies/deploy-production.rego", None, 7, ["production"], {}):
            with self.subTest(targets=targets):
                with self.assertRaises(LawmanError):
                    PolicyRegistry(policies={"deploy": targets})

    def test_actions_and_targets_are_names(self):
        for policies in (
            {"": {"production": "policies/deploy-production.rego"}},
            {"   ": {"production": "policies/deploy-production.rego"}},
            {"deploy": {"": "policies/deploy-production.rego"}},
            {"deploy": {"   ": "policies/deploy-production.rego"}},
        ):
            with self.subTest(policies=policies):
                with self.assertRaises(LawmanError):
                    PolicyRegistry(policies=policies)

    def test_every_entry_names_a_policy_path(self):
        for path in ("", "   ", None, 7, ["policies/deploy-production.rego"]):
            with self.subTest(path=path):
                with self.assertRaises(LawmanError):
                    PolicyRegistry(policies={"deploy": {"production": path}})

    def test_an_unconfigured_intent_has_no_path(self):
        registry = PolicyRegistry(DEPLOY_PRODUCTION)

        for intent in (Intent(action="deploy", target="staging"), Intent(action="rollback", target="production")):
            with self.subTest(intent=str(intent)):
                with self.assertRaises(LawmanError):
                    registry.path_for(intent)

    def test_the_rules_cannot_be_rewritten_after_they_are_read(self):
        registry = PolicyRegistry(DEPLOY_PRODUCTION)

        with self.assertRaises(TypeError):
            registry.policies["rollback"] = {"production": "policies/weak.rego"}
        with self.assertRaises(TypeError):
            registry.policies["deploy"]["production"] = "policies/weak.rego"
        with self.assertRaises(AttributeError):
            registry.policies = {"deploy": {"production": "policies/weak.rego"}}

    def test_the_registry_does_not_alias_the_caller_s_map(self):
        targets = {"production": "policies/deploy-production.rego"}
        policies = {"deploy": targets}
        registry = PolicyRegistry(policies)

        targets["production"] = "policies/weak.rego"
        policies["deploy"] = {"production": "policies/weak.rego"}

        self.assertEqual(registry.path_for(DEPLOY), "policies/deploy-production.rego")


if __name__ == "__main__":
    unittest.main()

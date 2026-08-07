"""Selection decides which rules apply. The requester does not."""

import json
import tempfile
import unittest
from pathlib import Path

from lawman import Contract, ContractRegistry, Intent, LawmanError, select_contract

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = Intent(action="deploy", target="production")
PRODUCTION_CONTRACT = Contract(requires=("tests_passed", "human_approved"))
DEPLOY_PRODUCTION = {"deploy": {"production": "contracts/deploy-production.json"}}


def write(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document if isinstance(document, str) else json.dumps(document), encoding="utf-8")
    return path


def policy(directory, registry, contracts=()):
    """Build a policy directory: a registry, plus contracts it can point at."""
    policy_directory = Path(directory) / ".lawman"
    write(policy_directory / "contracts.json", registry)
    for relative, contract in dict(contracts).items():
        write(policy_directory / relative, contract)
    return policy_directory


class SelectsTheContractTheRepositoryConfigured(unittest.TestCase):
    def test_deploy_to_production_resolves_to_the_checked_in_contract(self):
        contract = select_contract(DEPLOY, ROOT / ".lawman")

        self.assertEqual(contract, PRODUCTION_CONTRACT)

    def test_the_same_intent_always_selects_the_same_contract(self):
        selections = [select_contract(DEPLOY, ROOT / ".lawman") for _ in range(5)]

        self.assertEqual(len(set(selections)), 1)

    def test_a_contract_is_read_from_the_policy_directory_not_from_beside_the_intent(self):
        with tempfile.TemporaryDirectory() as directory:
            write(Path(directory) / "contract.json", {"requires": ["tests_passed"]})
            selected = select_contract(
                DEPLOY,
                policy(
                    directory,
                    DEPLOY_PRODUCTION,
                    {"contracts/deploy-production.json": {"requires": ["tests_passed", "human_approved"]}},
                ),
            )

        self.assertEqual(selected, PRODUCTION_CONTRACT)

    def test_one_action_can_govern_several_targets_independently(self):
        registry = ContractRegistry(
            {"deploy": {"production": "contracts/production.json", "staging": "contracts/staging.json"}}
        )

        self.assertEqual(registry.path_for(DEPLOY), "contracts/production.json")
        self.assertEqual(
            registry.path_for(Intent(action="deploy", target="staging")), "contracts/staging.json"
        )


class FailsClosedWhenItCannotFindTheRules(unittest.TestCase):
    """Not knowing the rules is not the same as applying them."""

    def test_an_intent_with_no_configured_contract_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            configured = policy(
                directory,
                DEPLOY_PRODUCTION,
                {"contracts/deploy-production.json": {"requires": ["tests_passed"]}},
            )

            with self.assertRaises(LawmanError) as refusal:
                select_contract(Intent(action="deploy", target="staging"), configured)

        self.assertIn("no contract is configured for deploy -> staging", str(refusal.exception))

    def test_an_unconfigured_action_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            configured = policy(
                directory,
                DEPLOY_PRODUCTION,
                {"contracts/deploy-production.json": {"requires": ["tests_passed"]}},
            )

            with self.assertRaises(LawmanError) as refusal:
                select_contract(Intent(action="rollback", target="production"), configured)

        self.assertIn("no contract is configured for rollback -> production", str(refusal.exception))

    def test_a_missing_registry_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(LawmanError) as refusal:
                select_contract(DEPLOY, Path(directory) / ".lawman")

        self.assertIn("cannot read contract registry", str(refusal.exception))

    def test_a_registry_that_is_not_valid_json_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(LawmanError) as refusal:
                select_contract(DEPLOY, policy(directory, "{ not json"))

        self.assertIn("not valid JSON", str(refusal.exception))

    def test_a_registry_that_is_not_nested_names_is_refused(self):
        for registry in (
            [],
            "deploy",
            {},
            {"deploy": "contracts/deploy-production.json"},
            {"deploy": {}},
            {"deploy": {"production": 7}},
        ):
            with self.subTest(registry=registry), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(LawmanError):
                    select_contract(DEPLOY, policy(directory, registry))

    def test_a_configured_contract_that_cannot_be_read_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            configured = policy(directory, DEPLOY_PRODUCTION)

            with self.assertRaises(LawmanError) as refusal:
                select_contract(DEPLOY, configured)

        self.assertIn("cannot read contract for deploy -> production", str(refusal.exception))

    def test_a_configured_contract_that_is_not_valid_json_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            configured = policy(
                directory, DEPLOY_PRODUCTION, {"contracts/deploy-production.json": "{ not json"}
            )

            with self.assertRaises(LawmanError) as refusal:
                select_contract(DEPLOY, configured)

        self.assertIn("not valid JSON", str(refusal.exception))

    def test_a_configured_contract_that_requires_nothing_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            configured = policy(
                directory, DEPLOY_PRODUCTION, {"contracts/deploy-production.json": {"requires": []}}
            )

            with self.assertRaises(LawmanError) as refusal:
                select_contract(DEPLOY, configured)

        self.assertIn("at least one requirement", str(refusal.exception))


class RefusesContractsTheRepositoryDoesNotOwn(unittest.TestCase):
    """A registry can only offer contracts inside its own policy directory."""

    def test_a_path_climbing_out_of_the_policy_directory_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            write(Path(directory) / "weak.json", {"requires": ["tests_passed"]})
            configured = policy(directory, {"deploy": {"production": "../weak.json"}})

            with self.assertRaises(LawmanError) as refusal:
                select_contract(DEPLOY, configured)

        self.assertIn("outside the policy directory", str(refusal.exception))

    def test_an_absolute_path_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            weak = write(Path(directory) / "weak.json", {"requires": ["tests_passed"]})
            configured = policy(directory, {"deploy": {"production": str(weak)}})

            with self.assertRaises(LawmanError) as refusal:
                select_contract(DEPLOY, configured)

        self.assertIn("outside the policy directory", str(refusal.exception))

    def test_a_symlink_out_of_the_policy_directory_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            weak = write(Path(directory) / "weak.json", {"requires": ["tests_passed"]})
            configured = policy(directory, DEPLOY_PRODUCTION)
            (configured / "contracts").mkdir(parents=True, exist_ok=True)
            (configured / "contracts" / "deploy-production.json").symlink_to(weak)

            with self.assertRaises(LawmanError) as refusal:
                select_contract(DEPLOY, configured)

        self.assertIn("outside the policy directory", str(refusal.exception))


class HoldsItsInvariantsWhenConstructedDirectly(unittest.TestCase):
    """Parsing is one way in, not the only way. The invariants belong to the type."""

    def test_a_registry_that_names_no_contracts_cannot_exist(self):
        for contracts in ({}, []):
            with self.subTest(contracts=contracts):
                with self.assertRaises(LawmanError):
                    ContractRegistry(contracts=contracts)

    def test_registry_must_be_a_map(self):
        for contracts in (None, "deploy", ["deploy"]):
            with self.subTest(contracts=contracts):
                with self.assertRaises(LawmanError):
                    ContractRegistry(contracts=contracts)

    def test_every_action_names_a_map_of_targets(self):
        for targets in ("contracts/deploy-production.json", None, 7, ["production"], {}):
            with self.subTest(targets=targets):
                with self.assertRaises(LawmanError):
                    ContractRegistry(contracts={"deploy": targets})

    def test_actions_and_targets_are_names(self):
        for contracts in (
            {"": {"production": "contracts/deploy-production.json"}},
            {"   ": {"production": "contracts/deploy-production.json"}},
            {"deploy": {"": "contracts/deploy-production.json"}},
            {"deploy": {"   ": "contracts/deploy-production.json"}},
        ):
            with self.subTest(contracts=contracts):
                with self.assertRaises(LawmanError):
                    ContractRegistry(contracts=contracts)

    def test_every_entry_names_a_contract_path(self):
        for path in ("", "   ", None, 7, ["contracts/deploy-production.json"]):
            with self.subTest(path=path):
                with self.assertRaises(LawmanError):
                    ContractRegistry(contracts={"deploy": {"production": path}})

    def test_an_unconfigured_intent_has_no_path(self):
        registry = ContractRegistry(DEPLOY_PRODUCTION)

        for intent in (Intent(action="deploy", target="staging"), Intent(action="rollback", target="production")):
            with self.subTest(intent=str(intent)):
                with self.assertRaises(LawmanError):
                    registry.path_for(intent)

    def test_the_rules_cannot_be_rewritten_after_they_are_read(self):
        registry = ContractRegistry(DEPLOY_PRODUCTION)

        with self.assertRaises(TypeError):
            registry.contracts["rollback"] = {"production": "contracts/weak.json"}
        with self.assertRaises(TypeError):
            registry.contracts["deploy"]["production"] = "contracts/weak.json"
        with self.assertRaises(AttributeError):
            registry.contracts = {"deploy": {"production": "contracts/weak.json"}}

    def test_the_registry_does_not_alias_the_caller_s_map(self):
        targets = {"production": "contracts/deploy-production.json"}
        contracts = {"deploy": targets}
        registry = ContractRegistry(contracts)

        targets["production"] = "contracts/weak.json"
        contracts["deploy"] = {"production": "contracts/weak.json"}

        self.assertEqual(registry.path_for(DEPLOY), "contracts/deploy-production.json")


if __name__ == "__main__":
    unittest.main()

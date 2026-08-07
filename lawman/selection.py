"""Intent -> Contract Selection -> Contract.

The requester chooses what it wants to do. The governed repository chooses the
rules it will be judged by. Nothing the requester supplies at runtime names the
contract (ADR 6).

Selection reads a registry checked into the repository being governed:
`.lawman/contracts.json`, mapping `action:target` to a contract file. Contract
paths are relative to the policy directory that holds the registry, and one
that resolves outside it is refused — the repository can only offer contracts
it owns.

Selection fails closed, and never as a denial. An unknown intent, an
unreadable registry, or an unreadable contract means Lawman could not find the
rules, not that it applied them. Both refuse the transition; only one of them
is a verdict.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .decision import Contract, Intent, LawmanError, _object, _require_name

POLICY_DIRECTORY = ".lawman"
"""Where a governed repository keeps its rules, relative to its root."""

REGISTRY_FILE = "contracts.json"
"""The registry, relative to the policy directory."""


@dataclass(frozen=True)
class ContractRegistry:
    """A governed repository's map from intent to authoritative contract.

    Keys are `action:target`. Values are contract paths relative to the policy
    directory. The map is copied and made read-only on construction, for the
    same reason evidence is: rules that could change after they were read would
    make decisions unrepeatable.
    """

    contracts: Mapping[str, str]

    def __post_init__(self) -> None:
        contracts = _object(self.contracts, "contract registry")
        if not contracts:
            raise LawmanError("contract registry names no contracts")
        for key, path in contracts.items():
            _require_name(key, "contract registry key")
            parts = key.split(":")
            if len(parts) != 2 or not all(part.strip() for part in parts):
                raise LawmanError(f"contract registry key {key!r} must be 'action:target'")
            _require_name(path, f"contract registry entry {key!r}")
        object.__setattr__(self, "contracts", MappingProxyType(dict(contracts)))

    @classmethod
    def from_dict(cls, data: Any) -> ContractRegistry:
        """A registry document is the map itself."""
        return cls(contracts=data)

    def path_for(self, intent: Intent) -> str:
        key = f"{intent.action}:{intent.target}"
        if key not in self.contracts:
            raise LawmanError(f"no contract is configured for {intent}")
        return self.contracts[key]


def select_contract(intent: Intent, policy: Path | str = POLICY_DIRECTORY) -> Contract:
    """Resolve the contract an intent will be judged by.

    `policy` is the governed repository's policy directory, defaulting to
    `.lawman` in the current working directory — so running Lawman from a
    repository root governs that repository. The intent is the only input here,
    and it cannot name a file.
    """
    policy = Path(policy)
    registry = ContractRegistry.from_dict(_read_json(policy / REGISTRY_FILE, "contract registry"))
    contract = _inside(policy, registry.path_for(intent))
    return Contract.from_dict(_read_json(contract, f"contract for {intent}"))


def _inside(policy: Path, relative: str) -> Path:
    """Contracts live inside the policy directory. Anything else is not ours.

    Resolving first means this refuses an absolute path, a `..` climb, and a
    symlink pointing out of the directory, without reasoning about each.
    """
    contract = (policy / relative).resolve()
    if not contract.is_relative_to(policy.resolve()):
        raise LawmanError(f"contract path {relative!r} is outside the policy directory {policy}")
    return contract


def _read_json(path: Path | str, label: str) -> Any:
    """Read a JSON document, or say why it could not be read."""
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as error:
        raise LawmanError(f"cannot read {label} at {path}: {error.strerror}") from error
    except json.JSONDecodeError as error:
        raise LawmanError(f"{label} at {path} is not valid JSON: {error}") from error

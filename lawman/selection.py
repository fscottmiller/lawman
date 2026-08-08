"""Intent -> Policy Selection -> Policy.

The requester chooses what it wants to do. The governed repository chooses the
rules it will be judged by. Nothing the requester supplies at runtime names the
policy (ADR 6).

Selection reads a registry checked into the repository being governed:
`.lawman/policies.json`, nested the way an intent is shaped — action, then
target — so it says which policy governs `deploy -> production` without giving
that pair a name of its own. Policy paths are relative to the policy directory
that holds the registry, and one that resolves outside it is refused — the
repository can only offer policies it owns.

Selection resolves a file and stops. The file is Rego, and OPA is what reads
Rego (ADR 9). Nothing here parses a policy, so nothing here can quietly grow
into a second opinion about what one means.

Selection fails closed, and never as a denial. An unknown intent, an unreadable
registry, or a missing policy means Lawman could not find the rules, not that
it applied them. Both refuse the transition; only one of them is a verdict.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .decision import Intent, LawmanError, _object, _require_name

POLICY_DIRECTORY = ".lawman"
"""Where a governed repository keeps its rules, relative to its root."""

REGISTRY_FILE = "policies.json"
"""The registry, relative to the policy directory."""


@dataclass(frozen=True)
class PolicyRegistry:
    """A governed repository's map from intent to authoritative policy.

    Nested by action, then target, mirroring the intent it selects on. Values
    are policy paths relative to the policy directory:

        {"deploy": {"production": "policies/deploy-production.rego"}}

    Both levels are copied and made read-only on construction, for the same
    reason evidence is: rules that could change after they were read would make
    decisions unrepeatable.
    """

    policies: Mapping[str, Mapping[str, str]]

    def __post_init__(self) -> None:
        actions = _object(self.policies, "policy registry")
        if not actions:
            raise LawmanError("policy registry names no policies")
        by_action: dict[str, Mapping[str, str]] = {}
        for action, targets in actions.items():
            _require_name(action, "policy registry action")
            targets = _object(targets, f"policy registry action {action!r}")
            if not targets:
                raise LawmanError(f"policy registry action {action!r} names no targets")
            for target, path in targets.items():
                _require_name(target, f"policy registry target under {action!r}")
                _require_name(path, f"policy registry entry {action!r} -> {target!r}")
            by_action[action] = MappingProxyType(dict(targets))
        object.__setattr__(self, "policies", MappingProxyType(by_action))

    @classmethod
    def from_dict(cls, data: Any) -> PolicyRegistry:
        """A registry document is the map itself."""
        return cls(policies=data)

    def path_for(self, intent: Intent) -> str:
        targets = self.policies.get(intent.action, {})
        if intent.target not in targets:
            raise LawmanError(f"no policy is configured for {intent}")
        return targets[intent.target]


def select_policy(intent: Intent, policy: Path | str = POLICY_DIRECTORY) -> Path:
    """Resolve the policy file an intent will be judged by.

    `policy` is the governed repository's policy directory, defaulting to
    `.lawman` in the current working directory — so running Lawman from a
    repository root governs that repository. The intent is the only input here,
    and it cannot name a file.
    """
    policy = Path(policy)
    registry = PolicyRegistry.from_dict(_read_json(policy / REGISTRY_FILE, "policy registry"))
    selected = _inside(policy, registry.path_for(intent))
    if not selected.is_file():
        raise LawmanError(f"cannot read policy for {intent} at {selected}: no such file")
    return selected


def _inside(policy: Path, relative: str) -> Path:
    """Policies live inside the policy directory. Anything else is not ours.

    Resolving first means this refuses an absolute path, a `..` climb, and a
    symlink pointing out of the directory, without reasoning about each.
    """
    selected = (policy / relative).resolve()
    if not selected.is_relative_to(policy.resolve()):
        raise LawmanError(f"policy path {relative!r} is outside the policy directory {policy}")
    return selected


def _read_json(path: Path | str, label: str) -> Any:
    """Read a JSON document, or say why it could not be read."""
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as error:
        raise LawmanError(f"cannot read {label} at {path}: {error.strerror}") from error
    except json.JSONDecodeError as error:
        raise LawmanError(f"{label} at {path} is not valid JSON: {error}") from error

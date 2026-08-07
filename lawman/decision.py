"""Intent -> Contract -> Evidence -> Decision.

The first executable slice of Lawman. It decides whether an intent may
transition, and says why. It does not do the work, and it does not perform the
transition.

Two rules shape everything below. The argument for each is in docs/decisions/.

* A requirement is a name. Evidence proves it true or proves it false, and
  nothing richer is expressible (ADR 3).
* Silence is not proof, so an absent fact denies exactly like a false one, and
  a contract requiring nothing is a misconfiguration rather than a permit
  (ADR 4).

Invariants live in `__post_init__`, not in the parsers, so an invalid Intent,
Contract, or Evidence cannot be constructed at all and `decide()` has nothing
left to distrust. `from_dict` only unwraps JSON.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class LawmanError(ValueError):
    """Input could not be understood. Lawman refuses to guess."""


@dataclass(frozen=True)
class Intent:
    """The consequential action being requested."""

    action: str
    target: str

    def __post_init__(self) -> None:
        _require_name(self.action, "intent.action")
        _require_name(self.target, "intent.target")

    @classmethod
    def from_dict(cls, data: Any) -> Intent:
        fields = _object(data, "intent")
        return cls(action=fields.get("action"), target=fields.get("target"))

    def __str__(self) -> str:
        return f"{self.action} -> {self.target}"


@dataclass(frozen=True)
class Contract:
    """What must be proven before an intent may transition."""

    requires: tuple[str, ...]

    def __post_init__(self) -> None:
        if isinstance(self.requires, str) or not isinstance(self.requires, (list, tuple)):
            raise LawmanError("contract.requires must be a list of requirement names")
        if not self.requires:
            raise LawmanError("contract.requires must name at least one requirement")
        for requirement in self.requires:
            _require_name(requirement, "contract.requires[]")
        object.__setattr__(self, "requires", tuple(dict.fromkeys(self.requires)))

    @classmethod
    def from_dict(cls, data: Any) -> Contract:
        return cls(requires=_object(data, "contract").get("requires"))


@dataclass(frozen=True)
class Evidence:
    """Facts presented to Lawman. A fact is proven true or proven false."""

    facts: Mapping[str, bool]

    def __post_init__(self) -> None:
        facts = _object(self.facts, "evidence")
        for name, proof in facts.items():
            _require_name(name, "evidence key")
            if not isinstance(proof, bool):
                raise LawmanError(f"evidence.{name} must be true or false, not {proof!r}")
        object.__setattr__(self, "facts", dict(facts))

    @classmethod
    def from_dict(cls, data: Any) -> Evidence:
        """An evidence document is the fact map itself."""
        return cls(facts=data)


@dataclass(frozen=True)
class Decision:
    """The deterministic verdict, and the reasoning behind it."""

    allowed: bool
    intent: Intent
    satisfied: tuple[str, ...]
    failed: tuple[str, ...]
    unproven: tuple[str, ...]
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "explanation": self.explanation,
            "intent": {"action": self.intent.action, "target": self.intent.target},
            "satisfied": list(self.satisfied),
            "failed": list(self.failed),
            "unproven": list(self.unproven),
        }


def decide(intent: Intent, contract: Contract, evidence: Evidence) -> Decision:
    """Evaluate evidence against a contract. Same inputs, same decision, always."""
    satisfied: list[str] = []
    failed: list[str] = []
    unproven: list[str] = []
    for requirement in contract.requires:
        if requirement not in evidence.facts:
            unproven.append(requirement)
        elif evidence.facts[requirement]:
            satisfied.append(requirement)
        else:
            failed.append(requirement)

    allowed = not failed and not unproven
    return Decision(
        allowed=allowed,
        intent=intent,
        satisfied=tuple(satisfied),
        failed=tuple(failed),
        unproven=tuple(unproven),
        explanation=_explain(allowed, intent, satisfied, failed, unproven),
    )


def _explain(
    allowed: bool,
    intent: Intent,
    satisfied: list[str],
    failed: list[str],
    unproven: list[str],
) -> str:
    parts = [f"{'Allowed' if allowed else 'Denied'}: {intent}."]
    for label, requirements in (("Failed", failed), ("Unproven", unproven), ("Satisfied", satisfied)):
        if requirements:
            parts.append(f"{label}: {', '.join(requirements)}.")
    return " ".join(parts)


def _object(data: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(data, dict):
        raise LawmanError(f"{label} must be an object")
    return data


def _require_name(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise LawmanError(f"{label} must be a non-empty string")

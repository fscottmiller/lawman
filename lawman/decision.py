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

    @classmethod
    def from_dict(cls, data: Any) -> Intent:
        fields = _object(data, "intent")
        return cls(
            action=_name(fields.get("action"), "intent.action"),
            target=_name(fields.get("target"), "intent.target"),
        )

    def __str__(self) -> str:
        return f"{self.action} -> {self.target}"


@dataclass(frozen=True)
class Contract:
    """What must be proven before an intent may transition."""

    requires: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: Any) -> Contract:
        fields = _object(data, "contract")
        requires = fields.get("requires")
        if not isinstance(requires, list) or not requires:
            raise LawmanError("contract.requires must be a non-empty list of requirement names")
        names = [_name(item, "contract.requires[]") for item in requires]
        return cls(requires=tuple(dict.fromkeys(names)))


@dataclass(frozen=True)
class Evidence:
    """Facts presented to Lawman. A fact is proven true or proven false."""

    facts: Mapping[str, bool]

    @classmethod
    def from_dict(cls, data: Any) -> Evidence:
        facts = _object(data, "evidence")
        for name, proof in facts.items():
            if not isinstance(proof, bool):
                raise LawmanError(f"evidence.{name} must be true or false, not {proof!r}")
        return cls(facts=dict(facts))


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


def _name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LawmanError(f"{label} must be a non-empty string")
    return value

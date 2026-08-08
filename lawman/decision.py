"""Intent, evidence, and the decision a policy reached.

The transition domain, and nothing else. Lawman no longer interprets what a
transition requires — policy does, OPA evaluates it, and `opa.py` is the seam
(ADR 9). What is left here is the vocabulary on both sides of that seam: what
goes to OPA, and what may come back.

Invariants live in `__post_init__`, not in the parsers, so an invalid Intent,
Evidence, or Decision cannot be constructed at all. `from_dict` only unwraps
JSON — it never supplies a default for a key that was absent, because deciding
that a missing key means an empty one is exactly the guess ADR 4 forbids.

That is why the values pulled out of a document are annotated `Any`. The field
types describe what a validated object holds; construction accepts whatever
the JSON contained, and rejects it.

Evidence is the one thing Lawman deliberately does not read. A fact's meaning
belongs to the policy, so evidence is checked for shape and carried through
whole: no required keys, no booleans, no interpretation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any


class LawmanError(ValueError):
    """Input or configuration could not be understood. Lawman refuses to guess.

    Never a denial. A denial is a `Decision` that a policy reached.
    """


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
        action: Any = fields.get("action")
        target: Any = fields.get("target")
        return cls(action=action, target=target)

    def to_dict(self) -> dict[str, str]:
        return {"action": self.action, "target": self.target}

    def __str__(self) -> str:
        return f"{self.action} -> {self.target}"


@dataclass(frozen=True)
class Evidence:
    """Facts presented to Lawman, for the policy to read.

    A JSON object, and that is the whole specification. Lawman checks that it
    is an object with named keys so it can be handed to OPA as one document; it
    does not check a value's type, and it does not know which names matter.

    The mapping is copied and made read-only on construction. Evidence that
    could change after it was presented would make decisions unrepeatable.
    """

    facts: Mapping[str, Any]

    def __post_init__(self) -> None:
        facts = _object(self.facts, "evidence")
        for name in facts:
            _require_name(name, "evidence key")
        object.__setattr__(self, "facts", MappingProxyType(dict(facts)))

    @classmethod
    def from_dict(cls, data: Any) -> Evidence:
        """An evidence document is the fact map itself."""
        return cls(facts=data)


@dataclass(frozen=True)
class Decision:
    """A policy's verdict, and the reasons the policy gave for it.

    Every decision carries at least one reason, including an allowed one. A
    permit nobody can explain is the failure mode this whole tool exists to
    prevent, and OPA can say why as easily as it can say yes.

    Reasons are kept in the order the policy emitted them, with duplicates
    intact. They are prose written by the policy author, not names Lawman may
    reorder or fold together.
    """

    allowed: bool
    intent: Intent
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.allowed, bool):
            raise LawmanError(f"policy decision.allowed must be true or false, not {self.allowed!r}")
        if not isinstance(self.intent, Intent):
            raise LawmanError("policy decision must name the intent it decided")
        if isinstance(self.reasons, str) or not isinstance(self.reasons, (list, tuple)):
            raise LawmanError("policy decision.reasons must be a list of reasons")
        if not self.reasons:
            raise LawmanError("policy decision.reasons must give at least one reason")
        for reason in self.reasons:
            _require_name(reason, "policy decision.reasons[]")
        object.__setattr__(self, "reasons", tuple(self.reasons))

    @classmethod
    def from_dict(cls, data: Any, intent: Intent) -> Decision:
        """Read what OPA returned, or refuse it.

        Unknown fields are refused rather than ignored. A policy that returns
        something Lawman does not report is a policy whose author believes it
        is being read, and quietly dropping it is how a requirement disappears.
        """
        fields = _object(data, "policy decision")
        unknown = sorted(set(fields) - {"allowed", "reasons"})
        if unknown:
            raise LawmanError(f"policy decision has fields Lawman does not understand: {', '.join(unknown)}")
        allowed: Any = fields.get("allowed")
        reasons: Any = fields.get("reasons")
        return cls(allowed=allowed, intent=intent, reasons=reasons)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "intent": self.intent.to_dict(),
            "reasons": list(self.reasons),
        }


def _object(data: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(data, Mapping):
        raise LawmanError(f"{label} must be an object")
    return data


def _require_name(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise LawmanError(f"{label} must be a non-empty string")

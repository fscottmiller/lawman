"""Work Contract -> Evidence -> Work Contract Result.

This answers whether one piece of work met its acceptance criteria. It does
not decide whether any transition is allowed (ADR 8).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .decision import LawmanError, _object, _require_name

CriterionStatus = Literal["proven", "failed", "unproven"]


@dataclass(frozen=True)
class AcceptanceCriterion:
    id: str
    description: str

    def __post_init__(self) -> None:
        _require_name(self.id, "work contract criterion.id")
        _require_name(self.description, f"work contract criterion {self.id!r}.description")

    @classmethod
    def from_dict(cls, data: Any) -> AcceptanceCriterion:
        fields = _object(data, "work contract criterion")
        criterion_id: Any = fields.get("id")
        description: Any = fields.get("description")
        return cls(id=criterion_id, description=description)


@dataclass(frozen=True)
class WorkContract:
    criteria: tuple[AcceptanceCriterion, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.criteria, (list, tuple)):
            raise LawmanError("work contract.criteria must be a list of criteria")
        if not self.criteria:
            raise LawmanError("work contract must name at least one criterion")
        if not all(isinstance(criterion, AcceptanceCriterion) for criterion in self.criteria):
            raise LawmanError("work contract.criteria must contain acceptance criteria")
        ids = [criterion.id for criterion in self.criteria]
        if len(ids) != len(set(ids)):
            raise LawmanError("work contract criterion IDs must be unique")
        object.__setattr__(self, "criteria", tuple(self.criteria))

    @classmethod
    def from_dict(cls, data: Any) -> WorkContract:
        criteria: Any = _object(data, "work contract").get("criteria")
        if not isinstance(criteria, list):
            raise LawmanError("work contract.criteria must be a list of criteria")
        return cls(criteria=tuple(AcceptanceCriterion.from_dict(item) for item in criteria))


@dataclass(frozen=True)
class CriterionEvidence:
    criterion_id: str
    source: str
    passed: bool

    def __post_init__(self) -> None:
        _require_name(self.criterion_id, "work evidence criterion_id")
        _require_name(self.source, f"work evidence for {self.criterion_id!r}.source")
        if not isinstance(self.passed, bool):
            raise LawmanError(f"work evidence for {self.criterion_id!r}.passed must be true or false")

    @classmethod
    def from_dict(cls, data: Any) -> CriterionEvidence:
        fields = _object(data, "work evidence entry")
        criterion_id: Any = fields.get("criterion_id")
        source: Any = fields.get("source")
        passed: Any = fields.get("passed")
        return cls(criterion_id=criterion_id, source=source, passed=passed)


@dataclass(frozen=True)
class WorkEvidence:
    entries: tuple[CriterionEvidence, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.entries, (list, tuple)):
            raise LawmanError("work evidence.evidence must be a list")
        if not all(isinstance(entry, CriterionEvidence) for entry in self.entries):
            raise LawmanError("work evidence.evidence must contain evidence entries")
        ids = [entry.criterion_id for entry in self.entries]
        if len(ids) != len(set(ids)):
            raise LawmanError("work evidence must not repeat a criterion")
        object.__setattr__(self, "entries", tuple(self.entries))

    @classmethod
    def from_dict(cls, data: Any) -> WorkEvidence:
        entries: Any = _object(data, "work evidence").get("evidence")
        if not isinstance(entries, list):
            raise LawmanError("work evidence.evidence must be a list")
        return cls(entries=tuple(CriterionEvidence.from_dict(item) for item in entries))


@dataclass(frozen=True)
class CriterionResult:
    criterion: AcceptanceCriterion
    evidence: CriterionEvidence | None

    def __post_init__(self) -> None:
        if not isinstance(self.criterion, AcceptanceCriterion):
            raise LawmanError("criterion result must name an acceptance criterion")
        if self.evidence is not None and not isinstance(self.evidence, CriterionEvidence):
            raise LawmanError("criterion result evidence must be criterion evidence or absent")
        if self.evidence is not None and self.evidence.criterion_id != self.criterion.id:
            raise LawmanError("criterion result evidence must reference its criterion")

    @property
    def status(self) -> CriterionStatus:
        if self.evidence is None:
            return "unproven"
        return "proven" if self.evidence.passed else "failed"

    @property
    def source(self) -> str | None:
        return None if self.evidence is None else self.evidence.source

    @property
    def explanation(self) -> str:
        if self.status == "unproven":
            return "Unproven: no evidence was provided."
        if self.status == "failed":
            return f"Failed: {self.source} reported failure."
        return f"Proven by {self.source}."

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.criterion.id,
            "description": self.criterion.description,
            "status": self.status,
            "source": self.source,
            "explanation": self.explanation,
        }


@dataclass(frozen=True)
class WorkContractResult:
    criteria: tuple[CriterionResult, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.criteria, (list, tuple)) or not self.criteria:
            raise LawmanError("work contract result must contain criterion results")
        if not all(isinstance(result, CriterionResult) for result in self.criteria):
            raise LawmanError("work contract result must contain criterion results")
        ids = [result.criterion.id for result in self.criteria]
        if len(ids) != len(set(ids)):
            raise LawmanError("work contract result criterion IDs must be unique")
        object.__setattr__(self, "criteria", tuple(self.criteria))

    @property
    def satisfied(self) -> bool:
        return all(result.status == "proven" for result in self.criteria)

    def to_dict(self) -> dict[str, Any]:
        return {
            "satisfied": self.satisfied,
            "criteria": [result.to_dict() for result in self.criteria],
        }


def evaluate_work_contract(contract: WorkContract, evidence: WorkEvidence) -> WorkContractResult:
    """Account for every criterion in contract order, or refuse malformed evidence."""
    if not isinstance(contract, WorkContract) or not isinstance(evidence, WorkEvidence):
        raise LawmanError("work contract evaluation requires a work contract and work evidence")

    criterion_ids = {criterion.id for criterion in contract.criteria}
    unknown = [entry.criterion_id for entry in evidence.entries if entry.criterion_id not in criterion_ids]
    if unknown:
        raise LawmanError(f"work evidence references unknown criteria: {', '.join(unknown)}")

    by_criterion = {entry.criterion_id: entry for entry in evidence.entries}
    return WorkContractResult(
        criteria=tuple(CriterionResult(criterion, by_criterion.get(criterion.id)) for criterion in contract.criteria)
    )

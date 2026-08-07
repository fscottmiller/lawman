"""Lawman: prove work, decide transitions, and say why."""

from .decision import Contract, Decision, Evidence, Intent, LawmanError, decide
from .selection import ContractRegistry, select_contract
from .work import (
    AcceptanceCriterion,
    CriterionEvidence,
    CriterionResult,
    WorkContract,
    WorkContractResult,
    WorkEvidence,
    evaluate_work_contract,
)

__all__ = [
    "AcceptanceCriterion",
    "Contract",
    "ContractRegistry",
    "CriterionEvidence",
    "CriterionResult",
    "Decision",
    "Evidence",
    "Intent",
    "LawmanError",
    "WorkContract",
    "WorkContractResult",
    "WorkEvidence",
    "decide",
    "evaluate_work_contract",
    "select_contract",
]

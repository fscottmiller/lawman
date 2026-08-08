"""Lawman: prove work, decide transitions, and say why."""

from .decision import Decision, Evidence, Intent, LawmanError
from .github import ContractSource, IssueReference, issue_contract
from .opa import evaluate_policy
from .selection import PolicyRegistry, select_policy
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
    "ContractSource",
    "CriterionEvidence",
    "CriterionResult",
    "Decision",
    "Evidence",
    "Intent",
    "IssueReference",
    "LawmanError",
    "PolicyRegistry",
    "WorkContract",
    "WorkContractResult",
    "WorkEvidence",
    "evaluate_policy",
    "evaluate_work_contract",
    "issue_contract",
    "select_policy",
]

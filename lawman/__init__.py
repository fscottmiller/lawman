"""Lawman: prove work, decide transitions, and say why."""

from .ci import ExecutionContext, JUnitCase, JUnitReport, actions_evidence
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
    "ExecutionContext",
    "Intent",
    "IssueReference",
    "JUnitCase",
    "JUnitReport",
    "LawmanError",
    "PolicyRegistry",
    "WorkContract",
    "WorkContractResult",
    "WorkEvidence",
    "actions_evidence",
    "evaluate_policy",
    "evaluate_work_contract",
    "issue_contract",
    "select_policy",
]

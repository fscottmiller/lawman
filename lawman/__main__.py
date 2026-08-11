"""Command line entry point: python -m lawman.

Both commands exit 0 for success, 1 for a valid negative result, and 2 when
Lawman cannot reach a result because the input or governing rules are invalid.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .ci import ExecutionContext, actions_evidence
from .decision import Evidence, Intent, LawmanError
from .github import TOKEN_VARIABLE, ContractSource, issue_contract
from .opa import DECISION_DOCUMENT, evaluate_policy
from .selection import POLICY_DIRECTORY, REGISTRY_FILE, _read_json, select_policy
from .work import WorkContract, WorkEvidence, evaluate_work_contract


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == ["work"]:
        return _work(arguments[1:])
    return _transition(arguments)


def _transition(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="lawman",
        description="Decide whether an intent may transition, given evidence.",
        epilog=(
            f"The policy is selected from {POLICY_DIRECTORY}/{REGISTRY_FILE} in the current "
            f"directory and evaluated by OPA as {DECISION_DOCUMENT}. Neither is supplied by "
            "the caller. Run 'lawman work --help' to evaluate a work contract."
        ),
    )
    parser.add_argument("--intent", required=True, metavar="PATH", help="JSON file: the requested action")
    parser.add_argument("--evidence", required=True, metavar="PATH", help="JSON file: what is proven")
    args = parser.parse_args(argv)

    try:
        intent = Intent.from_dict(_read_json(args.intent, "intent"))
        decision = evaluate_policy(
            intent,
            select_policy(intent),
            Evidence.from_dict(_read_json(args.evidence, "evidence")),
        )
    except LawmanError as error:
        print(f"lawman: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("lawman: interrupted before a policy decision was reached", file=sys.stderr)
        return 2

    print(json.dumps(decision.to_dict(), indent=2))
    return 0 if decision.allowed else 1


def _work(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="lawman work",
        description="Evaluate a work contract.",
        epilog=(
            "The contract comes from one local file or one canonical GitHub issue URL. A GitHub "
            f"read is authenticated with {TOKEN_VARIABLE} from the environment; no argument "
            "accepts a token. --junit derives the evidence from the tests of the current GitHub "
            "Actions execution, and requires --issue. Satisfying a work contract does not "
            "authorize a transition."
        ),
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--contract", metavar="PATH", help="JSON file: acceptance criteria")
    source.add_argument("--issue", metavar="URL", help="GitHub issue: the authoritative contract")
    proof = parser.add_mutually_exclusive_group(required=True)
    proof.add_argument("--evidence", metavar="PATH", help="JSON file: criterion evidence")
    proof.add_argument("--junit", metavar="PATH", help="JUnit XML: this execution's test results")
    args = parser.parse_args(argv)

    try:
        contract, source_identity = _contract(args)
        evidence, execution = _evidence(args, contract)
        result = evaluate_work_contract(contract, evidence)
    except LawmanError as error:
        print(f"lawman: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("lawman: interrupted before a work contract result was reached", file=sys.stderr)
        return 2

    document = result.to_dict()
    if execution is not None:
        document = {"execution": execution.to_dict(), **document}
    if source_identity is not None:
        document = {"contract_source": source_identity.to_dict(), **document}
    print(json.dumps(document, indent=2))
    return 0 if result.satisfied else 1


def _contract(args: argparse.Namespace) -> tuple[WorkContract, ContractSource | None]:
    """Read the contract from wherever the caller pointed, and say where that was.

    A local file identifies itself: the caller is holding it. A GitHub issue
    does not, so a GitHub-backed result carries the source it was read from —
    which issue, and which version of its contract.
    """
    if args.issue is not None:
        return issue_contract(args.issue)
    return WorkContract.from_dict(_read_json(args.contract, "work contract")), None


def _evidence(args: argparse.Namespace, contract: WorkContract) -> tuple[WorkEvidence, ExecutionContext | None]:
    """Read the evidence the caller wrote, or derive it from this execution.

    Derived evidence says which execution produced it; a document the caller
    presented cannot, so it carries no execution at all rather than one Lawman
    made up. `--junit` requires `--issue` because deriving proof is only worth
    anything against criteria the claimant did not also write (ADR 12).
    """
    if args.junit is None:
        return WorkEvidence.from_dict(_read_json(args.evidence, "work evidence")), None
    if args.issue is None:
        raise LawmanError("--junit derives evidence for the issue that ordered the work, so it requires --issue")
    return actions_evidence(contract, args.junit)


if __name__ == "__main__":
    sys.exit(main())

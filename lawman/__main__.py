"""Command line entry point: python -m lawman.

Both commands exit 0 for success, 1 for a valid negative result, and 2 when
Lawman cannot reach a result because the input or governing rules are invalid.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .decision import Evidence, Intent, LawmanError, decide
from .selection import POLICY_DIRECTORY, REGISTRY_FILE, _read_json, select_contract
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
            f"The contract is selected from {POLICY_DIRECTORY}/{REGISTRY_FILE} in the current "
            "directory, not supplied by the caller. "
            "Run 'lawman work --help' to evaluate a work contract."
        ),
    )
    parser.add_argument("--intent", required=True, metavar="PATH", help="JSON file: the requested action")
    parser.add_argument("--evidence", required=True, metavar="PATH", help="JSON file: what is proven")
    args = parser.parse_args(argv)

    try:
        intent = Intent.from_dict(_read_json(args.intent, "intent"))
        decision = decide(
            intent,
            select_contract(intent),
            Evidence.from_dict(_read_json(args.evidence, "evidence")),
        )
    except LawmanError as error:
        print(f"lawman: {error}", file=sys.stderr)
        return 2

    print(json.dumps(decision.to_dict(), indent=2))
    return 0 if decision.allowed else 1


def _work(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="lawman work", description="Evaluate a work contract.")
    parser.add_argument("--contract", required=True, metavar="PATH", help="JSON file: acceptance criteria")
    parser.add_argument("--evidence", required=True, metavar="PATH", help="JSON file: criterion evidence")
    args = parser.parse_args(argv)

    try:
        result = evaluate_work_contract(
            WorkContract.from_dict(_read_json(args.contract, "work contract")),
            WorkEvidence.from_dict(_read_json(args.evidence, "work evidence")),
        )
    except LawmanError as error:
        print(f"lawman: {error}", file=sys.stderr)
        return 2

    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.satisfied else 1


if __name__ == "__main__":
    sys.exit(main())

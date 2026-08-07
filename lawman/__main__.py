"""Command line entry point: python -m lawman

The caller supplies what it wants to do and what it has proven. It does not
supply the contract — Lawman selects that from the repository it is run in, so
there is deliberately no `--contract` flag (ADR 6).

Exit codes are the useful part of the interface (ADR 5):
    0  transition allowed
    1  transition denied
    2  input, or the governing contract, could not be understood
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .decision import Evidence, Intent, LawmanError, decide
from .selection import (POLICY_DIRECTORY, REGISTRY_FILE, _read_json,
                        select_contract)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lawman",
        description="Decide whether an intent may transition, given evidence.",
        epilog=(
            f"The contract is selected from {POLICY_DIRECTORY}/{REGISTRY_FILE} in the current "
            "directory, not supplied by the caller."
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


if __name__ == "__main__":
    sys.exit(main())

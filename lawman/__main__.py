"""Command line entry point: python -m lawman

Exit codes are the useful part of the interface:
    0  transition allowed
    1  transition denied
    2  input could not be understood
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Sequence

from .decision import Contract, Evidence, Intent, LawmanError, decide


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lawman",
        description="Decide whether an intent may transition, given a contract and evidence.",
    )
    parser.add_argument("--intent", required=True, metavar="PATH", help="JSON file: the requested action")
    parser.add_argument("--contract", required=True, metavar="PATH", help="JSON file: what must be proven")
    parser.add_argument("--evidence", required=True, metavar="PATH", help="JSON file: what is proven")
    args = parser.parse_args(argv)

    try:
        decision = decide(
            Intent.from_dict(_load(args.intent, "intent")),
            Contract.from_dict(_load(args.contract, "contract")),
            Evidence.from_dict(_load(args.evidence, "evidence")),
        )
    except LawmanError as error:
        print(f"lawman: {error}", file=sys.stderr)
        return 2

    print(json.dumps(decision.to_dict(), indent=2))
    return 0 if decision.allowed else 1


def _load(path: str, label: str) -> Any:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as error:
        raise LawmanError(f"cannot read {label} at {path}: {error.strerror}") from error
    except json.JSONDecodeError as error:
        raise LawmanError(f"{label} at {path} is not valid JSON: {error}") from error


if __name__ == "__main__":
    sys.exit(main())

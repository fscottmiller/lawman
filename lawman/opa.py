"""Policy -> OPA -> Decision.

Lawman does not decide transitions. It hands OPA the selected policy and one
input document, and validates what comes back (ADR 9). There is no Python
evaluator behind this: without OPA, Lawman reaches no decision at all.

Three things are fixed, and none of them is an input:

* the executable — `opa`, found on PATH, named by no flag;
* the query — `data.lawman.decision`, the one document every selected policy
  exposes;
* the input document — the validated intent, and the requester's evidence
  passed through whole.

Everything that is not exactly one well-formed decision is a refusal, not a
denial. A missing executable, a failed evaluation, unreadable output, an
undefined document, or a decision Lawman cannot read all mean the same thing:
no verdict was reached. Exit 2, never exit 1.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .decision import Decision, Evidence, Intent, LawmanError, _object

EXECUTABLE = "opa"
"""Found on PATH. Lawman takes no argument naming it, and reads no override."""

DECISION_DOCUMENT = "data.lawman.decision"
"""The one document Lawman asks every policy for."""

TIMEOUT_SECONDS = 30.0
"""How long a decision may take before Lawman stops waiting for one.

Fixed, and generous: evaluating one local policy is milliseconds, so this is
only ever reached by an OPA that has wedged. It is not configurable, because a
caller who can raise the bound can hold the gate open indefinitely, and a gate
that never answers is a gate nobody can enforce.
"""


def evaluate_policy(intent: Intent, policy: Path, evidence: Evidence) -> Decision:
    """Ask OPA what `policy` decides about `intent`, given `evidence`."""
    document = {"intent": intent.to_dict(), "evidence": evidence.to_dict()}
    return Decision.from_dict(_value(_run(policy, document), policy), intent)


def _run(policy: Path, document: dict[str, Any]) -> Any:
    """Evaluate the policy in a real OPA process, and read its JSON output.

    Bytes in, bytes out. Decoding happens here, inside the guard, because an
    OPA that answers in something other than UTF-8 has produced unreadable
    output — a refusal — and letting `UnicodeDecodeError` escape a governance
    gate would turn that refusal into a traceback.
    """
    command = [EXECUTABLE, "eval", "--format", "json", "--data", str(policy), "--stdin-input", DECISION_DOCUMENT]
    try:
        completed = subprocess.run(
            command,
            input=json.dumps(document).encode("utf-8"),
            capture_output=True,
            timeout=TIMEOUT_SECONDS,
        )
    except OSError as error:
        raise LawmanError(f"cannot run the OPA executable {EXECUTABLE!r}: {error.strerror}") from error
    except subprocess.TimeoutExpired as error:
        raise LawmanError(f"OPA did not decide {policy} within {TIMEOUT_SECONDS:g} seconds") from error

    stdout, stderr = _text(completed.stdout), _text(completed.stderr)
    try:
        output = None if stdout is None else json.loads(stdout)
    except json.JSONDecodeError:
        output = None

    if completed.returncode != 0:
        raise LawmanError(f"OPA could not evaluate {policy}: {_diagnostic(output, stderr, completed.returncode)}")
    if stdout is None:
        raise LawmanError(f"OPA output for {policy} is not readable UTF-8")
    if output is None:
        raise LawmanError(f"OPA output for {policy} is not valid JSON")
    return output


def _text(raw: bytes) -> str | None:
    """OPA speaks UTF-8. Anything else is unreadable, not a decision."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _diagnostic(output: Any, stderr: str | None, returncode: int) -> str:
    """Say why OPA failed, in one line. OPA reports its own errors on stdout."""
    errors = output.get("errors") if isinstance(output, Mapping) else None
    if isinstance(errors, list) and errors:
        message = errors[0].get("message") if isinstance(errors[0], Mapping) else None
        if isinstance(message, str) and message.strip():
            return message.strip()
    complaint = (stderr or "").strip()
    return complaint.splitlines()[0].strip() if complaint else f"exit status {returncode}"


def _value(output: Any, policy: Path) -> Any:
    """Unwrap OPA's result envelope, insisting on exactly one decision."""
    results = _object(output, "OPA output").get("result")
    if results is None:
        raise LawmanError(f"{DECISION_DOCUMENT} is undefined in {policy}")
    expressions = _object(_one(results, policy), "OPA result").get("expressions")
    expression = _object(_one(expressions, policy), "OPA expression")
    if "value" not in expression:
        raise LawmanError(f"OPA returned no value for {DECISION_DOCUMENT} in {policy}")
    return expression["value"]


def _one(values: Any, policy: Path) -> Any:
    if not isinstance(values, list) or len(values) != 1:
        raise LawmanError(f"{DECISION_DOCUMENT} in {policy} did not produce exactly one decision")
    return values[0]

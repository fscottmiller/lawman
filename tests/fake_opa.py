"""A stand-in for the OPA executable, for outcomes a real OPA will not produce.

Lawman finds OPA on PATH, so a test can put a different `opa` there. These are
real files, made executable and run as real subprocesses — nothing is patched,
and Lawman is exercised exactly as it will be in a pipeline. Only the policy
engine is missing.

Use it to pin down Lawman's half of the contract: what it sends, what it
accepts, and what it refuses. Everything that depends on OPA's own behavior
uses the real pinned executable — see `tests/test_opa.py`.
"""

import json
import stat
import sys
from pathlib import Path

_SCRIPT = '''#!{interpreter}
"""A stand-in OPA, written by tests/fake_opa.py."""

import json
import os
import signal
import sys
import time

received = sys.stdin.read()
record = {record!r}
if record is not None:
    with open(record, "w", encoding="utf-8") as handle:
        json.dump({{"argv": sys.argv[1:], "input": received}}, handle)
if {wedged_for!r}:
    time.sleep({wedged_for!r})
if {interrupted!r}:
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    os.kill(os.getpid(), signal.SIGINT)
sys.stdout.buffer.write({stdout!r})
sys.stderr.buffer.write({stderr!r})
sys.exit({exit_code!r})
'''


def _raw(output):
    return output if isinstance(output, bytes) else output.encode("utf-8")


def envelope(value):
    """OPA's --format json envelope around one decision document."""
    return {"result": [{"expressions": [{"value": value, "text": "data.lawman.decision"}]}]}


def install(directory, *, stdout="", stderr="", exit_code=0, record=None, interrupted=False, wedged_for=0):
    """Write an executable `opa` into `directory`, and return it as a PATH.

    `stdout` and `stderr` may be `bytes`, so a test can hand Lawman output that
    is not text at all.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "opa"
    script.write_text(
        _SCRIPT.format(
            interpreter=sys.executable,
            record=None if record is None else str(record),
            stdout=_raw(stdout),
            stderr=_raw(stderr),
            exit_code=exit_code,
            interrupted=interrupted,
            wedged_for=wedged_for,
        ),
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(directory)


def deciding(directory, value, **kwargs):
    """A stand-in that returns `value` as the decision document."""
    return install(directory, stdout=json.dumps(envelope(value)), **kwargs)


def missing(directory):
    """A PATH with no `opa` on it at all."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    return str(directory)

# 2. Python 3.11, standard library only

Status: Accepted (2026-08-07). Amended by [ADR 7](0007-check-types-and-style-in-ci.md) (2026-08-07) — development dependencies exist now (`mypy`, `flake8`, `isort`). No runtime dependency was added, and the test suite still runs with no install step.

## Context

The repository established no implementation language before the first slice — only README, working agreement, and licence.

What the first slice needs is small: read three JSON documents, compare names against facts, print a result. What Lawman eventually needs is harder to predict, but the shape is visible in the README: it reads authoritative state, evaluates contracts, and runs wherever consequential changes happen — which today means CI runners and developer laptops.

## Decision

Python 3.11, standard library only. No dependencies, no `pyproject.toml`, no packaging.

`json`, `dataclasses`, `argparse`, and `unittest` cover the entire slice. The Ponytail ladder stops at rung 3 — the standard library solves it — so nothing further is installed. `unittest` in particular is chosen over pytest for exactly this reason, which is why CI has no install step.

Go was the real alternative. A single static binary is a better distribution story for a tool meant to run inside arbitrary pipelines, and would matter if Lawman is ever shipped as a gate other teams drop into their CI. It was not chosen now because it buys nothing for a decision function, and distribution is not yet a problem we have.

## Consequences

Anything Python 3.11 ships with is available. Anything else needs a new decision, and a dependency at a seam is a tool choice, not a Ponytail shortcut.

Running Lawman requires a Python runtime. Fine for CI and laptops, and a real cost the day someone wants a single binary. That day gets a superseding ADR, and reversing is cheap while the implementation is a few hundred lines — it will not stay cheap forever.

Tests run as `python -m unittest discover -s tests`, from the repository root, with no install step in CI.

# 7. Check types and style in CI

Status: Accepted (2026-08-07)

Amends [ADR 2](0002-python-and-the-standard-library.md) — Lawman has development dependencies now. It still has no runtime ones.

## Context

An agent opened a pull request against this repository titled "fix type/linting issues." It ran `mypy`, `flake8`, and `isort` with their default settings and committed what came back.

The result is the argument for this ADR. `flake8`'s only complaint about this codebase is line length, at its default of 79 characters — and the repository's own untouched code runs to 119. So "fixed stylistic issues via flake8" meant re-wrapping two import statements and leaving 83 violations of the same rule, in a style that clashed with the lines directly around it. Nobody could reproduce that result, because no configuration said what the rule was.

The `mypy` half found something real: `Intent.from_dict` and `Contract.from_dict` pass `Any | None` into fields typed `str` and `tuple[str, ...]`. Those three errors predate the contract-selection slice; they have been on `main` since the first one.

Its fix was to default the missing keys — `fields.get("action", "")`, `.get("requires", ())`. That silences `mypy` and changes what Lawman says: a contract file missing `requires` entirely went from "contract.requires must be a list of requirement names" to "must name at least one requirement", which describes an empty list the author does not have. It also puts the parser in the business of deciding that an absent key means an empty one, which is the guess ADR 4 exists to forbid.

Both halves come from the same root cause: tools with no committed configuration.

## Decision

Adopt `mypy`, `flake8`, and `isort` as development dependencies, configured in the repository and enforced in CI.

- **Configuration is committed.** One `setup.cfg`, holding all three. Settings describe the style the repository already had — `max-line-length = 120` against a longest existing line of 119 — so adopting them reformatted nothing. The headroom is thin on purpose: the limit describes the code, and widening it later is a formatting decision that deserves its own argument. A tool whose config lives on a contributor's laptop is worse than no tool: it hands each contributor a different answer and makes the churn look like a decision somebody made.
- **Versions are pinned exactly** in `requirements-dev.txt`. A checker that changes its mind between runs is the problem being solved, not the solution.
- **`setup.cfg` is tool configuration, not packaging.** No `[metadata]`, no `[options]`. Lawman is still not installable. `flake8` cannot read `pyproject.toml`, and one config file beats three.
- **`mypy` runs strict, over `lawman/` only.** The tests hand invalid values to the types on purpose — `Contract(requires=None)`, a write to a read-only mapping — because that is what proves the types reject them. Type-checking them means fifteen `# type: ignore` comments on the suite's most valuable tests, which is an invitation to "fix" a test by deleting the invalid case. The test suite runs them; that is the check that matters. `flake8` and `isort` still cover `tests/`.
- **The pre-existing `mypy` errors are fixed by annotating, not defaulting.** The values pulled out of a JSON document are `Any`, which is what they are. Field types describe what a validated object holds; construction accepts whatever the document contained and rejects it. Every error message is byte-identical to before.
- **CI runs checks in a separate job from the tests.** The test job still has no install step, so the suite keeps proving that running Lawman needs nothing but Python.

## Consequences

Contributors need `pip install -r requirements-dev.txt` to reproduce CI. Running Lawman, and running its tests, still needs nothing.

`mypy` is now a constraint on the shipped code. Strict mode on a few hundred lines is cheap; it will have opinions about the first genuinely dynamic thing Lawman tries to do, and that argument is worth having when it arrives.

The line length is 120 because that is what the code already was, not because 120 is correct. Changing it is a formatting decision that will touch unrelated lines, so it belongs in its own commit.

Style disagreements are now settled by a file rather than by whoever ran a tool last. That is the whole point.

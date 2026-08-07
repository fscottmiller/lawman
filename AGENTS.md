# Agent Instructions

These instructions apply to every agent working in this repository.

## Before changing code

1. Read `README.md`, `WORKING_AGREEMENT.md`, the assigned issue and its comments, and the relevant ADRs under `docs/decisions/`.
2. Read the affected code and tests.
3. Start from the latest `main` on a focused branch.
4. Treat the issue's `lawman-work-contract` block as the authoritative definition of done.

If the issue has no contract, or its contract is missing or ambiguous, stop and ask. Do not invent acceptance criteria.

## Build

- Stay within the assigned issue.
- Follow Ponytail: stop at the first complete solution.
- Preserve Lawman's domain boundaries and fail-closed behavior.
- Give every acceptance criterion explicit, named automated evidence.
- Keep the AC-to-evidence mapping clear enough for another agent to verify.
- Do not weaken existing behavior or checks to make the change pass.

Run the complete local checks:

```bash
python -m unittest discover -s tests
pip install -r requirements-dev.txt
python -m mypy
python -m flake8
python -m isort --check-only lawman tests
```

Before publishing, review the whole diff for scope creep, premature abstraction, missing failure cases, and unproven criteria.

## Publish

1. Commit and push the focused change.
2. Open a normal published PR against `main` — never a draft.
3. Include `Closes #N`.
4. Map every acceptance criterion to its exact evidence in the PR description.
5. Wait for CI and repair failures.
6. Do not merge unless explicitly instructed.

Use concise Ponytail-style wording throughout.

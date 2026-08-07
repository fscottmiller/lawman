# Running Lawman

The first executable slice: **Intent → Contract → Evidence → Decision**. Give Lawman an intent, a contract, and evidence, and it decides whether the transition is allowed and explains why. Work and Transition are not built yet.

Python 3.11+. No dependencies, no install step.

## The canonical example

Deployment to production is allowed only when tests have passed and a human has approved.

```bash
python -m lawman \
  --intent examples/deploy-to-production/intent.json \
  --contract examples/deploy-to-production/contract.json \
  --evidence examples/deploy-to-production/evidence.json
```

```json
{
  "allowed": true,
  "explanation": "Allowed: deploy -> production. Satisfied: tests_passed, human_approved.",
  "intent": { "action": "deploy", "target": "production" },
  "satisfied": ["tests_passed", "human_approved"],
  "failed": [],
  "unproven": []
}
```

Swap in `evidence-tests-failed.json` and the same command denies:

```json
{
  "allowed": false,
  "explanation": "Denied: deploy -> production. Failed: tests_passed. Satisfied: human_approved.",
  "satisfied": ["human_approved"],
  "failed": ["tests_passed"],
  "unproven": []
}
```

The exit code carries the verdict: `0` allowed, `1` denied, `2` input could not be understood.

## The model

Four things, no more:

* **Intent** — the action being requested. `{"action": "deploy", "target": "production"}`
* **Contract** — the requirement names that must be proven. `{"requires": ["tests_passed", "human_approved"]}`
* **Evidence** — facts, explicitly true or false. `{"tests_passed": true, "human_approved": true}`
* **Decision** — `allowed`, plus which requirements were `satisfied`, `failed`, or `unproven`, plus an explanation.

A requirement is just a name. Evidence proves it true, proves it false, or says nothing — and silence is never proof, so missing evidence denies exactly like failed evidence. The decision always says which. A contract that requires nothing is rejected as a misconfiguration, not honoured as a permit.

Requirements are evaluated in contract order, so the same inputs always produce the same bytes.

## The tests

```bash
python -m unittest discover -s tests
```

Every acceptance criterion has a named test in `tests/test_decision.py`:

| Behavior | Test |
| --- | --- |
| tests passed + human approved → allow | `AllowsWhenEveryRequirementIsProven.test_tests_passed_and_human_approved_allows` |
| tests failed + human approved → deny | `DeniesWhenEvidenceRefutesARequirement.test_tests_failed_denies_even_with_human_approval` |
| tests passed + no human approval → deny | `DeniesWhenEvidenceIsMissing.test_no_human_approval_evidence_denies` |
| missing evidence → deny | `DeniesWhenEvidenceIsMissing.test_no_evidence_at_all_denies` |
| identical inputs → identical decision | `DecidesDeterministically.test_identical_inputs_produce_identical_decisions` |

`HoldsItsInvariantsWhenConstructedDirectly` covers the same invariants for code that builds the types directly rather than parsing them, including evidence that cannot be rewritten once presented.

`tests/test_cli.py` covers the same ground through the command line, including exit codes, unreadable and malformed input, and byte-identical output across runs.

## Why it looks like this

The decisions behind this slice, and the arguments against the alternatives, are in [`decisions/`](decisions/).

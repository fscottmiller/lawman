# Running Lawman

**Intent → Contract Selection → Contract → Evidence → Decision**. Give Lawman an intent and evidence. It selects the contract that governs that intent, decides whether the transition is allowed, and explains why. Work and Transition are not built yet.

Python 3.11+. No dependencies, no install step.

## The canonical example

Deployment to production is allowed only when tests have passed and a human has approved.

```bash
python -m lawman \
  --intent examples/deploy-to-production/intent.json \
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

The exit code carries the verdict: `0` allowed, `1` denied, `2` the input or the governing contract could not be understood.

## Where contracts come from

Not from the caller. The requester passes an intent and evidence; Lawman resolves the contract itself, from a registry checked into the repository being governed:

```
.lawman/
  contracts.json                     the registry
  contracts/deploy-production.json   the contract it points at
```

```json
{
  "deploy": {
    "production": "contracts/deploy-production.json"
  }
}
```

* The registry is nested the way an intent is shaped: action, then target. `deploy -> production` is looked up, not named — the pair has no identity of its own.
* The value is a path relative to `.lawman/`, and it must stay inside `.lawman/` — an absolute path, a `..` climb, or a symlink out is refused.
* `.lawman/` itself is relative to the current working directory, so **run Lawman from the root of the repository it is governing.**

Governing a new intent is two files: an entry in the registry, and the contract. There is no `--contract` flag, and adding one would hand the party asking for permission an edit on the rules. The reasoning is in [ADR 6](decisions/0006-the-repository-picks-the-contract.md).

### Refusing is not denying

`2` is not a quiet `1`. Exit `1` means Lawman read a contract and said no. Exit `2` means Lawman never got that far:

| Situation | Exit |
| --- | --- |
| a requirement failed, or was never proven | `1` |
| no contract configured for this intent | `2` |
| `.lawman/contracts.json` missing, unreadable, or malformed | `2` |
| the configured contract is missing, unreadable, or malformed | `2` |
| the configured contract path escapes `.lawman/` | `2` |

Both refuse the transition, so a pipeline gating on `exit == 0` is safe either way. Only one of them is a verdict, and "the tests failed" calls for a different response than "nobody configured this."

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

Every acceptance criterion has a named test.

Deciding — `tests/test_decision.py`:

| Behavior | Test |
| --- | --- |
| tests passed + human approved → allow | `AllowsWhenEveryRequirementIsProven.test_tests_passed_and_human_approved_allows` |
| tests failed + human approved → deny | `DeniesWhenEvidenceRefutesARequirement.test_tests_failed_denies_even_with_human_approval` |
| tests passed + no human approval → deny | `DeniesWhenEvidenceIsMissing.test_no_human_approval_evidence_denies` |
| missing evidence → deny | `DeniesWhenEvidenceIsMissing.test_no_evidence_at_all_denies` |
| identical inputs → identical decision | `DecidesDeterministically.test_identical_inputs_produce_identical_decisions` |

Selecting — `tests/test_selection.py`:

| Behavior | Test |
| --- | --- |
| `deploy -> production` resolves to the checked-in contract | `SelectsTheContractTheRepositoryConfigured.test_deploy_to_production_resolves_to_the_checked_in_contract` |
| a contract beside the intent does not govern | `SelectsTheContractTheRepositoryConfigured.test_a_contract_is_read_from_the_policy_directory_not_from_beside_the_intent` |
| identical inputs → identical contract | `SelectsTheContractTheRepositoryConfigured.test_the_same_intent_always_selects_the_same_contract` |
| unknown target, unknown action → refuse | `FailsClosedWhenItCannotFindTheRules.test_an_intent_with_no_configured_contract_is_refused`, `.test_an_unconfigured_action_is_refused` |
| missing or malformed registry → refuse | `FailsClosedWhenItCannotFindTheRules.test_a_missing_registry_is_refused`, `.test_a_registry_that_is_not_nested_names_is_refused` |
| missing or invalid contract file → refuse | `FailsClosedWhenItCannotFindTheRules.test_a_configured_contract_that_cannot_be_read_is_refused`, `.test_a_configured_contract_that_requires_nothing_is_refused` |
| contract outside `.lawman/` → refuse | `RefusesContractsTheRepositoryDoesNotOwn` (climb, absolute path, symlink) |

`HoldsItsInvariantsWhenConstructedDirectly`, in both files, covers the same invariants for code that builds the types directly rather than parsing them — including evidence and registries that cannot be rewritten once read.

`tests/test_cli.py` covers the same ground through the command line, including exit codes, byte-identical output across runs, and `TheCallerCannotChooseTheContract` — that there is no `--contract` flag, and that a weaker contract sitting beside the requester's own files does not govern.

## Why it looks like this

The decisions behind this slice, and the arguments against the alternatives, are in [`decisions/`](decisions/).

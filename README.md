# Lawman

No matter what your AI agents think, your SDLC isn’t the Wild West.

Lawman sits between intent and consequence, watching every change like a quiet judge that never sleeps. Agents can write, propose, refactor, test — but they do not decide.

> **Agents can run wild. Production can’t.**<br>
> **Lawman keeps the peace.**

That’s the whole system.

## What is it?

Lawman is a governance layer for autonomous software delivery.

It coordinates agents, tools, and pipelines — not by trusting them, but by constraining them. Every consequential change must satisfy its contract and applicable policy, backed by evidence, before it becomes reality.

Lawman is designed for autonomous, cloud-driven changes, but it is not limited to them. Work may be produced by an agent, a human engineer, a tool, or a combination. Lawman governs the change, not the identity of the author.

If it can’t be proven, it doesn’t happen.

### Why does it exist?

Because autonomous systems don’t fail by being too weak.

They fail by being too confident, too permissive, and too eager to build.

Lawman removes confidence from the wrong places and puts it where it belongs: in rules, evidence, and repeatability.

### What does it do?

A change enters as intent.<br>
From there, Lawman drives it through a controlled sequence:

Intent → Contract → Work → Evidence → Decision → Transition

The goal is not to maximize agent activity. The goal is to produce changes that empirically satisfy the contract.

Lawman does not create a separate manual path. The actor may matter to policy — for example, a repository may require human approval or independent review — but no actor bypasses the contract and evidence.

### What is it NOT?

* Not an agent framework
* Not a CI system
* Not a deployment tool
* Not a model wrapper

Those things may exist inside it, but they are not it.

Lawman is the authority they answer to.

## The Laws

* Contracts define what “done” means
* Evidence proves what is true
* Policy decides what is allowed
* Nothing is trusted by identity
* Models, agents, providers, and execution layers are replaceable
* Agents do not get to reinterpret any of the above

No implicit exceptions. No “creative autonomy.” No silent overrides.

Lawman does not decide how software should be built. The contract does.

A repository may demand minimal changes, exhaustive testing, human approval, independent review, or none of the above. Lawman’s job is not to choose those rules. Its job is to enforce them.

## The System

GitHub keeps the record.<br>
Lawman makes the call.

Everything else is just movement.

Lawman should own as little as possible. It reads authoritative state, evaluates the applicable contracts and policies, authorizes the next transition, and records why.

The workers can change. The rules can change. The enforcement persists.

## What runs today

The first executable slice: **Intent → Contract → Evidence → Decision**.

Give Lawman an intent, a contract, and evidence. It decides whether the transition is allowed and explains why. Work and Transition are not built yet.

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

### The model

Four things, no more:

* **Intent** — the action being requested. `{"action": "deploy", "target": "production"}`
* **Contract** — the requirement names that must be proven. `{"requires": ["tests_passed", "human_approved"]}`
* **Evidence** — facts, explicitly true or false. `{"tests_passed": true, "human_approved": true}`
* **Decision** — `allowed`, plus which requirements were `satisfied`, `failed`, or `unproven`, plus an explanation.

A requirement is just a name. Evidence proves it true, proves it false, or says nothing — and silence is never proof, so missing evidence denies exactly like failed evidence. The decision always says which. A contract that requires nothing is rejected as a misconfiguration, not honoured as a permit.

Files are JSON because the standard library reads it. Requirements are evaluated in contract order, so the same inputs always produce the same bytes.

### Run the tests

```bash
python -m unittest discover -s tests
```

Python 3.11+. No dependencies. Every acceptance criterion has a named test in `tests/test_decision.py`:

| Behavior | Test |
| --- | --- |
| tests passed + human approved → allow | `AllowsWhenEveryRequirementIsProven.test_tests_passed_and_human_approved_allows` |
| tests failed + human approved → deny | `DeniesWhenEvidenceRefutesARequirement.test_tests_failed_denies_even_with_human_approval` |
| tests passed + no human approval → deny | `DeniesWhenEvidenceIsMissing.test_no_human_approval_evidence_denies` |
| missing evidence → deny | `DeniesWhenEvidenceIsMissing.test_no_evidence_at_all_denies` |
| identical inputs → identical decision | `DecidesDeterministically.test_identical_inputs_produce_identical_decisions` |

`tests/test_cli.py` covers the same ground through the command line, including exit codes, unreadable and malformed input, and byte-identical output across runs.

### Why it looks like this

The decisions behind this slice, and the arguments against the alternatives, are in [`docs/decisions/`](docs/decisions/): Python and the standard library, a requirement is a name, silence is not proof, three JSON files and a CLI.

## License

Lawman is licensed under the [Apache License 2.0](LICENSE).

Copyright 2026 Scott Miller.

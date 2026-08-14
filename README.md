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

Lawman makes two separate calls.

**Intent → Policy Selection → OPA → Decision**. It decides whether policy allows a transition:

```bash
python -m lawman \
  --intent examples/deploy-to-production/intent.json \
  --evidence examples/deploy-to-production/evidence.json
```

The requester chooses what it wants to do. It does not choose the rules it will be judged by — there is no `--contract`, and no `--policy`.

Lawman does not interpret the rules either. The governed repository owns them as Rego in `.lawman/policies/`, and [OPA](https://www.openpolicyagent.org/) evaluates them. Lawman selects the policy, hands OPA the intent and the evidence, validates the decision, and reports it.

**Work Contract → Bound Evidence → Work Contract Result**. It decides whether one piece of work satisfied every acceptance criterion:

```bash
python -m lawman work \
  --contract examples/work-contract/contract.json \
  --evidence examples/work-contract/evidence.json
```

Each criterion names the one `evidence_source` that can prove it, so a passing result attached to the right criterion ID is not enough — it has to be the proof the contract asked for.

The contract can also come from the GitHub Issue that ordered the work, so the criteria are not written by whoever claims to have met them:

```bash
python -m lawman work \
  --issue https://github.com/fscottmiller/lawman/issues/8 \
  --evidence evidence.json
```

The issue states its contract in one fenced `lawman-work-contract` block, and the result records which issue it read and a hash of the exact contract it judged.

And the evidence does not have to be written by the party claiming to have earned it. Run Lawman inside the GitHub Actions job that ran the tests, and it derives the evidence from what they reported:

```bash
python -m lawman work \
  --issue "$ISSUE_URL" \
  --junit junit.xml
```

Each criterion is proven by the exact test the contract named, or it is not proven. The result records `GITHUB_SHA` — the revision that execution actually tested — and no argument can supply one.

Satisfying a work contract proves the work is done. It does not authorize a transition. Transition execution is not built yet.

[How to run it](docs/running-lawman.md) · [Why it looks like this](docs/decisions/)

## License

Lawman is licensed under the [Apache License 2.0](LICENSE).

Copyright 2026 Scott Miller.


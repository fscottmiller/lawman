# 9. Transition policy is delegated to OPA

Status: Accepted (2026-08-08)

Supersedes the transition half of [ADR 3](0003-a-requirement-is-a-name.md) and [ADR 4](0004-silence-is-not-proof.md). Renames the registry of [ADR 6](0006-the-repository-picks-the-contract.md) from contracts to policies; the boundary it establishes is unchanged. Work contracts keep ADR 3 and ADR 4 intact ([ADR 8](0008-work-contracts-are-separate-from-transition-policy.md)).

## Context

ADR 3 made a requirement a name, deliberately, to keep Lawman from growing an expression language. That held exactly as long as no repository needed a rule it could not phrase as a boolean.

The pressure arrives immediately. "Two approvals" is a count. "Not on a Friday" is a time. "Any of these three checks" is a disjunction. Each one is a small, reasonable ask, and each one is answered either by pushing more computation into the evidence producer — until `deploy_allowed: true` is the only fact left and Lawman decides nothing — or by adding an operator, then a value, then a type system.

That second path is the one ADR 3 named and refused. It also ends somewhere specific: a policy language nobody outside this repository knows, with no test tooling, no coverage story, and no reviewers.

Policy-as-code already solved this. Rego is a real language for exactly this problem, with a decision-log story, a test runner, an editor story, and people who already write it.

## Decision

Lawman does not evaluate transition policy. OPA does.

**Intent → Contract Selection → Contract → Evidence → Decision** becomes **Intent → Policy Selection → OPA → Decision**.

The governed repository keeps Rego beside its registry, and the registry now names policies:

```text
.lawman/
  policies.json                      the registry
  policies/deploy-production.rego    the policy it points at
```

Four things are fixed, and none of them is a caller input:

- **The executable.** `opa`, found on PATH, invoked as a local process. Not a Python policy library, not a service — a library would put a policy engine's release cycle inside Lawman's dependency tree, and a server would put a network hop and a second deployment inside a decision that must fail closed.
- **The query.** `data.lawman.decision`. One document, the same for every policy. A registry that also chose the query would let a policy file quietly answer a different question than the one Lawman asked.
- **The input.** `{"intent": ..., "evidence": ...}`. The intent is validated. The evidence is passed through whole — no required keys, no booleans, no coercion. Lawman does not know what `coverage` means, and after this ADR it does not need to.
- **The result.** `allowed`, plus at least one non-empty reason. Unknown fields are refused rather than ignored: a policy that returns something Lawman drops is a policy whose author believes it is being read.

Every decision carries a reason, including an allowed one. A permit nobody can explain is the failure this tool exists to prevent, and OPA can say why as cheaply as it can say yes.

Reasons are reported in the order the policy emitted them. Lawman does not sort, deduplicate, or rewrite prose it did not write.

Refusal semantics are unchanged and now cover more ground. A missing `opa`, a non-zero OPA exit, unreadable OPA output, an undefined or ill-formed decision, and an unselectable policy all raise `LawmanError` and exit `2`. Exit `1` still means a policy was evaluated and said no. A pipeline gating on `exit == 0` stays fail-closed either way.

### What was deliberately not built

No compatibility layer for `.lawman/contracts.json`. It is a breaking rename, taken now, while the only governed repository is this one. Supporting both would mean two policy models, a precedence rule between them, and a permanent question about which one actually decided.

No OPA server, no bundles, no policy composition, no remote distribution. All of them are distribution and scale answers, and the local slice has neither problem yet.

No configurable executable path, and no `--opa`. PATH is already the trust boundary for every tool a pipeline runs; a flag naming the policy engine would be a flag naming the decider.

No embedding of work-contract results into the policy input. That seam is real and deferred (ADR 8) — wiring it now would mean designing it against no user.

## Consequences

Rules become as expressive as Rego, which is to say expressive enough. Adding "two approvals" is a Rego change with Rego tests, reviewed like any other code, and Lawman's Python does not move.

Lawman gains a runtime dependency it cannot fake. `python -m lawman` still needs nothing but Python 3.11, but a transition decision now needs an `opa` executable, and CI must install one exact pinned version — a decision engine that changes between runs is the problem these ADRs keep solving. This is the first amendment to ADR 2 that reaches runtime.

The seam is now a process boundary, which is the point: OPA is replaceable, and swapping it means changing one module.

Two policy models exist in one tool, and the distinction has to stay legible. Work contracts are still names, evidence, and silence-is-not-proof (ADR 3, ADR 4, ADR 8); transitions are Rego. Anyone reading `lawman/work.py` next to `lawman/opa.py` and expecting one model will be wrong.

Lawman can no longer explain a denial in its own words. The reasons come from the policy, so a policy that returns `["no"]` produces a decision that says `no`. That is the correct owner of the explanation, and it makes reason quality a policy review concern.

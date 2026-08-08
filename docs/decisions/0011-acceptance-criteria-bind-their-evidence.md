# 11. An acceptance criterion names the evidence that can prove it

Status: Accepted (2026-08-08)

Extends the work-contract half of [ADR 8](0008-work-contracts-are-separate-from-transition-policy.md). Keeps ADR 3 and ADR 4 intact: a criterion is still a name, and silence is still not proof. Amends the contract normalization recorded in [ADR 10](0010-work-contracts-can-come-from-github-issues.md). Adds nothing to transition policy ([ADR 9](0009-delegate-transition-policy-to-opa.md)).

## Context

A criterion said what had to be true. Evidence said which source said so. Nothing connected them, so any passing source attached to the right criterion ID counted:

```json
{ "criterion_id": "AC7", "source": "test_it_imports", "passed": true }
```

That is the whole obligation discharged by whichever green thing was closest to hand. The contract stated an obligation and then accepted an unrelated proof of it, which makes "proven" a claim about the author's diligence rather than about the work.

The contract already knows what should prove each criterion — the issue that ordered the work names the test. It just was not being carried, so it could not be enforced.

## Decision

The contract owns both the obligation and the proof it requires:

```json
{ "id": "AC1", "description": "Invalid tokens return 401", "evidence_source": "test_invalid_token" }
```

**Work Contract → Bound Evidence → Work Contract Result.** The evidence document keeps its schema. What changed is which entries a criterion will accept.

### One criterion, one source

Each criterion requires exactly one `evidence_source`, and a source may be bound to only one criterion. The relationship is one-to-one so that a single broad passing check cannot stand in for several obligations — which is the substitution the binding exists to stop.

Multiple acceptable sources for one criterion, and one source proving several, were both deliberately left out. Either would reintroduce a choice about which proof counts, and that choice belongs to whoever wrote the contract, not to Lawman.

### The identifier is opaque and compared exactly

Lawman does not interpret test names, paths, check names, or prefixes. Matching is exact and case-sensitive. `test_invalid_token` and `TEST_INVALID_TOKEN` are different sources, and `tests/auth.py::test_invalid_token` is a third.

Every alternative here is Lawman inventing a naming convention — a prefix rule, a case fold, a path parser — and then quietly accepting things a contract author did not agree to. An identifier nobody parses cannot be argued into matching.

### A missing entry is a result. A wrong source is not

Silence about a bound source is `unproven` and exits `1`: an obligation nobody proved is exactly what the contract is for, and the result names the source that is owed.

Evidence that names a criterion and a source that criterion did not bind is refused with exit `2`, with no result printed. It is not an answer to the obligation, so there is no honest status for it. Ignoring it would silently drop a claim the author believed was being read, and counting it would be the substitution this ADR removes.

### The result reports both sources

```json
{
  "id": "AC1",
  "description": "Invalid tokens return 401",
  "evidence_source": "test_invalid_token",
  "status": "unproven",
  "source": null,
  "explanation": "Unproven: no evidence from test_invalid_token was provided."
}
```

`evidence_source` is what the contract requires; `source` is what was presented, or `null`. A reader of an unproven result should not have to open the contract to learn what would have proven it.

### The binding is part of the contract's identity

`contract_sha256` now covers `id`, `description`, and `evidence_source`, in criterion order. Changing only a binding changes the hash; reindenting the JSON or reordering object keys does not. A contract that demands different proof is a different contract, and later policy comparing hashes has to see that.

### Existing contracts without bindings stop working

No compatibility default for a contract without `evidence_source`. There is nothing safe to guess: the whole point is that Lawman cannot know which source was meant to prove a criterion, and inventing one — the first passing entry, a name derived from the ID — would be the guess ADR 4 exists to forbid. Repository-owned examples, fixtures, and documented contracts were updated in the same change.

## Consequences

Contracts get longer, and writing one now requires deciding what would prove each criterion before the work starts. That is the intended cost: it moves the argument about what counts as proof to before the work, where it can still change the work.

**Lawman does not retrieve evidence.** It does not run the named source, fetch it from CI, or check that it exists. A presented document still says what passed. This story binds a claim to the obligation it answers; it does not establish that the claim is true. Retrieval — a workflow run, a check, a commit SHA — is the next question, and it is deliberately not this one.

Binding is not authorization. A satisfied contract still authorizes no transition, and no work result reaches OPA. The seam stays where ADR 8 put it.

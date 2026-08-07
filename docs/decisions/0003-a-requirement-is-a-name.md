# 3. A requirement is a name

Status: Accepted (2026-08-07)

## Context

A contract has to say what must be proven before an intent may transition. The obvious first move is to give requirements structure — a type, an operator, a value, a comparison — so that a contract can express `coverage >= 80` as easily as `tests_passed`.

That move is one small step from a general-purpose rules engine, which the README explicitly says Lawman is not.

## Decision

A requirement is a name. A contract is a list of names:

```json
{ "requires": ["tests_passed", "human_approved"] }
```

Evidence proves a name true or proves it false. Nothing else is expressible.

A shape like `{"requires": [{"test": "tests_passed"}]}` was considered and rejected: the `test:` key implies a taxonomy of requirement types, and no second type exists. Operators and values were rejected for the same reason — the moment Lawman compares values, it owns an expression language, an evaluation order, and a type system.

Whoever produces the evidence already computed `coverage >= 80`. They can present `coverage_met`.

## Consequences

Contracts stay readable by anyone, and the whole evaluator is one loop with three outcomes.

Pushing evaluation out to the evidence producer is the trade. Lawman cannot check the arithmetic behind `coverage_met`, only that someone asserted it. Making that assertion trustworthy is an evidence-provenance problem — who signed this, and can it be replayed — and that is a better problem to solve than an expression language.

If richer requirements become genuinely necessary, this is the ADR to supersede, and the contract format will need a version.

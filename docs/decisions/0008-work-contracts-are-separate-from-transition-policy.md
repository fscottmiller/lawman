# 8. Work contracts are separate from transition policy

Status: Accepted (2026-08-07)

## Context

Lawman needs to answer two different questions:

1. Did this piece of work satisfy its acceptance criteria?
2. May the resulting change transition?

Collapsing them would turn story obligations into deployment rules, or let completed work imply permission it does not have.

## Decision

Work contracts and transition policy are separate domains.

A work contract belongs to one piece of work. It names acceptance criteria, accepts evidence mapped explicitly to each criterion, and produces a work-contract result. Every criterion is proven, failed, or unproven. The aggregate is satisfied only when all are proven.

Transition policy decides whether an intent is allowed. It remains unchanged.

For this local slice, the caller names the work-contract file. That identifies the work being checked; it does not select the policy governing a transition.

## Consequences

A satisfied work contract can become evidence for policy later, but it does not authorize anything by itself.

Lawman owns criterion accounting. It does not gain operators, expressions, inheritance, composition, or another policy language.


# 1. Record decisions as ADRs

Status: Accepted (2026-08-07)

## Context

The working agreement asks us to record a short rationale when a decision is likely to matter again, and to prefer a durable explanation over rediscovering the same design question.

The first slice made several such decisions. Their rationale ended up in commit messages and a pull request description — outside the repository, unversioned, and effectively unfindable six months from now.

## Decision

Meaningful decisions get a short file in `docs/decisions/`, numbered `NNNN-kebab-title.md`, with four headings: Status, Context, Decision, Consequences.

One decision per file. Reverse a decision by writing a new ADR that supersedes the old one, and mark the old one superseded; do not quietly edit history.

Record a decision when it constrains future work or when someone will reasonably ask "why is it like this?" Not every choice qualifies. An ADR nobody would have questioned is ceremony.

## Consequences

Rationale is versioned with the code that depends on it, and reviewable in the pull request that makes the decision.

The cost is one small file per decision, and the discipline to write it while the reasoning is still fresh.

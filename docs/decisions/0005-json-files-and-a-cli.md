# 5. Three JSON files, one CLI

Status: Accepted (2026-08-07)

## Context

The slice needs some way to hand Lawman an intent, a contract, and evidence, and to get a decision back. Anything chosen here will be the first thing an integration touches.

## Decision

A CLI — `python -m lawman` — taking three file paths and printing the decision as JSON. No HTTP.

Three separate files, not one document, because the three inputs come from three different places: the intent is requested by an actor, the contract is declared by the repository, the evidence is produced by work. The interface says so.

JSON rather than YAML because the standard library reads it (see ADR 2). This is the weakest decision here: contracts are the input humans actually hand-write, and YAML is kinder to write by hand. Revisit it when contracts are written by people often enough to hurt.

The exit code carries the verdict:

- `0` allowed
- `1` denied
- `2` input could not be understood

## Consequences

Lawman composes with anything that can run a process and read a file, which is every CI system, and needs no server, port, or client library.

Separating "will not allow" from "cannot understand" matters: a pipeline that treats every non-zero exit as a denial is correct but uninformative, and one that treats a crash as a denial would be dangerously wrong in the other direction.

Decisions are printed, not stored. Nothing here persists a record; the caller keeps it. Persistence, when it exists, gets its own ADR.

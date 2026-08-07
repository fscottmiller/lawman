# 5. Three JSON files, one CLI

Status: Accepted (2026-08-07)

## Context

The slice needs some way to hand Lawman an intent, a contract, and evidence, and to get a decision back. Anything chosen here will be the first thing an integration touches.

## Decision

A CLI — `python -m lawman` — taking three file paths and printing the decision as JSON. No HTTP.

Three separate files, not one bundled document.

The reason is not tidiness, it is who writes each one. The intent is raised by whoever wants the transition. The evidence is produced by whatever did the work. The contract is declared by the repository and reviewed like code.

Bundle them and the party asking for permission also supplies the contract it will be judged against. Weakening a requirement stops being a reviewed change to a checked-in file and becomes a line edit in the request itself — which is the failure the README describes as an agent reinterpreting its own acceptance criteria. Keeping the contract a separate input means it can be read from a trusted, version-controlled location while evidence arrives from wherever the work happened. That separation is the whole point of the tool; the file boundary is just where it becomes visible.

Their lifetimes differ for the same reason. A contract is written once per governed target and changes rarely. Intent and evidence are produced per evaluation and thrown away.

So this does not multiply files by three. Per evaluation it is two ephemeral inputs rather than one, and the contract count grows with the number of things being governed, not with the number of runs.

A single bundled `--case` file would be convenient for local experimentation and was deliberately not built. If it ever is, it must be a convenience for one person driving Lawman by hand, never a path by which a requester supplies its own contract.

JSON rather than YAML because the standard library reads it (see ADR 2). This is the weakest decision here: contracts are the input humans actually hand-write, and YAML is kinder to write by hand. Revisit it when contracts are written by people often enough to hurt.

The exit code carries the verdict:

- `0` allowed
- `1` denied
- `2` input could not be understood

## Consequences

Lawman composes with anything that can run a process and read a file, which is every CI system, and needs no server, port, or client library.

Separating "will not allow" from "cannot understand" matters: a pipeline that treats every non-zero exit as a denial is correct but uninformative, and one that treats a crash as a denial would be dangerously wrong in the other direction.

Decisions are printed, not stored. Nothing here persists a record; the caller keeps it. Persistence, when it exists, gets its own ADR.

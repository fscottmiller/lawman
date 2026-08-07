# 5. Three JSON files, one CLI

Status: Accepted (2026-08-07). Superseded in part by [ADR 6](0006-the-repository-picks-the-contract.md) (2026-08-07) — the contract is no longer a caller-supplied path, and there is no `--contract` flag. Everything else here stands, and the gap ADR 6 closes is the one described below.

## Context

The slice needs some way to hand Lawman an intent, a contract, and evidence, and to get a decision back. Anything chosen here will be the first thing an integration touches.

## Decision

A CLI — `python -m lawman` — taking three file paths and printing the decision as JSON. No HTTP.

Three separate files, not one bundled document.

The reason is not tidiness, it is who writes each one. The intent is raised by whoever wants the transition. The evidence is produced by whatever did the work. The contract is declared by the repository and reviewed like code.

Bundle them and the party asking for permission also supplies the contract it will be judged against. Weakening a requirement stops being a reviewed change to a checked-in file and becomes a line edit in the request itself — which is the failure the README describes as an agent reinterpreting its own acceptance criteria. Keeping the contract a separate input means an integration *can* read it from a trusted, version-controlled location while evidence arrives from wherever the work happened.

What the split does not do is enforce that. The CLI takes all three paths from one caller, and nothing binds a contract to an intent, so Lawman will print `Allowed: deploy -> production` against whatever contract file it was pointed at — including a weaker one written for somewhere else. The separation makes trustworthy sourcing possible. It does not make it true, and nothing in this slice checks it.

Binding a contract to an intent would not close that on its own either. A caller free to choose the file is free to choose one whose binding happens to match. Enforcement has to come from where the contract is read — a pinned location, a signature, a reference the requester does not control — which is contract selection, and contract selection is deferred. It gets its own ADR when it arrives.

Their lifetimes differ for the same reason. A contract is written once per governed target and changes rarely. Intent and evidence are produced per evaluation and thrown away.

So this does not multiply files by three. Per evaluation it is two ephemeral inputs rather than one, and the contract count grows with the number of things being governed, not with the number of runs.

### Why not bundle the intent with the contract

Of the three pairings this is the one to avoid hardest, because the intent is the request. Whoever raises it is the party asking for permission, so putting it in the same document as the contract hands the requester an edit on the rules — the concern above, at its sharpest rather than its mildest.

It also assumes the intent is checked in. The examples in this repository do check one in, because they are examples. In a real integration the intent is raised per request — an agent finishes work and asks to deploy — and it is what will select which contract applies. Hardcoding it means a repository change to request anything new, and one file per intent-and-contract pair rather than one per intent plus one per contract. That is where files actually multiply.

Reuse of a contract across intents is not hypothetical. `decide()` records the intent and never evaluates it, so today every contract already applies to every intent, and one `requires: ["tests_passed", "human_approved"]` file can govern `deploy -> production` and `rollback -> production` alike. Bundling forces a copy per intent.

The honest counterargument is that the intent is inert right now — recorded and explained, never evaluated — so bundling would cost nothing yet. It would cost once intent selects the contract, and this is the first thing an integration touches.

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

Anything acting on a decision today is trusting whoever ran the command to have pointed `--contract` at the right file. The interface permits that trust to be established elsewhere; this slice does not establish it.

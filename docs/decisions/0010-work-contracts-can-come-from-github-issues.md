# 10. A work contract can come from a GitHub Issue, identified by its content

Status: Accepted (2026-08-08)

Extends the work-contract half of [ADR 8](0008-work-contracts-are-separate-from-transition-policy.md). Keeps ADR 3 and ADR 4 intact: a criterion is still a name, and silence is still not proof. Adds nothing to transition policy ([ADR 9](0009-delegate-transition-policy-to-opa.md)).

## Context

A local `--contract` file is written by whoever runs Lawman. That is fine for proving the model, and useless for governing anything: the party claiming the work is done also gets to say what "done" meant.

The criteria already exist somewhere better. Work is ordered in a GitHub Issue, reviewed there, and argued about there. The issue is the authoritative statement of the obligation, and it is not a file the agent can edit on the way past.

Reading it raises two questions this ADR answers: which part of the issue is the contract, and which version of it was judged.

## Decision

Lawman reads a work contract from a GitHub Issue named by a canonical URL:

```bash
python -m lawman work \
  --issue https://github.com/fscottmiller/lawman/issues/8 \
  --evidence evidence.json
```

`--contract` and `--issue` are alternatives, and exactly one is required.

### The contract is one fenced block, not the issue

An issue body must contain exactly one fenced ` ```lawman-work-contract ` block, holding the same JSON a `--contract` file holds. Everything else — prose, headings, task lists, other fenced blocks, labels, comments, titles, assignees — is ignored.

Nothing is inferred. A checklist is not criteria, a heading is not a criterion, and an issue with no block, or two of them, is refused rather than resolved. Inference would mean Lawman deciding what the work is, which is exactly the authority a contract exists to remove.

### Identity is the node ID plus a hash of the contract

A GitHub-backed result carries its source:

```json
{
  "contract_source": {
    "type": "github_issue",
    "url": "https://github.com/fscottmiller/lawman/issues/8",
    "node_id": "I_kwDOexample",
    "updated_at": "2026-08-08T00:00:00Z",
    "contract_sha256": "sha256:c5d3…"
  }
}
```

- **The node ID says which issue.** It survives renaming the repository or the owner; the URL does not.
- **The hash says which contract.** It is computed from the normalized semantic contract — criteria in issue order, each reduced to `id` and `description`, sorted keys, compact separators, UTF-8, lowercase hex. Rewording the prose around the block, reindenting the JSON, or reordering its keys leaves it alone. Changing, adding, renaming, or reordering a criterion moves it.
- **`updated_at` says nothing about identity.** Any edit to the issue moves it, and no edit to the issue is required to move the contract. It is trace information.

Later policy can therefore ask whether the contract that was judged is the contract that was agreed, instead of trusting an unbound `work_satisfied: true`.

### The read is narrow, and the token is not an input

One REST `GET` of the named issue. No comments, no timeline, no search, no writes. `GITHUB_TOKEN` is read from the environment when present, never from an argument, and never printed — not in a result, not in a diagnostic. Redirects are refused rather than followed, because urllib would resend the token to wherever the redirect points.

"Never printed" has to be enforced, not assumed. A token carrying whitespace or a control character is refused before it becomes a header, because the HTTP layer rejects an illegal header value with an error that quotes the whole value — which is the credential. The same reasoning applies to the issue URL: `.` and `..` are legal characters in a GitHub name and a directory climb in the path Lawman assembles, so an issue reference cannot be built from them at all, whether it was parsed or constructed in code.

### Refusal semantics are unchanged

Exit `2`, no result on stdout, one line on stderr: a non-canonical URL, a pull-request URL, an inaccessible issue, an HTTP error, a network failure, a timeout, a response that is not the issue that was asked for, a missing or duplicated block, invalid JSON, duplicate JSON keys, or content the existing `WorkContract` invariants refuse. Exit `1` still means a contract was read and its criteria were not all proven.

### What was deliberately not built

No inference from prose or checklists, and no reading of comments. Both are the same mistake in different clothing: Lawman guessing at an obligation nobody stated in the one place it agreed to look.

No caching, no persistence, no webhooks, no GitHub Enterprise, no automatic selection of the governing issue.

No environment variable or flag naming the API origin. A caller who can choose the server can choose the contract; tests substitute the origin in process, and that is the only place it moves.

No feeding of the result into transition policy. The seam stays where ADR 8 put it.

## Consequences

Lawman makes a network call on a path that previously touched only local files, so the work command now has a failure mode that has nothing to do with the work: GitHub can be down. It fails closed, and the local `--contract` path is unchanged for anyone who does not want the dependency.

"Authoritative" means the contract came from the identified issue rather than from caller-controlled local input. It does not mean the caller picked the right issue. Nothing here proves that this issue governs this change — the source identity exists so later policy can decide that without trusting a boolean.

The result schema now has two shapes: a local result, and a GitHub-backed result with `contract_source` in front of it. A consumer reading `satisfied` sees no difference; a consumer that wants provenance has to ask for the issue path.

The hash is a commitment. Changing what it covers, or how it is serialized, changes every recorded identity, so it is specified here rather than left to whatever `json.dumps` does by default.

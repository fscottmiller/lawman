# 6. The repository picks the contract

Status: Accepted (2026-08-07)

Supersedes the `--contract` half of [ADR 5](0005-json-files-and-a-cli.md).

## Context

ADR 5 kept the contract a separate input so that an integration *could* read it from a trusted, version-controlled location, and said plainly that nothing enforced it: the CLI took all three paths from one caller, so Lawman would print `Allowed: deploy -> production` against whatever contract file it was pointed at, including a weaker one written for somewhere else.

That gap is the whole point of the tool. A governance layer whose rules are chosen by the party asking for permission is a formatting step.

ADR 5 also ruled out the near miss: binding a contract to an intent inside the contract file does not close it, because a caller free to choose the file is free to choose one whose binding happens to match. Enforcement has to come from where the contract is *read*.

## Decision

The requester supplies the intent and the evidence. Lawman resolves the contract itself.

A checked-in registry at a fixed location in the governed repository maps an intent to its contract:

```json
{ "deploy": { "production": "contracts/deploy-production.json" } }
```

Four things make that a boundary rather than a convention:

- **The location is fixed.** `.lawman/contracts.json`, relative to the current working directory — so running Lawman from a repository root governs that repository. There is no flag naming it.
- **The lookup is the intent's shape.** Action, then target — the pair Lawman already had, nested rather than serialized. No separate intent ID, because nothing yet needs to distinguish two `deploy -> production` requests, and an ID the requester supplies would be one more thing to trust.
- **Contract paths are relative to `.lawman/` and must resolve inside it.** Resolving before the check refuses an absolute path, a `..` climb, and a symlink pointing out, without reasoning about each separately. A repository can only offer contracts it owns.
- **The CLI has no `--contract`.** Not deprecated, not hidden behind a development flag — absent. An escape hatch that weakens the rules is the failure this ADR exists to prevent, and `select_contract(intent, policy)` already takes a policy directory for tests and for in-process use, which the CLI never passes.

Failing to resolve a contract is **not** a denial. An unknown intent, an unreadable registry, a registry that is not names nested by action and target, a missing or malformed contract file — all raise `LawmanError` and exit `2`, alongside every other input Lawman refuses to guess about. Exit `1` still means Lawman applied a contract and said no. Both refuse the transition; only one of them is a verdict, and a pipeline that cannot tell "the tests failed" from "nobody configured this" is being lied to.

Selection lives in its own module. `decide()` still takes three objects, touches no filesystem, and does not know a registry exists.

### What was deliberately not built

Wildcards, inheritance, composition, priorities, and fallback chains were all rejected: the canonical use case is one intent resolving to one contract, and every one of those features answers a question nobody has asked. A fallback contract is the most tempting and the worst — it turns an unconfigured intent from a loud refusal into a quiet default.

One registry, one policy directory. Multiple policy sources would need precedence rules, and precedence rules are where a governance layer starts arguing with itself.

A flat `"deploy:production"` key was written first, and replaced in review. It read the way people say it, but `action:target` is a *serialization* of the intent's pair, not a name the pair has — and putting it in the registry quietly proposed that contracts and intents are identified `verb:noun` from here on. It also bought a delimiter and the rules that come with it: keys splitting into exactly two non-blank parts, `a:b:c` rejected as malformed, blank halves refused. Every one of those rules existed only to undo the serialization.

Nesting removes them. The registry says what it means — this action, at this target, is governed by this contract — and the lookup is two dictionary reads. An action present with the target absent fails closed exactly like an absent action.

An empty registry is rejected. It would already fail closed on every intent — this only buys a better error — but a policy document that governs nothing is a misconfiguration for the same reason a contract that requires nothing is (ADR 4).

## Consequences

The governance property now holds locally: the requester chooses what it wants to do, not the rules it will be judged by. Weakening a requirement is a reviewed change to a checked-in file, which is what ADR 5 wanted and could not enforce.

`.lawman/` is now a governed repository's public surface. Write access to it is write access to the rules — which is correct, and is exactly the thing branch protection and review already know how to guard.

Contracts are selected by *location*, and location is only as trustworthy as the checkout. Lawman still cannot tell a genuine `.lawman/` from one an attacker with commit access rewrote, and it verifies no signature or provenance. That is the next boundary, not this one, and it gets its own ADR.

Adding a governed intent is two files: an entry in the registry, and the contract. Lawman gains no new inputs.

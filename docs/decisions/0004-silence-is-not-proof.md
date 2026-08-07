# 4. Silence is not proof

Status: Accepted (2026-08-07)

## Context

Evidence arrives as a set of facts. Some requirements will have no fact at all — the check never ran, the reviewer never looked, the producer forgot the key.

The permissive reading is that an absent fact is not a failure. That reading is how governance layers quietly stop governing: a renamed evidence key silently converts a hard requirement into no requirement.

## Decision

A requirement is satisfied only when evidence explicitly proves it true. Absence denies, exactly like `false`.

Three consequences of the same principle:

- Evidence values must be real booleans. `"true"`, `1`, and `null` are rejected as malformed rather than coerced.
- A contract with no requirements is rejected. A contract that proves nothing is a misconfiguration, not a permit.
- The decision reports `failed` and `unproven` separately. Both deny, but "the tests failed" and "nobody ran the tests" call for different responses.

## Consequences

Lawman denies noisily on incomplete evidence, which is the intended failure mode. Expect the first real integration to hit this while evidence producers are still being wired up.

Evidence keys become a contract of their own: renaming one is a breaking change, and the denial says which name it wanted.

Facts beyond the contract's requirements are ignored, not rejected. Evidence is a bag of what is known; the contract decides what matters.

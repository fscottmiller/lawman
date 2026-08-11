# 12. Work evidence comes from the execution that produced it

Status: Accepted (2026-08-11)

Finishes the sentence [ADR 11](0011-acceptance-criteria-bind-their-evidence.md) ended on. Uses the issue contract from [ADR 10](0010-work-contracts-can-come-from-github-issues.md). Leaves the work domain ([ADR 8](0008-work-contracts-are-separate-from-transition-policy.md)) and transition policy ([ADR 9](0009-delegate-transition-policy-to-opa.md)) exactly where they were.

## Context

ADR 11 bound each criterion to the one source that could prove it, and then said plainly: **Lawman does not retrieve evidence.** The document still came from the party claiming the work was done.

```json
{ "criterion_id": "AC1", "source": "test_invalid_token", "passed": true }
```

That is a sentence anyone can type. Binding narrowed what a claim may be made of; it did nothing about whether the claim is true. An agent that can write the evidence file can prove anything, and a contract proven that way records diligence, not work.

## Decision

**GitHub Issue contract → GitHub Actions execution → JUnit report → Work Evidence → Work Contract Result.**

```bash
python -m lawman work --issue "$ISSUE_URL" --junit junit.xml
```

`--junit` replaces `--evidence`, and requires `--issue`. Derived proof against criteria the claimant also wrote proves nothing new, so the narrow path is the only path.

### The execution is the anchor, and it is not an argument

Lawman runs inside the GitHub Actions job that ran the tests, and reads the run from the environment: `GITHUB_ACTIONS`, `GITHUB_REPOSITORY`, `GITHUB_SHA`, `GITHUB_RUN_ID`, `GITHUB_RUN_ATTEMPT`. All five are required, none is a flag, and none is repaired — an abbreviated SHA, an uppercased one, or one with a newline appended is refused, because a value Actions did not set is somebody's edit.

`GITHUB_SHA` is reported in the result as `execution.revision`. It is the commit Actions checked out and tested; on a `pull_request` event that is the merge commit, which is what ran, so Lawman reports it rather than substituting a branch head it never saw.

Remote alternatives were rejected for this slice. Discovering a workflow run through the API, downloading artifacts, or publishing a Check all add a second trust question — which run, retrieved how, believed why — to a story whose point is the first one. Running inside the execution answers it by construction: there is no run to select.

### A test identity is exact, and a case has exactly two of them

A `<testcase>` answers to `name`, and to `classname` + `.` + `name`. Both are strings the report wrote; Lawman only joins two attributes JUnit already keeps apart. There is no prefix rule, no case fold, no path parser, and no alias, for the reason ADR 11 gave: an identifier nobody parses cannot be argued into matching.

A contract binds whichever of the two is unique. `test_invalid_token` is enough when one test carries it; `tests.test_auth.Tokens.test_invalid_token` is there for when it is not.

### Absent is unproven. Ambiguous or unreadable is refused

The distinction ADR 11 drew survives contact with a real report:

* a required test present and passing → `passed: true` → `proven`
* a required test present and failing or erroring → `passed: false` → `failed`
* a required test absent, or skipped → **no evidence entry at all** → `unproven`
* two cases carrying one bound identity → refused, exit `2`
* a missing, unreadable, or malformed report → refused, exit `2`

A skipped test reported no outcome. Calling it a failure blames a test that never ran, and calling it a pass is the lie the whole tool exists to prevent, so it produces nothing and the criterion stays owed.

An unreadable report is never "no tests ran". Treating a parse failure as an empty run turns every truncated write into an honest-looking `unproven`, and every wrong path into a silent one.

### CI code produces `WorkEvidence`, and stops

`lawman/ci.py` builds the existing domain type and hands it to the existing `evaluate_work_contract`. It does not know the words `proven`, `failed`, or `unproven`, and there is no second path to a verdict. `evaluate_work_contract` stays CI-agnostic, and `evidence_source` stays opaque to the work domain — the module that matches identities is the only one that knows an identifier can be a test name.

## Consequences

The `--evidence` document keeps working, unchanged, for both `--contract` and `--issue`. It is now the weaker of the two paths, and that is visible in the result: derived evidence carries an `execution` block naming the revision, and a presented document carries nothing, because it cannot honestly claim one.

**The report is trusted as a product of the execution.** Lawman reads the file the workflow points it at; it does not prove the XML came from the test runner rather than from an `echo`. What it refuses to accept is a hand-written claim that a required test passed.

**The execution context is an assumption about the environment, not a verified fact.** `GITHUB_ACTIONS=true` and four plausible values can be exported anywhere — a laptop, another CI, a shell. Lawman reads the environment Actions sets; it does not authenticate the run, and verifying one would need precisely the remote workflow-run lookup this slice defers. A derived result is worth what the reader's knowledge of where it ran is worth.

**The execution's repository is reported, not enforced.** `GITHUB_REPOSITORY` is never compared to the `owner/repo` in the issue URL, so a fork's green run can satisfy an upstream issue's contract. The mismatch is visible — `contract_source.url` and `execution.repository` are both in the result — but nothing refuses it. Binding them is a rule the contract did not ask for, and it would break a governance repository holding the issue for work done elsewhere. A later policy comparing the two is the right place for that question.

**A passing test is not a good specification of a requirement.** This ADR establishes that the named test ran and what it said. Whether that test actually proves the criterion is the contract author's judgment, and no tooling replaces it.

Nothing here reaches policy. No work result is fed to OPA, no Check is published, no merge is authorized, and no artifact is downloaded. The seam ADR 8 put between work and transition is untouched.

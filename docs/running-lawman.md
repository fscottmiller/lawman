# Running Lawman

Lawman makes two separate calls:

* **Work Contract → Bound Evidence → Work Contract Result** asks whether one piece of work met its acceptance criteria. The contract comes from a local file or from the GitHub Issue that ordered the work.
* **Intent → Policy Selection → OPA → Decision** asks whether policy allows a transition.

A satisfied work contract does not authorize a transition. Policy still decides what is allowed. Transition execution is not built yet.

Python 3.11+. Work-contract satisfaction needs nothing else. Transition decisions need OPA.

## Installing OPA

Lawman does not evaluate transition policy — it delegates to [Open Policy Agent](https://www.openpolicyagent.org/) ([ADR 9](decisions/0009-delegate-transition-policy-to-opa.md)). Install one exact version and put it on `PATH`; CI installs **OPA 1.19.0** and verifies its checksum.

```bash
curl -fsSL -o /usr/local/bin/opa \
  https://github.com/open-policy-agent/opa/releases/download/v1.19.0/opa_linux_amd64_static
chmod +x /usr/local/bin/opa
opa version
```

`opa` is found on `PATH`. There is no flag naming it, and no environment variable overriding it. Without it, Lawman reaches no transition decision at all — it refuses with exit `2`.

## Work contract satisfaction

A work contract names explicit acceptance criteria, and each one names the source that can prove it ([ADR 11](decisions/0011-acceptance-criteria-bind-their-evidence.md)). Evidence names exactly one criterion, one traceable source, and whether that source passed:

```json
{
  "criteria": [
    { "id": "AC1", "description": "Invalid tokens return 401", "evidence_source": "test_invalid_token" },
    { "id": "AC2", "description": "Valid tokens return 200", "evidence_source": "test_valid_token" }
  ]
}
```

```json
{
  "evidence": [
    { "criterion_id": "AC1", "source": "test_invalid_token", "passed": true }
  ]
}
```

Evidence is a list so duplicate entries can be refused instead of silently overwritten. The evidence schema is unchanged; what changed is which entries a criterion will accept.

### What a binding means

Each criterion requires exactly one evidence source, and no source may prove two criteria. An entry applies only when its `criterion_id` **and** its `source` are the ones the contract named. Matching is exact and case-sensitive.

The identifier is opaque. Lawman does not interpret test names, paths, check names, or prefixes; it does not run the source, fetch it, or check that it exists. Binding says which proof was owed — not that the proof is trustworthy.

Run the complete example:

```bash
python -m lawman work \
  --contract examples/work-contract/contract.json \
  --evidence examples/work-contract/evidence.json
```

Each criterion becomes exactly one of:

* `proven` — the bound source was presented and passed
* `failed` — the bound source was presented and failed
* `unproven` — no evidence named the criterion

The result is satisfied only when every criterion is proven. Missing evidence fails closed as `unproven`. A valid but unsatisfied result exits `1`; a satisfied result exits `0`.

Results follow contract order, and every criterion appears:

```json
{
  "id": "AC3",
  "description": "Authentication failures emit an audit event",
  "evidence_source": "test_authentication_audit_event",
  "status": "unproven",
  "source": null,
  "explanation": "Unproven: no evidence from test_authentication_audit_event was provided."
}
```

`evidence_source` is what the contract requires; `source` is what was presented, or `null` when nothing was. Use `evidence-missing-audit.json` to see an explained `unproven` result.

### Unsatisfied is not refused

A missing entry is an unsatisfied result; a wrong source is malformed evidence. Silence is something the contract anticipated, so it is reported. A passing claim against a source nobody bound is not an answer to the obligation, so it is refused rather than counted or quietly dropped:

| Situation | Exit |
| --- | --- |
| the bound source reports `false` | `1` |
| no evidence names the criterion | `1` |
| evidence names a criterion but not the source it bound | `2` |
| evidence names a criterion the contract does not | `2` |
| evidence repeats a criterion | `2` |
| a criterion has no `evidence_source`, or a blank one | `2` |
| two criteria share one `evidence_source` | `2` |

`evidence-wrong-source.json` is a claim against the wrong source: it exits `2`, prints no result, and says which source AC3 actually requires.

A contract without `evidence_source` is refused, and no default is supplied. Lawman cannot safely guess which source was meant to prove a criterion.

This command needs no OPA. Work contracts are Lawman's own model, and they are not transition policy ([ADR 8](decisions/0008-work-contracts-are-separate-from-transition-policy.md)).

## Work contracts from a GitHub Issue

A local contract file is written by whoever runs Lawman. An issue is not. Point Lawman at the issue that ordered the work, and the criteria come from there ([ADR 10](decisions/0010-work-contracts-can-come-from-github-issues.md)):

```bash
python -m lawman work \
  --issue https://github.com/fscottmiller/lawman/issues/8 \
  --evidence evidence.json
```

`--contract` and `--issue` are alternatives. Exactly one is required, and `--evidence` is always required.

### The exact issue syntax

The issue body may be any prose you like, and it must contain **exactly one** fenced block tagged `lawman-work-contract`:

````markdown
Some prose explaining the work. None of this is read.

```lawman-work-contract
{
  "criteria": [
    { "id": "AC1", "description": "Invalid tokens return 401", "evidence_source": "test_invalid_token" },
    { "id": "AC2", "description": "Valid tokens return 200", "evidence_source": "test_valid_token" }
  ]
}
```
````

The block holds exactly what a `--contract` file holds. Everything else in the issue — prose, headings, task lists, other fenced blocks, labels, comments, title, assignees — is ignored. Nothing is inferred: **a checklist is not acceptance criteria.**

### Authentication

`GITHUB_TOKEN` is read from the environment when it is set, and sent as a bearer token:

```bash
GITHUB_TOKEN="$(gh auth token)" python -m lawman work --issue "$ISSUE_URL" --evidence evidence.json
```

No argument accepts a token, and no token is ever printed — not in a result, not in a diagnostic. A `GITHUB_TOKEN` carrying whitespace or control characters is refused before any request is made, because the HTTP layer's own complaint about an illegal header value quotes that value back. A public issue reads without one. Lawman makes exactly one request: a REST `GET` of the named issue. It reads no comments, follows no redirects, and writes nothing.

### What the result says about its source

A GitHub-backed result adds `contract_source` in front of the usual document:

```json
{
  "contract_source": {
    "type": "github_issue",
    "url": "https://github.com/fscottmiller/lawman/issues/8",
    "node_id": "I_kwDOexample",
    "updated_at": "2026-08-08T00:00:00Z",
    "contract_sha256": "sha256:6a1e09b344ecc7219ade4e2a9e67abce96430b7439d29d2abe21b0a0ff680636"
  },
  "satisfied": false,
  "criteria": []
}
```

* `node_id` says **which issue**, permanently. It survives renaming the repository or the owner; the URL does not.
* `contract_sha256` says **which contract**. It is a SHA-256 of the normalized semantic contract: criteria in issue order, each reduced to `id`, `description`, and `evidence_source`, sorted keys, compact separators, UTF-8, lowercase hex. Rewording the prose or reindenting the JSON does not move it; changing a criterion does, and so does **changing only a binding** — the source a criterion requires is part of the obligation ([ADR 11](decisions/0011-acceptance-criteria-bind-their-evidence.md)).
* `updated_at` is trace information, not identity. Any edit to the issue moves it.

The local `--contract` result is unchanged and carries no `contract_source`.

### What is refused

Exit `2`, nothing on stdout, one line on stderr:

| Situation | Exit |
| --- | --- |
| the URL is not `https://github.com/{owner}/{repo}/issues/{number}` | `2` |
| the URL names a pull request, or carries a query or a `#comment` fragment | `2` |
| the issue has no `lawman-work-contract` block, or more than one | `2` |
| the block is not valid JSON, or repeats a JSON key | `2` |
| the contract violates the usual work-contract rules — no criteria, duplicate IDs, blank description, a missing or shared `evidence_source` | `2` |
| the issue is inaccessible, or GitHub returns an HTTP error | `2` |
| the network fails, the read times out, or GitHub redirects elsewhere | `2` |
| GitHub answers with a different issue than the one requested | `2` |
| evidence names a criterion the issue does not, or a source the issue did not bind | `2` |

A valid contract behaves exactly as a local one: exit `0` when every criterion is proven, exit `1` when one is not.

### What this does and does not prove

The contract came from the identified issue rather than from caller-controlled local input. That is all "authoritative" means here.

**Reading an issue does not prove the caller chose the right issue**, and a satisfied issue contract still authorizes nothing. This command reaches no policy and runs no OPA; the source identity is there so later policy can check the relationship itself, instead of trusting an unbound `work_satisfied: true`.

Binding narrows what a claim may be made of, not who made it. **Lawman does not retrieve evidence**: the presented document still says what passed, and nothing here proves that the named source ran, exists, or told the truth.

## Work evidence from GitHub Actions

An issue contract with a caller-written evidence file still leaves half the question open: the document is typed by whoever wants it to pass. Run Lawman inside the GitHub Actions job that ran the tests, and the evidence comes from the tests instead ([ADR 12](decisions/0012-work-evidence-comes-from-the-execution.md)):

```bash
python -m lawman work \
  --issue "$ISSUE_URL" \
  --junit junit.xml
```

`--junit` replaces `--evidence`; exactly one of the two is required. `--junit` also requires `--issue`, because deriving proof against criteria the claimant wrote proves nothing new.

### Producing the report

Any test runner that writes a JUnit XML report will do. JUnit is the interchange format here, not a Lawman concept and not a Python one:

```yaml
- run: pytest --junitxml=junit.xml
  continue-on-error: true
- run: python -m lawman work --issue "$ISSUE_URL" --junit junit.xml
```

`continue-on-error: true` is the load-bearing line: a failing test should reach Lawman as a `failed` criterion, not end the job before the contract is judged. The complete workflow is [`examples/github-actions/verify-work.yml`](../examples/github-actions/verify-work.yml).

The report must be written by this job. Lawman opens the path it is given, reads it once, and writes nothing — it downloads no artifact and looks up no workflow run.

### How a test identity binds to `evidence_source`

A test case answers to two names, and both are strings the report itself wrote:

```xml
<testsuites>
  <testcase classname="tests.test_auth.Tokens" name="test_invalid_token"/>
</testsuites>
```

* `test_invalid_token` — the `name` attribute
* `tests.test_auth.Tokens.test_invalid_token` — `classname` + `.` + `name`

A criterion's `evidence_source` is one of those two strings exactly, or it matched nothing at all. There is no prefix, suffix, substring, case fold, or alias — `TEST_INVALID_TOKEN`, `Tokens.test_invalid_token`, and `tests/test_auth.py::Tokens::test_invalid_token` are three different sources, and none of them is the two above. Bind whichever of the two names is unique in your suite.

### The revision the result is bound to

A derived result says which execution produced it:

```json
{
  "execution": {
    "type": "github_actions",
    "repository": "fscottmiller/lawman",
    "revision": "9f8e7d6c5b4a39281706f5e4d3c2b1a09f8e7d6c",
    "run_id": "17285941003",
    "run_attempt": "1"
  }
}
```

* `revision` is `GITHUB_SHA` — **the exact commit this execution checked out and tested.** On a `pull_request` event that is the merge commit, which is what actually ran; Lawman reports what was tested rather than a branch head it never saw.
* `GITHUB_ACTIONS`, `GITHUB_REPOSITORY`, `GITHUB_SHA`, `GITHUB_RUN_ID`, and `GITHUB_RUN_ATTEMPT` are all required, and all read from the environment. A missing or malformed one is refused with exit `2`.
* Nothing is repaired: an abbreviated SHA, an uppercased one, or one with a newline appended is refused, because a value Actions did not set is somebody's edit.
* **No argument supplies any of it.** There is no `--revision`, `--sha`, `--run-id`, or `--repository`, so the party asking to be judged cannot choose the revision it is judged against.

A presented `--evidence` document carries no `execution` block. It cannot honestly claim one, so none is invented.

### What each outcome means

| CI evidence | Criterion status | Exit |
| --- | --- | --- |
| the bound test is present and passed | `proven` | `0` only when every criterion is proven |
| the bound test is present and failed or errored | `failed` | `1` |
| the bound test is absent from the report | `unproven` | `1` |
| the bound test was skipped | `unproven` | `1` |

**A skipped test reported no outcome.** It produces no evidence entry: calling it a failure blames a test that never ran, and calling it a pass is the substitution this tool exists to prevent. Job success is not proof either — the named test has to be in the report.

Refusals are unchanged in kind: exit `2`, nothing on stdout, one line on stderr.

| Situation | Exit |
| --- | --- |
| `GITHUB_ACTIONS` is not `true` | `2` |
| `GITHUB_SHA` is missing, abbreviated, uppercased, or padded | `2` |
| `GITHUB_REPOSITORY`, `GITHUB_RUN_ID`, or `GITHUB_RUN_ATTEMPT` is missing or malformed | `2` |
| the report is missing, unreadable, or not well-formed XML | `2` |
| the report's root element is not `<testsuites>` or `<testsuite>` | `2` |
| a `<testcase>` carries no name | `2` |
| two test cases answer to one bound identity | `2` |
| the report is larger than 8388608 bytes | `2` |
| `--junit` is used without `--issue` | `2` |

An unreadable report is never read as "no tests ran": a parse failure that became `unproven` would make every truncated write look like an honest result.

### What this v0 does and does not prove

The supported path is deliberately narrow: **GitHub Actions only, running inside the execution, reading one JUnit report.** Remote workflow-run discovery, artifact downloads, the Checks API, other CI providers, evidence that is not a test report, and any evidence-provider plugin framework are all deliberately absent.

The report is trusted as a product of the execution. Lawman does not prove the XML came from the test runner rather than from an `echo` — what it refuses to accept is a hand-written claim that a required test passed.

The execution context is an assumption about the environment, not a verified fact. `GITHUB_ACTIONS=true` and four plausible values can be exported anywhere; Lawman reads the environment Actions sets, and does not authenticate the run. A derived result is worth what the reader's knowledge of where it ran is worth.

`execution.repository` is reported, not enforced. It is never compared to the repository in the issue URL, so a fork's green run can satisfy an upstream issue's contract. Both values are in the result, and comparing them is a policy question rather than this command's.

And a passing test is not a good specification of a requirement. This says the named test ran, and what it said. Whether that test proves the criterion is the contract author's judgment.

Satisfying a work contract this way still authorizes nothing. No work result reaches OPA, no Check is published, and no merge is decided.

## Transition policy

Deployment to production is allowed only when tests have passed and a human has approved — because that is what this repository's Rego says, not because Lawman believes it.

```bash
python -m lawman \
  --intent examples/deploy-to-production/intent.json \
  --evidence examples/deploy-to-production/evidence.json
```

```json
{
  "allowed": true,
  "intent": { "action": "deploy", "target": "production" },
  "reasons": [
    "Tests passed.",
    "A human approved this deploy."
  ]
}
```

Swap in `evidence-tests-failed.json` and the same command denies:

```json
{
  "allowed": false,
  "intent": { "action": "deploy", "target": "production" },
  "reasons": [
    "Tests did not pass, or no test result was presented.",
    "A human approved this deploy."
  ]
}
```

The exit code carries the verdict: `0` allowed, `1` denied, `2` Lawman never reached a policy decision.

Reasons are reported in the order the policy emitted them. Lawman does not sort them, deduplicate them, or write them.

## Where policies come from

Not from the caller. The requester passes an intent and evidence; Lawman resolves the policy itself, from a registry checked into the repository being governed:

```text
.lawman/
  policies.json                      the registry
  policies/deploy-production.rego    the policy it points at
```

```json
{
  "deploy": {
    "production": "policies/deploy-production.rego"
  }
}
```

* The registry is nested the way an intent is shaped: action, then target. `deploy -> production` is looked up, not named — the pair has no identity of its own.
* The value is a path relative to `.lawman/`, and it must stay inside `.lawman/` — an absolute path, a `..` climb, or a symlink out is refused.
* `.lawman/` itself is relative to the current working directory, so **run Lawman from the root of the repository it is governing.**

Governing a new intent is two files: an entry in the registry, and the policy. There is no `--policy`, `--contract`, `--data`, or `--query` flag, and adding one would hand the party asking for permission an edit on the rules. The reasoning is in [ADR 6](decisions/0006-the-repository-picks-the-contract.md).

### What OPA is asked

Lawman evaluates one fixed decision document:

```text
data.lawman.decision
```

Every selected policy exposes it, and the query is not configurable. OPA receives one input object:

```json
{
  "intent": { "action": "deploy", "target": "production" },
  "evidence": { "tests_passed": true, "human_approved": true }
}
```

The intent is validated. The evidence is passed through whole — Lawman does not know which keys matter, what type a value should be, or what an absent key means. It checks only that the whole tree is JSON, and snapshots it, so evidence cannot change between being presented and being judged. That is the policy's job:

```rego
package lawman

default allowed := false

allowed if {
	tests_passed
	human_approved
}

tests_passed if input.evidence.tests_passed == true

human_approved if input.evidence.human_approved == true

decision := {
	"allowed": allowed,
	"reasons": array.concat(tests_reason, approval_reason),
}
```

`.lawman/policies/deploy-production.rego` is the complete version.

### What OPA must return

Exactly one defined decision, and nothing else:

```json
{
  "allowed": true,
  "reasons": ["Tests passed and human approval was recorded."]
}
```

* `allowed` must be `true` or `false`. Nothing is coerced.
* `reasons` must be a list of at least one non-empty string — **including for an allowed decision**. A permit nobody can explain is the failure this tool exists to prevent.
* Any other field is refused, not ignored. A policy returning something Lawman drops is a policy whose author believes it is being read.

Because `data.lawman.decision` is a fixed document, evolving policy means evolving Rego. Changing what `deploy -> production` requires is a change to one `.rego` file and its Rego tests; Lawman's Python does not move.

### Refusing is not denying

`2` is not a quiet `1`. Exit `1` means a policy was evaluated and said no. Exit `2` means Lawman never got that far:

| Situation | Exit |
| --- | --- |
| the policy returned `allowed: false` | `1` |
| no policy configured for this intent | `2` |
| `.lawman/policies.json` missing, unreadable, or malformed | `2` |
| the configured policy file is missing, or escapes `.lawman/` | `2` |
| `opa` is not installed, or exits non-zero | `2` |
| OPA output is unreadable, or evaluation is interrupted | `2` |
| OPA does not answer within the fixed 30-second bound | `2` |
| `data.lawman.decision` is undefined, empty, or not exactly one decision | `2` |
| the decision is missing `allowed`, missing `reasons`, or has unknown fields | `2` |

Both refuse the transition, so a pipeline gating on `exit == 0` is safe either way. Only one of them is a verdict, and "the tests failed" calls for a different response than "nobody configured this."

## The model

Four things on the transition side:

* **Intent** — the action being requested. `{"action": "deploy", "target": "production"}`
* **Policy** — Rego, owned by the governed repository, exposing `data.lawman.decision`.
* **Evidence** — a JSON object, whatever the policy needs. `{"tests_passed": true, "human_approved": true}`
* **Decision** — `allowed`, the intent, and the policy's ordered reasons.

Work contracts keep their own model — names, explicit evidence bound to the source that must prove it, and silence is never proof ([ADR 3](decisions/0003-a-requirement-is-a-name.md), [ADR 4](decisions/0004-silence-is-not-proof.md), [ADR 11](decisions/0011-acceptance-criteria-bind-their-evidence.md)). The two do not mix: a work-contract result is not policy input, and policy is not an acceptance criterion.

## The tests

```bash
python -m unittest discover -s tests
```

Tests that need the real OPA skip when it is not installed. CI installs the pinned version, so CI runs all of them.

The type and style checks need their tools, pinned in `requirements-dev.txt` and configured in `setup.cfg`:

```bash
pip install -r requirements-dev.txt
python -m mypy                              # strict, over lawman/
python -m flake8
python -m isort --check-only lawman tests
```

CI runs both, in separate jobs. Why they are configured rather than left on defaults is [ADR 7](decisions/0007-check-types-and-style-in-ci.md).

Every acceptance criterion has a named test.

Working — `tests/test_work.py`:

| Behavior | Test |
| --- | --- |
| every criterion binds one non-empty source | `BindsEveryCriterionToOneSource.test_every_criterion_requires_one_evidence_source` |
| no source proves two criteria | `BindsEveryCriterionToOneSource.test_contract_requires_unique_evidence_sources` |
| an entry applies only to the source it was bound to | `AcceptsOnlyTheSourceTheContractBound.test_evidence_must_match_the_bound_source_exactly` |
| bound evidence → proven or failed | `AcceptsOnlyTheSourceTheContractBound.test_bound_evidence_determines_proven_and_failed` |
| silence about the bound source → unproven | `AcceptsOnlyTheSourceTheContractBound.test_missing_bound_evidence_is_explicitly_unproven` |
| every binding accounted for, in contract order | `AcceptsOnlyTheSourceTheContractBound.test_results_account_for_every_binding_in_contract_order` |
| malformed, duplicate, or unknown input → refuse | `RefusesMalformedOrAmbiguousInput` |
| direct construction preserves invariants, results are immutable | `HoldsItsInvariantsWhenConstructedDirectly.test_bound_work_domain_is_immutable_and_cannot_bypass_invariants` |

`tests/test_work_cli.py` covers the same capability through `python -m lawman work`, including exit codes and byte-identical output. `test_unknown_duplicate_or_misbound_evidence_is_refused` pins the refusals, `test_binding_is_deterministic_and_transition_policy_is_untouched` pins determinism and the untouched transition surface, and `test_local_work_contract_command_remains_byte_identical` pins the local result's exact bytes. `tests/test_cli.py`'s `TheWorkCommandIsUntouched` proves it still runs with no OPA on `PATH`.

Reading an issue — `tests/test_github.py`, against a local stand-in GitHub (`tests/fake_github.py`), never a live issue:

| Behavior | Test |
| --- | --- |
| exactly one of `--contract` and `--issue`, and always `--evidence` | `TheContractSourceIsTheOnlyThingItProves.test_work_requires_exactly_one_contract_source` |
| one authenticated `GET`, and the token never leaves the environment | `ReadsTheContractFromTheIssue.test_issue_contract_uses_authenticated_read_only_get_without_leaking_token` |
| only the single tagged block is read | `ReadsTheContractFromTheIssue.test_only_the_single_tagged_contract_block_is_parsed` |
| missing, duplicated, or malformed blocks → refuse | `RefusesAnythingItCannotReadAsAContract.test_missing_duplicate_or_malformed_contract_blocks_are_refused` |
| bad URLs, HTTP errors, timeouts, and mismatched responses → refuse | `RefusesAnythingItCannotReadAsAContract.test_invalid_urls_and_github_failures_are_refused` |
| local and issue contracts bind and evaluate identically | `ReadsTheContractFromTheIssue.test_local_and_github_contracts_bind_evidence_identically` |
| source identity is bound to the contract's content | `SaysWhichContractItJudged.test_issue_contract_source_has_content_bound_identity` |
| changing only a binding changes the hash | `SaysWhichContractItJudged.test_contract_identity_is_bound_to_required_evidence` |
| satisfied exits `0`, unsatisfied exits `1` | `SaysWhichContractItJudged.test_issue_contract_returns_satisfied_and_unsatisfied_results` |
| identical responses produce identical bytes | `SaysWhichContractItJudged.test_issue_contract_output_is_byte_identical_across_runs` |
| no policy is selected, and no transition is authorized | `TheContractSourceIsTheOnlyThingItProves.test_issue_contract_evaluation_does_not_invoke_transition_policy` |

Proving from an execution — `tests/test_ci.py`, against the stand-in GitHub and a JUnit report written into a temporary directory, with the Actions environment patched in:

| Behavior | Test |
| --- | --- |
| an issue contract is proven from this run's report, with no evidence document | `DerivesEvidenceFromTheExecution.test_github_work_can_derive_evidence_from_junit` |
| the execution is required, unrepaired, reported, and never an argument | `DerivesEvidenceFromTheExecution.test_ci_evidence_is_bound_to_actions_revision` |
| two identities per case, matched exactly, and nothing near them | `DerivesEvidenceFromTheExecution.test_junit_test_identity_matching_is_exact` |
| a passing case → `proven` | `DerivesEvidenceFromTheExecution.test_passing_junit_case_proves_bound_criterion` |
| a failure or an error → `failed` | `DerivesEvidenceFromTheExecution.test_failing_junit_case_fails_bound_criterion` |
| an absent or skipped case → `unproven`, with nothing invented | `DerivesEvidenceFromTheExecution.test_missing_junit_case_remains_unproven` |
| two cases answering to one bound identity → refuse | `DerivesEvidenceFromTheExecution.test_ambiguous_junit_identity_is_refused` |
| missing, unreadable, oversized, or malformed report → refuse | `DerivesEvidenceFromTheExecution.test_invalid_junit_report_is_refused` |
| CI code produces `WorkEvidence`; the work domain still decides | `DerivesEvidenceFromTheExecution.test_ci_collection_delegates_to_existing_work_evaluator` |
| the local-file and issue-plus-evidence paths are unchanged | `DerivesEvidenceFromTheExecution.test_existing_work_evidence_paths_remain_unchanged` |
| identical contract, execution, and report → identical bytes | `DerivesEvidenceFromTheExecution.test_ci_evidence_evaluation_is_deterministic` |

Deciding — `tests/test_opa.py`:

| Behavior | Test |
| --- | --- |
| the verdict comes from the OPA process, not from Python | `EvaluatesThroughAnExternalOpa.test_transition_decision_is_evaluated_by_external_opa` |
| OPA gets the intent and the evidence, uninterpreted | `EvaluatesThroughAnExternalOpa.test_opa_receives_intent_and_uninterpreted_evidence` |
| undefined, empty, multiple, or schema-invalid decision → refuse | `RefusesAnythingThatIsNotOneWellFormedDecision.test_invalid_opa_decisions_are_refused` |
| missing, failing, unreadable, or interrupted OPA → refuse | `RefusesAnythingThatIsNotOneWellFormedDecision.test_opa_execution_failures_are_refused` |
| the real pinned OPA decides the example | `TheRealOpaDecides.test_real_pinned_opa_evaluates_the_example_policy` |
| changing only the Rego changes the decision | `TheRealOpaDecides.test_changing_only_rego_changes_the_decision` |

Selecting — `tests/test_selection.py`:

| Behavior | Test |
| --- | --- |
| `deploy -> production` resolves to the checked-in `.rego`, and `contracts.json` no longer selects anything | `SelectsThePolicyTheRepositoryConfigured.test_repository_selects_policy_for_the_intent` |
| a policy beside the intent does not govern | `SelectsThePolicyTheRepositoryConfigured.test_a_policy_is_read_from_the_policy_directory_not_from_beside_the_intent` |
| missing, malformed, unconfigured, or escaping selection → refuse | `FailsClosedWhenItCannotFindTheRules.test_invalid_or_escaping_policy_selection_is_refused` |

`HoldsItsInvariantsWhenConstructedDirectly`, in `tests/test_selection.py`, `tests/test_decision.py`, and `tests/test_work.py`, covers the same invariants for code that builds the types directly rather than parsing them — including evidence and registries that cannot be rewritten once read.

`tests/test_cli.py` covers exit codes, byte-identical output across runs, and `TheCallerCannotChooseTheRules` — that no `--policy`, `--contract`, `--data`, or `--query` flag exists, and that the policy OPA is handed is the repository's, not one sitting beside the requester's files.

`tests/test_docs.py` checks that this guide, the example workflow, ADR 9, ADR 10, ADR 11, and ADR 12 still describe the interface the code actually has.

## Why it looks like this

The decisions behind this slice, and the arguments against the alternatives, are in [`decisions/`](decisions/).

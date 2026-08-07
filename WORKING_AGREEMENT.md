# Working Agreement

This document describes how we build Lawman.

It is a development preference, not a Lawman policy. It governs contributors to Lawman itself; it does not impose these preferences on teams or repositories that use Lawman.

## Ponytail everything

Ponytail is an engineering discipline inspired by [Dietrich Gebert's Ponytail](https://github.com/DietrichGebert/ponytail). It is YAGNI expanded into a practical decision ladder: stop at the first rung that solves the problem.

1. Does this need to exist? If not, do not build it.
2. Does it already exist in the codebase? Reuse it.
3. Does the standard library solve it? Use it.
4. Does a native platform feature solve it? Use it.
5. Does an installed dependency solve it? Use it.
6. Can it be one line? Make it one line.
7. Only then, write the minimum that works.

The ladder runs after we understand the problem, not instead of understanding it. It applies to implementation choices within an established boundary. Choosing or replacing a boundary — such as a dependency at a seam, a provider, or an execution layer — is a tool choice governed by the next section.

Lazy means efficient, not careless: do not cut validation, error handling, security, accessibility, or anything explicitly requested. Prefer small abstractions and obvious next steps. Complexity must earn its place.

## Write for action

Lead with the answer. Add only the detail needed to act. Put deeper explanation below the useful surface.

## Choose the best tool for the job

Choose tools based on fit, correctness, security, cost, maintainability, and replaceability — not familiarity or habit.

Use a specialist tool when it is genuinely the best fit. Keep important boundaries portable so tools, models, and providers can change without rewriting the system.

## Contracts before agents

Define the intent, contract, evidence, decision, and transition before designing orchestration.

Agents can help shape and execute work. They do not define their own acceptance criteria or decide whether their work is acceptable.

For Lawman itself, agent-authored contributions follow the same review and evidence path as human-authored contributions.

## Evidence over assertion

Every acceptance criterion is covered by at least one named automated test, and the mapping from criterion to test is explicit. Tests may contain multiple cases or assertions, and one test may cover multiple related criteria. Every test runs in CI. Pull-request checks run the complete test suite; they do not selectively omit tests.

Documentation should make claims that can be checked, and implementation decisions should leave enough evidence to explain what happened and why.

## Build the smallest proving slice

Prefer the smallest end-to-end capability that tests the model in reality. Do not build speculative infrastructure, orchestration, or interfaces before the core behavior is proven.

This is a preference for how we build Lawman. It is not a requirement that Lawman impose minimal changes on its users.

## Record meaningful decisions

When a decision is likely to matter again, record a short rationale close to the relevant code or documentation. Prefer a durable explanation over repeatedly rediscovering the same design question.

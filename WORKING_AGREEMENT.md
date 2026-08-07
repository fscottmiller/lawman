# Working Agreement

This document describes how we build Lawman.

It is a development preference, not a Lawman policy. It governs contributors to Lawman itself; it does not impose these preferences on teams or repositories that use Lawman.

## Ponytail everything

Use the lazy ladder:

1. Lead with the answer.
2. Add only the detail needed to act.
3. Put deeper explanation below the useful surface.

Prefer concise prose, small abstractions, and obvious next steps. Complexity must earn its place.

## Choose the best tool for the job

Choose tools based on fit, correctness, security, cost, maintainability, and replaceability — not familiarity or habit.

Use a specialist tool when it is genuinely the best fit. Keep important boundaries portable so tools, models, and providers can change without rewriting the system.

## Contracts before agents

Define the intent, contract, evidence, decision, and transition before designing orchestration.

Agents can help shape and execute work. They do not define their own acceptance criteria or decide whether their work is acceptable.

## Evidence over assertion

Every acceptance criterion maps to exactly one automated test. Every test runs in CI. Pull-request checks execute the complete relevant suite across the environments that matter.

Documentation should make claims that can be checked, and implementation decisions should leave enough evidence to explain what happened and why.

## Build the smallest proving slice

Prefer the smallest end-to-end capability that tests the model in reality. Do not build speculative infrastructure, orchestration, or interfaces before the core behavior is proven.

This is a preference for how we build Lawman. It is not a requirement that Lawman impose minimal changes on its users.

## Keep humans and agents on the same path

The author may be a human, an agent, a tool, or a combination. The governance path remains the same:

> Intent → Contract → Work → Evidence → Decision → Transition

Actor identity may affect policy — for example, a contract may require human approval — but it never creates a bypass.

## Agents are workers, not authorities

Agents may propose, produce, refactor, test, and explain work. They do not get to reinterpret the contract, waive required evidence, or decide that their own work is acceptable.

## Record meaningful decisions

When a decision is likely to matter again, record a short rationale close to the relevant code or documentation. Prefer a durable explanation over repeatedly rediscovering the same design question.


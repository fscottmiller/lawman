# Lawman

No matter what your AI agents think, your SDLC isn’t the Wild West.

Lawman sits between intent and consequence, watching every change like a quiet judge that never sleeps. Agents can write, propose, refactor, test — but they do not decide.

> **Agents can run wild. Production can’t.**<br>
> **Lawman keeps the peace.**

That’s the whole system.

## What is it?

Lawman is a governance layer for autonomous software delivery.

It coordinates agents, tools, and pipelines — not by trusting them, but by constraining them. Every consequential change must satisfy its contract and applicable policy, backed by evidence, before it becomes reality.

If it can’t be proven, it doesn’t happen.

### Why does it exist?

Because autonomous systems don’t fail by being too weak.

They fail by being too confident, too permissive, and too eager to build.

Lawman removes confidence from the wrong places and puts it where it belongs: in rules, evidence, and repeatability.

### What does it do?

A change enters as intent.<br>
From there, Lawman drives it through a controlled sequence:

Intent → Contract → Work → Evidence → Decision → Transition

The goal is not to maximize agent activity. The goal is to produce changes that empirically satisfy the contract.

### What is it NOT?

* Not an agent framework
* Not a CI system
* Not a deployment tool
* Not a model wrapper

Those things may exist inside it, but they are not it.

Lawman is the authority they answer to.

## The Laws

* Contracts define what “done” means
* Evidence proves what is true
* Policy decides what is allowed
* Nothing is trusted by identity
* Models, agents, providers, and execution layers are replaceable
* Agents do not get to reinterpret any of the above

No implicit exceptions. No “creative autonomy.” No silent overrides.

Lawman does not decide how software should be built. The contract does.

A repository may demand minimal changes, exhaustive testing, human approval, independent review, or none of the above. Lawman’s job is not to choose those rules. Its job is to enforce them.

## The System

GitHub keeps the record.<br>
Lawman makes the call.

Everything else is just movement.

Lawman should own as little as possible. It reads authoritative state, evaluates the applicable contracts and policies, authorizes the next transition, and records why.

The workers can change. The rules can change. The enforcement persists.

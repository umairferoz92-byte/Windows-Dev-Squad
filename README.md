# Windows Dev Squad

**Your own AI development crew — guarded, budgeted, and honest.**

> **⚠️ Under Active Development** — This is an early-stage, private project. Not ready for general use.

## What It Is

Windows Dev Squad turns a single AI into a disciplined crew of specialized agents.
You give it one task. It plans, codes, tests, and reviews — then hands you one
reviewed branch and one honest report. Nothing merges, pushes, or deploys without
your explicit approval.

## What Makes It Different

- **🛡️ The Guard** — Every action passes through a default-deny security guard.
- **💰 The Budget Layer** — Estimates worst-case cost before every model call.
- **🔒 Real Isolation** — AI code never runs in your main Windows account.
- **🧠 A Crew, Not a Monolith** — Captain, Ironman, Tester, Batman, Quality.
- **📋 Honest by Design** — Reports include a dedicated "not checked" section.

## Status

**🚧 Phase 0 in progress.**

`squad doctor` is live and reports your machine's real isolation capabilities.
The guard, budget layer, and agent crew are being built in test-first phases.

## Planned Commands

```text
squad doctor [--setup-help]
squad check
squad run [--dry-run]
squad status
squad cost
squad logs [--follow]
squad audit
squad stop
squad providers test

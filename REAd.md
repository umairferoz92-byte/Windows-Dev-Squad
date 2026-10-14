Windows Dev Squad
Your own AI development crew — guarded, budgeted, and honest to a fault.

⚠️ Under Active Development — This is a private, early-stage project. The foundation is being built phase by phase. Not yet ready for general use.

The Problem
AI can write code. But letting it loose on your machine is a gamble: it burns through credits, touches files it shouldn't, runs commands you didn't approve, and tells you it's "done" when it isn't. You're left babysitting a black box that's expensive, unpredictable, and impossible to audit.

The Solution
Windows Dev Squad is a Windows-first toolkit that turns a single AI into a disciplined crew of specialized agents — each with a name, a role, a write scope, and a hard budget. You give it a task. It plans, codes, tests, reviews, and hands you a finished branch with a full report. You stay in command the entire time.

This isn't a chatbot with a system prompt. It's an operating system for accountable AI development.

What Makes It Different
🛡️ The Guard
Every action an agent takes — every file read, every command run, every line written — passes through a default-deny security guard. Unknown requests ask for your approval. Dangerous patterns are blocked outright. Credentials, config, and audit logs are untouchable. The guard is not a sandbox — it's a gatekeeper that never sleeps, built on the standard library and nothing else.

💰 The Budget Layer
Before every model call, the squad estimates the worst-case cost. If it would breach any limit — per call, per agent, per task, per day, per month, per provider — the call is refused before a single token is spent. An append-only SQLite ledger tracks every cent. A spike breaker pauses everything if spending accelerates. You set the caps. Only you can raise them.

🔒 Real Isolation
AI-generated code never runs in your account. The squad detects what isolation your machine actually supports — low-privilege user, Windows Sandbox, dev VM, or WSL2 with network disabled — and refuses to run if the level is insufficient. It tells you plainly what it can and cannot verify. No false confidence.

🧠 A Crew, Not a Monolith
Named agents with distinct roles: Captain plans. Ironman codes. Tester verifies. Batman hunts security issues from scanner output only, never model opinion. Quality enforces standards. Each owns separate files. Each runs on its own branch. The Captain merges one at a time and re-runs every check.

📋 Honest by Design
Every run ends with a short report: what changed, what passed, what it cost, and a dedicated "not checked" section that tells you exactly what the squad did not verify. Security findings come only from raw tool output. Flaky tests are flagged. Skipped tests are called out. Diffs are capped. You get the truth, not a sales pitch.

💸 Cost Intelligence Built In
Cheap models for classification, summaries, and lint fixes. Strong models for planning and code — escalating only after two failed checks, with every escalation shown to you. Repo maps and diffs instead of whole files. Prompt caching. Tool output capped. --dry-run shows you the estimate before you commit. The squad is designed to be frugal by default.

What You Get
One reviewed git branch. Nothing merges, pushes, or deploys without your explicit approval.

One short report with diff, results, cost per agent, and flagged files.

A complete audit trail — append-only, hash-chained, exportable outside the repo.

A live terminal view with one card per agent: name, role, status, cost, files touched.

A remote web page (later) for approvals and monitoring from anywhere — never exposed to the public internet, never able to raise a budget, never able to run raw commands.

The Philosophy
AI should be powerful, but never unchecked. Fast, but never reckless. Honest, but never verbose. And it should always leave a trail you can audit.

Windows Dev Squad is built on a simple belief: the value of an AI developer isn't just the code it writes — it's the trust you can place in how it writes it.

Status
🚧 Under active development — Phase 0 complete.

The foundation is set: squad doctor is live and reporting your machine's real isolation capabilities. The guard, budget layer, and agent crew are being built in disciplined, test-first phases.

This is a private project. It is not yet packaged for public use, and many features described above are planned but not yet implemented. Follow along as each phase is completed and verified.

Built for Windows 11. Designed for accountability. Under construction — one verified step at a time

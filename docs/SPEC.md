# SPEC

Windows Dev Squad (`squad`) is a Windows-first toolkit where a crew of named
agents splits one development task. It plans (you approve the plan and
acceptance criteria), writes code, tests it, checks security and quality, and
hands you one reviewed branch and one short report. Nothing merges, pushes, or
deploys without your approval. It must be safe, auditable, cost-controlled, and
honest about what it did not check.

This document and `docs/RULES.md` are the source of truth. Re-read both at the
start of every phase after Phase 0.

---

## Environment

- Windows 11 laptop, 16 GB RAM, no GPU, PowerShell in Windows Terminal. The tool
  never runs as administrator and never asks for admin rights.
- May be Windows Home (no Windows Sandbox or Hyper-V). `squad doctor` must detect
  which isolation levels are really available and say so plainly.
- One-time admin setup (low-privilege Windows user + a per-user firewall rule
  that blocks that user's network) is done by the user manually, following steps
  printed by `squad doctor --setup-help`.
- Native Windows first. No dependence on WSL2 or Docker. The executor is a
  swappable backend so Windows Sandbox, a dev VM, or WSL2/Docker can be used when
  available.
- Windows first, not Windows only. All OS-specific behavior (shell, process
  killing, isolation, credential paths, destructive-pattern lists, path rules)
  sits behind an OS-adapter interface so Linux (bash, zsh) and macOS (zsh)
  adapters can be added later without touching the guard, budget, agents, or
  reports. CI runs on Windows, Linux, and macOS. A platform is marked
  experimental until its attack tests pass.
- Develop and test only on a throwaway practice repo until told otherwise.

## Models and providers

- Cloud models only, behind one provider interface: OpenRouter (main key), plus
  direct Claude, DeepSeek, Gemini, and OpenAI keys if added. A local-model
  provider slot (Ollama, LM Studio) is reserved for when a GPU exists. No Claude
  Code backend until asked.
- `.env.example` lists `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`,
  `OPENAI_API_KEY`, `GEMINI_API_KEY`, and `DEEPSEEK_API_KEY` with no values.
- Roles: planner, strong, worker, reviewer. Reviewers use a different model from
  the coder. Only providers in `allowed_providers` may be used.
- API keys are loaded only by the main process from `.env` or Windows Credential
  Manager, are never passed to subprocesses, and are unreadable by the agent
  user.
- OpenRouter: plain HTTPS (httpx) against its OpenAI-compatible API. Verify the
  base URL and option names in its docs before coding. Add `allowed_models` per
  role in `squad.yaml` and block any model not listed. Fill `prices.yaml` from
  its model list with an as-of date. Before each task, read the key's remaining
  credit limit/usage from its key endpoint and stop if low. Disable automatic
  fallback where the API allows. HTTP 402 (out-of-credit / key limit) is a stop,
  never a retry. Record the model that actually answered.
- A real-key smoke test exists only as the opt-in `squad providers test`, one
  tiny call, never run by CI or the default suite.
- Provider-side spend limits or prepaid credit plus one key per provider is the
  backstop; local counters are a second layer.

## Filesystem, paths, and encoding

- Use `pathlib`. Test paths with spaces, non-ASCII characters, junctions,
  case-insensitivity, short 8.3 names, and long paths.
- Force UTF-8 for all subprocess I/O. Normalize CRLF/LF in diffs.
- Support a custom CA bundle and proxy settings.

## Dependencies

- Runtime: `typer`, `rich`, `pyyaml`, `httpx`.
- Dev: `pytest`, `ruff`, `bandit`, `pip-audit`.
- `ctypes` from the standard library for Windows Job Objects (no pywin32 unless
  approved).
- No tokenizer package: estimate tokens conservatively (characters ÷ 3, rounded
  up) before a call, and use the provider's reported usage after it.
- Later, only after approval: FastAPI, uvicorn, a WebAuthn library.
- Add nothing else without asking.

## The squad

- **Captain** (coordinator): produces the plan and acceptance criteria (you
  approve before any code), assigns self-contained jobs, merges, writes the
  report. Writes nothing.
- **Ironman** (coder): writes only the repo's configured source paths, on its own
  git branch/worktree. Cannot edit tests; to change a test it asks Captain, the
  Tester makes the edit, and the report flags it.
- **Tester**: writes and runs tests from the approved criteria. Writes only
  configured test paths.
- **Batman** (security reviewer): read-only. Findings come only from scanner
  output, never from model opinion.
- **Quality**: lint, types, formatting, complexity, docs, diff review. Read-only;
  proposes fixes.

Identity fields: `name`, `role`, `persona`, `model alias`, `tools`,
`write scope`, `workspace`, `budget`. Write scopes and check commands are
configured per repo in `squad.yaml`. Permissions come only from guard profiles,
never from names, personas, or model output.

Crew size: 1 to `max_agents` (hard cap 10). `--agents N --names A,B,C`;
config keys `crew.size`, `crew.max_agents`, `crew.max_running`, `crew.names`.
The five core roles are always covered; beyond five, Captain splits work by file
ownership into extra coders, testers, and reviewers (docs, performance,
dependencies, integration, AI/prompt evals). Captain may recommend fewer agents
and say why; you can override with a cost warning. Each agent owns separate
files; dependencies are marked; Captain merges one branch at a time and re-runs
all checks. Names are unique plain-text labels, escaped everywhere, with no
permissions. Unnamed agents get automatic names. Crews can be saved as presets.
v0.1 runs agents one after another; Phase 8 runs them in parallel up to
`max_running`, sharing one task budget.

## Typed tools (no raw shell in v0.1)

- **Tier 0**: `read_file`, `search_code`, `repo_map`, `git_diff`, `git_status`,
  `run_security_scan` (fixed commands from `squad.yaml`). `run_tests`,
  `run_lint`, `run_typecheck` are Tier 0 only when the required isolation level
  is verified; otherwise Tier 2 (ask).
- **Tier 1**: `edit_file` within write scope (never `.git`, hooks, CI, or config
  files without approval); `git_commit` on the agent's own branch.
- **Tier 2 (always ask)**: `install_dependencies` (shows package, version,
  registry; runs from a lockfile or internal registry with install scripts
  disabled), anything needing network, anything outside the repo, anything
  unrecognized.
- **Tier 3 (blocked)**: `git_push`, raw shell, credential access, invoking squad,
  admin elevation, known destructive patterns.

The guard validates every call's arguments. Git calls run with hooks disabled
(`core.hooksPath` pointing at an empty folder) and ignore repo-level git config
that can run programs.

## Gates ("done" requires all)

- Tests, lint, type check, and build exit 0 in this run; a failing test is
  re-run once and flaky tests are reported.
- Test count not lower; skipped tests flagged; coverage not lower.
- No unresolved high/critical security finding unless you approve each; false
  positives go through a triage list you control.
- Every finding matches raw tool output.
- Changes to dependencies, lockfiles, CI workflows, package scripts, git hooks
  and config, build files, and lint/type/test/coverage configs are flagged in
  their own report section.
- Any test file changed by the coder is flagged.
- Diffs capped (default 400 changed lines).
- Spend stays inside the budget layer's limits.

## Credit control (budget package; agents cannot read or change it)

- Layers: per call (max input/output tokens), per agent, per task, per day, per
  month, per provider, in `squad.yaml`, modes `economy | balanced | max`.
- Before **every** model call, estimate worst-case cost (conservative input
  tokens + max output tokens at the model's price) and refuse the call if it
  would pass any layer. Warn at 50% and 80%, stop at 100%, never continue
  automatically. Only the human can raise a cap, from the terminal. The web page
  may only lower a cap or stop.
- `prices.yaml` holds model prices with an as-of date; warn when older than 30
  days; an unknown model is blocked. Never hard-code prices.
- If usage is not reported or a stream is cut off, record the maximum possible
  cost. Max 3 retries per call with backoff; retries count against the budget.
- Append-only SQLite ledger: run, agent, provider, model, tokens in/out, cached
  tokens, estimated cost, time. `squad cost` shows totals by day, task, agent;
  `squad cost --reconcile` compares the ledger with figures pasted from each
  provider's billing page and flags a gap over 10%.
- Spike breaker: if spend in a 5-minute window passes a limit, pause all agents
  and alert; only the human can resume from the terminal.
- Savings: cheap models for classification/summaries/test triage/lint fixes;
  strong models only for Captain's plan and Ironman's code, escalating only after
  two failed checks and showing each escalation; send a repo map, relevant
  snippets, and diffs instead of whole files; cap tool output sent to the model
  (head and tail); summarize history after N steps; use provider prompt caching
  with a stable prompt prefix where available; use formatters, autofix linters,
  and the test runner before any model; `--dry-run` shows an estimate labeled as
  an estimate.

## Data locations

Config the agents must not change, the cost ledger, the audit log, and
`prices.yaml` live in `%LOCALAPPDATA%\squad\`, outside the repo and unreadable
and unwritable by the agent user. Agent worktrees live in a separate folder. The
guard blocks all of these paths. At the end of each run, print the audit log's
latest hash and write it to a folder outside the repo that the user chooses
(e.g. a synced folder); no network is used for this.

## Interfaces

- **Windows Terminal**: `squad doctor [--setup-help] | check | run | status |
  cost | logs [--follow] | audit | stop | run --dry-run | providers test`; a live
  TUI (rich) with one card per agent (name, role, step, status, cost against
  budget, files touched); approvals in the terminal showing the exact command,
  folder, and reason; a Windows Terminal profile named Squad.
- **Remote web page (Phase 10)**: daemon serves on `127.0.0.1`; remote reach only
  through a private-network route (VPN, Tailscale, or Cloudflare Tunnel with an
  access login) forwarding to localhost over a valid HTTPS hostname; never port
  forwarding or a public URL. Capabilities: live status, agent cards and cost,
  read-only logs and reports, approve/deny pending commands (only a short
  allowlist of Tier 2 actions; installs and credential-related actions stay
  terminal-only), start tasks from saved templates only, lower a budget or stop
  everything. It cannot run raw commands, edit rules/scope/config, or raise a
  budget. Every approval shows which agent asked and why, has a short hold time,
  is bound to the exact command, and expires in 5 minutes. Security: passkey
  (WebAuthn) + token, short sessions, `squad remote revoke`, Origin and Host
  checks, CSRF protection, strict CSP, escaped output, rate limits, remote
  actions logged with device and time, `squad remote on` per task and off when
  the task ends or on idle timeout.
- **Phone push (optional)**: needs an approved notification service; notifications
  contain only "approval needed" or "budget warning" and a run id, never code,
  paths, or secrets. Until then, alerts appear in the terminal and web page.

## Layout

```
squad/guard, squad/budget, squad/providers, squad/tools, squad/exec,
squad/checks, squad/agent, squad/crew, squad/report, squad/tui, squad/gateway,
squad/cli; tests/, docs/RULES.md, docs/SPEC.md, squad.yaml, guard.yaml,
prices.yaml, .env.example, practice/
```

Packages never import upward; each works alone as a Python library. The name
`squad` clashes with an existing PyPI package, so the distribution is
`windows-dev-squad` while the CLI command stays `squad`.

## Build order

After each phase: stop, show what changed, how to run it, tests passing, and what
is NOT covered; wait for OK.

- **Phase 0** — docs, repo, git, pytest, ruff, bandit, pip-audit, CI on three
  OSes, practice repo, `squad doctor` + `--setup-help`.
- **Phase 1** — guard. 50+ adversarial tests FIRST (path traversal, junctions,
  symlinks, short names, encoded payloads, chaining, Windows bypasses,
  write-scope violations), show failing, then implement. Done when all pass and
  unknown requests default to ask.
- **Phase 2** — typed tools and Windows executor with Job Objects (ctypes),
  scrubbed environment, git hardening, isolation levels, behind an OS-adapter
  interface. Done when no orphaned processes remain and agent code never runs in
  the user's own account.
- **Phase 3 (v0.0)** — `squad check` runs tests, lint, security scans under the
  guard and writes one report. No model, no network.
- **Phase 4** — budget layer and provider adapters (OpenRouter first) with fully
  mocked tests. Done when an over-cap call is refused before it is sent, unknown
  models are blocked, unreported usage counted at worst case.
- **Phase 5** — single agent loop with step limits, loop detection, plan
  approval, verification-gated done, terminal approvals, audit log. Done when
  `squad run` fixes the failing practice test within budget.
- **Phase 6 (v0.1)** — sequential squad with crew size and names, gates, flagged
  files, one-page report (diff, results, cost per agent, "not checked" section),
  `squad run --dry-run`.
- **Phase 7** — Windows Terminal live view with agent cards, cost, in-view
  approvals.
- **Phase 8** — parallel squad with git worktrees, `max_running`, per-agent and
  shared budgets.
- **Phase 9** — attack tests (prompt injection, secret leaks, guard bypass,
  self-approval, budget bypass, escalation by names) against guard, budget, and
  agents; fix every failure.
- **Phase 10** — remote web page as specified.
- **Phase 11 (optional)** — Linux and macOS adapters with CI on all three, dev VM
  or WSL2/Docker backend, overnight queue and morning digest.
- **Phase 12** — industrial hardening: service mode running as the user with no
  admin rights, crash recovery, config validation that refuses unsafe settings,
  versioned releases with changelog and rollback, backups and retention, a
  runbook, and an independent review of the guard, budget, and gateway. Done when
  a fresh install is safe by default.

## How we work

- One small slice at a time; commit after each working step.
- Write tests before implementation for the guard, budget layer, redaction,
  approvals, and web login, including adversarial cases.
- After each module, say what could go wrong and what is untested.
- If a requirement is ambiguous, ask one question rather than guessing.
- Do not add features that were not requested.
- Tests must run offline with mocked model calls and no API keys.

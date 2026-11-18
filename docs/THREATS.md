# Threat Model

Threats are written per component and mapped to the [OWASP Top 10 for LLM Applications](https://owasp.org/www-project-top-10-for-llm-applications/). Every threat carries either a `Test:` link (a test file that covers it) or an explicit `Accepted risk:` note. A threat with neither is a gap.

## Assets
| Asset | Where it lives |
|---|---|
| Source code | work repo (write_scope) |
| API keys | `.env`, Credential Manager |
| Budget / cost ledger | `%LOCALAPPDATA%/squad` ledger.sqlite |
| Audit log | `%LOCALAPPDATA%/squad` audit.log (hash chained) |

## Attackers
- Prompt-injected repo content (untrusted files the agent reads)
- A malicious dependency installed by the agent
- A mistaken agent (tool misuse, bad args)
- A curious local user (secrets in the same account)

---

## Guard component (decision layer)

### TH-01 Prompt injection tries to override the agent or leak secrets
Controls: default-deny policy; `edit_file` gated by write_scope; blocked components (`.ssh`, `.aws`, ...). OWASP LLM01 (Prompt Injection).
Test: `tests/attack/test_attacks.py`
Test: `tests/guard/test_decide.py`

### TH-02 A tool request with a forbidden or destructive action
Controls: default deny; tiered tools; `has_destructive` pattern filter. OWASP LLM02 (Insecure Output Handling).
Test: `tests/guard/test_decide.py`
Test: `tests/guard/test_patterns.py`

### TH-03 A request targets a path outside the write scope
Controls: `is_within` / `is_blocked` path canonicalization. OWASP LLM02.
Test: `tests/guard/test_paths.py`

## Budget component

### TH-04 A runaway loop spends past the caps
Controls: per-agent/provider/task/day/month caps, spike breaker, worst-case counting.
Test: `tests/budget/test_budget.py`

### TH-05 An unknown/off-prices model is used and billed at wrong rates
Controls: `price_for` returns None and `preflight` blocks. OWASP LLM05 (Supply Chain).
Test: `tests/budget/test_budget.py`
Test: `tests/budget/test_prices.py`

## Providers component

### TH-06 A provider response is parsed into an unsafe tool action
Controls: `parse_action` + guard re-validation of the resulting tool request. OWASP LLM02.
Test: `tests/agent/test_actions.py`

## Executor component (isolation)

### TH-07 Agent code runs in the user's own account
Controls: `MIN_AGENT_ISOLATION = 1`; `IsolationError` raised otherwise.
Test: `tests/exec/test_runner.py`

### TH-08 Agent code spawns orphaned processes that survive a crash
Controls: Job Object `KILL_ON_JOB_CLOSE`.
Test: `tests/exec/test_adapter.py`

### TH-09 A sandboxed process reads user secrets or reaches the network
Controls: restricted-token / low-integrity launch, AppContainer without network, per-user firewall block (Level 3); Windows Sandbox (Level 2). OWASP LLM04 (Data/Model Poisoning) countermeasure.
Test: `tests/exec/test_restricted.py`
Accepted risk: Level 3 (restricted token) is weaker than a VM; work repos still require level 2+ unless waived in writing (see docs/RULES.md).

## Gateway component (remote)

### TH-10 Remote control plane is reachable off-loopback
Controls: bind refused unless host is 127.0.0.1.
Test: `tests/gateway/test_controller.py`

### TH-11 Remote login without a passkey / token
Controls: WebAuthn passkey + session token; login gated.
Test: `tests/gateway/test_gateway.py`

## Durable state

### TH-12 A crash leaves a half-applied run unrecoverable
Controls: SQLite checkpoints after every step; resume / rollback / mark-failed on start; never resume silently.
Test: `tests/config/test_runstate.py`

## Evaluation

### TH-13 A change silently lowers pass rate or raises cost
Controls: evaluation harness records pass/cost per commit; CI fails on regression beyond margin.
Test: `tests/eval/test_eval.py`

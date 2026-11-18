# Windows Dev Squad — Security

This document records the threat model and the defense for each class of attack
that `tests/attack/` exercises. The guard is a **decision layer, not a sandbox**:
permissions come from guard profiles, agent code runs inside a real isolation
level, and everything is fail-closed.

## Attacks and defenses

| Attack | Defense | Where |
|---|---|---|
| **Prompt injection** — model output tries to run a blocked or unknown tool | The agent loop parses model output as *data*, validates every action through the guard (default-deny). `raw_shell`/`git_push`/`invoke_squad`/`admin_elevation` are Tier 3 DENY; unknown tools are ASK. | `squad/agent/loop.py`, `squad/guard/decide.py` |
| **Secret leak** — credentials reach a subprocess | Subprocess environment is scrubbed of `API_KEY`/`TOKEN`/`SECRET`/…; secrets are never printed and are redacted from output/logs/reports. | `squad/exec/env.py`, `squad/cli/doctor.py` |
| **Guard bypass** — traversal, symlinks, junctions, 8.3 names, encoded/backslash paths, ADS, `\\?\` prefixes | Path canonicalization is fail-closed (percent-decode, strip Windows aliasing, resolve symlinks/junctions/8.3, case-fold) before scope/block checks. | `squad/guard/paths.py` |
| **Self-approval** — an agent approves its own action | Approvals are human-only (`grant` rejects any non-human approver), bound to the exact command + cwd + args, and expire in 5 minutes. | `squad/guard/approvals.py` |
| **Budget bypass** — claim a lower cost or an unknown model | The budget estimates worst-case cost from the requested tokens *before* the call and refuses if any layer would be exceeded; unknown models are blocked. | `squad/budget/budget.py`, `prices.yaml` |
| **Escalation by names** — an agent named "root"/"captain" gains power | Names are labels with no permissions; write scopes come from roles/profiles, and unknown/privileged tool names are default-deny. | `squad/crew/roster.py`, `squad/guard` |
| **Audit tampering** | The audit log is append-only and hash-chained; tampering is detected by `verify()`. | `squad/audit/audit.py` |

## Fail-closed rule (rule 9)

Any error, log-write failure, or exception means DENY. When in doubt, deny.

## Not covered yet

- The remote web page (Phase 10) adds WebAuthn/token/CSP/CSRF protections; it is
  not built yet.
- Real-key provider interactions are only exercised by the opt-in
  `squad providers test`, never by CI.
# Windows Dev Squad — Known Issues

A plain record of open and recently-fixed issues. Status: **Open** = still to
address; **Fixed** = resolved in a commit. Severity: High / Medium / Low.

---

## Open issues

### SQD-001 — Real model calls need a live provider key (High, Fixed)
`run` and `chat` now work against a live model via a free local Ollama
(`squad chat --provider ollama`, or `setkey ollama free` in the TUI). Verified
on this machine against `llama3.2:1b` (running on 127.0.0.1:11434). A paid
provider key in `.env` (e.g. `OPENROUTER_API_KEY=…`, `ANTHROPIC_API_KEY=…`,
`FREELM_API_KEY=…`) remains a drop-in upgrade; key loading is dynamic (any
`<NAME>_API_KEY` is picked up) and the offline knowledge base answers common
questions with no model at all.
**Resolution:** implemented and verified against the local Ollama model.

### SQD-002 — Real isolation launch (Levels 1–4) now implemented (High, Fixed)
The Windows adapter now implements `supports_isolation()` and actual launch for
Level 1 (low-privilege user via `CreateProcessWithLogonW`), Level 2 (Windows
Sandbox via `WindowsSandbox.exe` and a generated `.wsb` config), and Level 4
(WSL2/Docker detection). `run_command` passes the isolation level through to the
adapter) while keeping IsolationError refusal at Level 0. The WFP network-block marker and
the low-privilege user must still be set up (see `squad doctor --setup-help`);
`supports_isolation(1)` returns True only once that marker is verified.
**Resolution:** implemented; verify with a configured low-priv user + password.

### SQD-003 — WebAuthn passkey is functional (Medium, Fixed)
The gateway now wires the `webauthn` lib into a real challenge /
registration / verification flow. `squad/gateway/webauthn.py` implements
`WebAuthnState` (challenge TTL, HMAC-signed sessions) plus register /
authenticate-options / login endpoints bound to `Origin`/`Host`
(loopback only). `squad remote serve` instantiates the state and falls back
to token-only login when the lib is absent.
**Resolution:** implemented; register a passkey at `/api/webauthn/register-options`
then log in at `/api/login`.

### SQD-004 — Linux/macOS CI unverified (Medium, Open)
The 3-OS workflow is written, but only Windows was run locally. The POSIX
adapter, bash/zsh detection, and the 8.3/hook tests are unverified on real
Linux/macOS.
**Impact:** cross-platform claims are untested.
**Resolution:** push to GitHub and confirm the `windows|ubuntu|macos` matrix.

### SQD-005 — Windows Credential Manager keys (Low, Fixed)
`squad/config/keys.py` now loads provider keys from the Windows Credential
Manager via `ctypes`/`CredReadW` (`load_credential_manager_keys()`), in addition
to repo + data-dir `.env`. First-set wins, loading never crashes if the manager
is unavailable. Covered by `tests/config/test_keys.py`.
**Resolution:** implemented and tested.

### SQD-006 — `squad remote on/off/revoke` are placeholders (Low, Fixed)
`squad/cli/remote.py` now implements real daemon management: `on` spawns
`remote serve` as a detached background process (DETACHED_PROCESS / new session)
and records the pid in `remote.pid` under the data dir; `off` reads the pidfile,
terminates the process tree (`taskkill /T /F` on Windows), and removes the file;
`revoke` clears the persisted web session store. Each function accepts injected
collaborators for offline unit tests.
**Resolution:** implemented (real daemon start/stop/revoke).

### SQD-007 — Gateway connected to live squad state (Medium, Fixed)
`RemoteController` now accepts a `live_state` snapshot (dict or callable) and
exposes `live_status()`; `/api/status` merges live agent cards, budget, and
pending approvals, and `/api/approvals` reads them from the live state. Sessions
issue from `squad remote serve --state <file.json>`.
**Resolution:** implemented; pass a live run-state snapshot via `--state`.

### SQD-008 — TUI has a live refresh loop (Low, Fixed)
`squad/tui/live.py` now provides `live_refresh(poll, interval=…)`, a daemon that
repaints the rich view on each poll, feeding a snapshot into the gateway via the
optional `on_render` hook. `poll` returns a list of AgentCard (or plain dicts).
**Resolution:** implemented; call `live_refresh` with a run-state poller.

### SQD-009 — `run` still reads cwd-relative config (Low, Fixed)
The data-dir active-config helpers exist and are now used for all config loads.
**Resolution:** switched those commands to `squad.config.data.active_config`. (Fixed)

### SQD-010 — Retention is not scheduled (Low, Fixed)
`archive_audit` is invoked automatically at the end of `squad run` and via
`squad audit --retention-days`; the cost ledger prunes old rows on
`squad cost --retention-days`. Old audit/ledger entries are archived out of the
live log on run, satisfying the retention rule.
**Resolution:** wired into `run` and the audit/cost CLI paths. (Fixed)

### SQD-011 — Independent security review (Medium, In progress)
Rule 13 requires the guard, budget, and gateway code (and their tests) to be
reviewed by a different model or by the user; that review is being performed via
the DeepSeek Harness agent (dsh) against the guard/budget/gateway/crew
directories and `tests/attack/`.
**Resolution:** review dispatched; findings to be triaged into fixes.

### SQD-012 — Non-fatal Starlette deprecation warning (Low, Fixed)
FastAPI's `TestClient` emits `StarletteDeprecationWarning` ("use httpx2") in the
test suite. Suppressed via pytest filterwarnings config.
**Resolution:** suppressed warning via pytest config. (Fixed)

---

## Fixed issues (for the record)

| ID | Issue | Fixed in |
|----|-------|----------|
| SQD-F1 | `.env` API-key loading not implemented | `9b8857d` |
| SQD-F2 | Config not loaded from `%LOCALAPPDATA%\squad\` | `9b8857d` |
| SQD-F3 | Audit log not wired into the agent loop | `9b8857d` |
| SQD-F4 | Budget ledger not wired into `squad run` | `9b8857d` |
| SQD-F5 | Gateway had no idle timeout ("remote off when idle") | `9b8857d` |
| SQD-F6 | `approver`/`audit` were class vars, not dataclass fields (latent bug) | `9b8857d` |
| SQD-F7 | `run` and `providers` still read cwd-relative config | local |
| SQD-F8 | Starlette deprecation warnings in test client | local |
| SQD-F9 | WebAuthn passkey stubbed (SQD-003) | local |
| SQD-F10 | Gateway not connected to live run state (SQD-007) | local |
| SQD-F11 | TUI had no live refresh loop (SQD-008) | local |
| SQD-F12 | Real isolation launch L1/L2/L4 not implemented (SQD-002) | local |

---

## How to track
Keep this file updated per change. Each Open issue above has a concrete
Resolution. SQD-004 (Linux/macOS CI) and the SQD-011 security review are the
remaining open items; the security core (guard/budget/gateway) is otherwise
covered by `tests/attack/`.
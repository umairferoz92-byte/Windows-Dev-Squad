# Windows Dev Squad — User Guide

How to install, run, read the output, and use the pieces that exist today. This
guide only documents what is actually built (Phases 0–1). Later sections are
added as each phase lands.

---

## 1. What works right now

| Thing | Status |
|---|---|
| `squad doctor` — read-only machine/limits report | ✅ Phase 0 |
| `squad doctor --setup-help` — one-time admin setup steps | ✅ Phase 0 |
| `squad --version`, `squad --help` | ✅ Phase 0 |
| The **guard** library (`squad.guard`) | ✅ Phase 1 |
| The **executor** (`squad.exec`): Job Objects, scrubbed env, git hardening, isolation enforcement | ✅ Phase 2 |
| **Typed tools** (`squad.tools`) | ✅ Phase 2 |
| `squad check` / `run` / `status` / `cost` / `logs` / `audit` / `stop` / `providers test` | ⏳ Later phases |
| Agents, budget layer, providers, web page | ⏳ Later phases |

There is **no model, no network, and no agent execution yet.** The guard is a
decision layer, not a sandbox.

---

## 2. One-time setup

Prerequisites: **Python 3.11+** (3.12 recommended) and **git**.

```powershell
# from inside the project folder
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"   # Windows
#   (POSIX: ./.venv/bin/python -m pip install -e ".[dev]")
```

`pip install -e .` registers the `squad` command. No `.env` is needed until
Phase 4 (model keys).

---

## 3. The commands

```powershell
.\.venv\Scripts\squad.exe --help              # list commands
.\.venv\Scripts\squad.exe --version           # squad 0.0.0
.\.venv\Scripts\squad.exe doctor              # machine/limits report
.\.venv\Scripts\squad.exe doctor --setup-help # Level 1 admin setup steps
```

`python -m squad <command>` is equivalent to `squad <command>`.

---

## 4. Reading `squad doctor`

Four sections:

1. **Environment** — OS + edition, architecture, Python, git, PowerShell
   language mode.
2. **Installed tools** — `Importable` (installed in this Python) and `On PATH`
   (reachable as a command). `Importable: yes` is the reliable signal; `On
   PATH: no` just means the venv isn't activated.
3. **Proxy variables** — which of `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY`/
   `NO_PROXY` are set, with any credentials redacted.
4. **Isolation levels** — what can actually run code on this machine.

Doctor is **read-only and never prints secrets.**

---

## 5. Isolation levels (what "available" means)

| Level | What | When "available" |
|---|---|---|
| 0 | Your own account | Always, but only for `squad check` on trusted repos (your own commits). AI work never runs here. |
| 1 | Low-privilege Windows user | Only if the user exists **and** a `verified` firewall-block marker is present. Default-deny: a partially-set-up Level 1 counts as *not available*. |
| 2 | Windows Sandbox | Pro/Enterprise/Education **and** `WindowsSandbox.exe` present. |
| 3 | Dev VM | Never auto-detected — you configure it. |
| 4 | WSL2 / Docker (network `none`) | WSL2 or Docker detected. |

The rule of thumb: **repos that matter need Level 2+.** If the required level
isn't available, the AI parts simply won't run on that repo.

---

## 6. Setting up Level 1 (optional, manual, elevated)

`doctor --setup-help` prints the full steps. Summary:

1. Create a standard (non-admin) user `squad-agent`.
2. Block that user's network with a **WFP** filter (note:
   `New-NetFirewallRule -LocalUser` is *not* enough — it only matches
   IPsec-authenticated traffic). A tested helper ships in Phase 2.
3. **Verify** as the agent user: a network probe must fail and your profile
   must be unreadable.
4. Write a marker file with `"verified": true` so `doctor` reports Level 1.

Prefer **Windows Sandbox (Level 2)** on Pro/Enterprise — simpler and stronger.

---

## 7. Using the guard library

`squad.guard` is **standard-library only**, so it imports with no third-party
dependencies. It is default-deny: an unknown tool asks for approval.

```python
from squad.guard import Policy, ToolRequest, Verdict, evaluate

policy = Policy(
    {
        "write_scope": ["C:/repo/src"],
        # Optionally override blocked_components, sensitive_files, sensitive_dirs.
    }
)

request = ToolRequest(
    tool="edit_file",
    args={"path": "C:/repo/src/main.py"},
    cwd="C:/repo",
    isolation_level=1,
)

decision = evaluate(request, policy)
print(decision.verdict)  # Verdict.ALLOW | Verdict.ASK | Verdict.DENY
print(decision.reason)  # human-readable reason
```

The decision logic:

- **Tier 0** (`read_file`, `git_diff`, …) → ALLOW; `run_tests`/`run_lint`/
  `run_typecheck` → ALLOW only when `isolation_level` meets the required level,
  otherwise ASK.
- **Tier 1** (`edit_file`, `git_commit`) → ALLOW if in `write_scope` and not
  blocked/sensitive; ASK if out of scope or under `.git`/`.github`; DENY for
  credential locations and squad config files.
- **Tier 2** (`install_dependencies`) → ASK.
- **Tier 3** (`git_push`, `raw_shell`, `credential_access`, `invoke_squad`,
  `admin_elevation`) → DENY.
- **Unknown tool** → ASK (default-deny).

Other useful functions:

```python
from squad.guard import is_within, is_blocked, has_destructive, ApprovalStore

is_within("../secret.txt", ["/repo/src"])  # False (traversal caught)
is_blocked("/home/u/.ssh/id_rsa", policy)  # True (credential location)
has_destructive("rm -rf /")  # True

store = ApprovalStore()
a = store.grant("human", "edit_file", "/repo", {"path": "/repo/src/a.py"})
store.find_valid("edit_file", "/repo", {"path": "/repo/src/a.py"}, now=a.created_at + 1)
# -> Approval (valid); None after 5 minutes, or for a different command/cwd/args
```

Approvals are **human-only** (`grant("agent", …)` raises), bound to the exact
command + working directory + arguments, and expire after 5 minutes.

---

## 7b. Using the executor

`squad.exec.run_command` runs commands as argument lists (never a shell string)
with a scrubbed, UTF-8-forced environment, and refuses agent code that would run
in your own account:

```python
from squad.exec import run_command, IsolationError, hardened_git_args, hardened_git_env

result = run_command(["git", *hardened_git_args(), "status"], cwd="/repo")
print(result.returncode, result.stdout)

try:
    run_command(["python", "run_tests.py"], is_agent_code=True, isolation_level=0)
except IsolationError as e:
    print(e)  # "agent code must never run in the user's own account ..."
```

Key guarantees: Windows runs children inside a **Job Object** with
`KILL_ON_JOB_CLOSE`, so a timed-out or crashed run leaves no orphaned processes;
`hardened_git_args()` disables hooks and blanks `core.sshCommand`/`core.askpass`
so repo config can't run programs.

---

## 8. Security model at a glance

- The **guard is not a sandbox** — it decides, it does not contain processes.
- Default-deny everywhere; anything unrecognized asks.
- Permissions come from guard profiles, never from names or model output.
- Subprocesses use argument lists (never `shell=True`) and a scrubbed
  environment; secrets are never printed.

---

## 9. Running the checks (development)

```powershell
.\.venv\Scripts\python.exe -m pytest -q                       # tests (offline)
.\.venv\Scripts\python.exe -m ruff check squad tests          # lint
.\.venv\Scripts\python.exe -m ruff format --check squad tests # formatting
.\.venv\Scripts\python.exe -m bandit -r squad -c pyproject.toml  # security scan
.\.venv\Scripts\python.exe -m pip_audit                      # dependency audit
```

The `practice/` repo contains a deliberately failing test and is excluded from
the main run (`--ignore=practice`). It is the throwaway target the agents will
fix in Phase 5.

---

## 10. Roadmap

Phase 2 (executor + typed tools + Job Objects) → Phase 3 (`squad check`) →
Phase 4 (budget + providers) → Phase 5 (single agent) → Phase 6 (`squad run`,
v0.1) → Phase 7 (TUI) → Phase 8 (parallel) → Phase 9 (attack tests) →
Phase 10 (web) → Phase 11 (Linux/macOS) → Phase 12 (hardening).

---

## 11. FAQ

- **"On PATH: no" but the tool is installed?** Activate the venv, or trust the
  `Importable: yes` column — it reflects the current Python environment.
- **Symlink/junction tests skip?** They need Developer Mode or admin on
  Windows; they run on CI (Linux/macOS always, Windows runners with symlinks).
- **Can I run the AI agents yet?** No — they arrive in Phase 5/6. Today you can
  only run `doctor` and the guard library.

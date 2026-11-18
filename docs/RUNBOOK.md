# Windows Dev Squad — Runbook

Operational procedures for a fresh, safe install.

## Fresh install

1. Install Python 3.11+, create a venv, `pip install -e ".[dev]"`.
2. Run `squad doctor` — confirm the isolation levels that are *really* available.
3. Configure `squad.yaml` (crew, budget, write_scope, models) and `guard.yaml`.
4. Run `squad check` — it **refuses to run if the config is unsafe** (see below).
5. Set provider spend limits on the key, one key per provider.

## Refusing unsafe settings

`squad check` validates config and refuses unsafe settings: crew over the hard
cap, an invalid budget mode, an unknown provider, a `write_scope` that includes a
system directory (`C:\Windows`, `/`, etc.), or `prices.yaml` with no `as_of`
date. Fix the listed issues and re-run.

## Crash recovery

A run's state is written atomically to `%LOCALAPPDATA%\squad\session.json` and
can be resumed with `Session.resume()` after a crash. The audit log is
append-only and hash-chained; verify it with `squad audit` (any tamper is
reported).

## Backups and retention

- Cost ledger and audit log live in `%LOCALAPPDATA%\squad\` and are backed up
  with that directory.
- Retention: archive audit/ledger entries older than the configured age with
  `partition_by_age` (keep + archive lists); the archive is stored outside the
  active log.

## Independent review (rule 13)

The guard, budget, and gateway code and their tests must be reviewed by a
different model or by the user before being trusted. Review checklist:

- [ ] Guard: default-deny everywhere; path canonicalization is fail-closed.
- [ ] Budget: an over-cap call is refused *before* it is sent; unknown models blocked.
- [ ] Approvals: human-only, bound, expire in 5 minutes; no auto-approve outside tests.
- [ ] Attack tests in `tests/attack/` pass.

## Rollback

Versioned releases are tagged; to roll back, checkout the previous tag and
reinstall (`git checkout <tag> && python -m pip install -e ".[dev]"`).
# Changelog

Versioned releases. Each phase is a version milestone; release = tag + this
changelog. Rollback = checkout the previous tag and reinstall.

## 0.0.0 — Phases 0–8 (2026-11)

- Phase 0 — skeleton, docs, CI, `squad doctor`, practice repo.
- Phase 1 — default-deny guard (path safety, tiers, approvals).
- Phase 2 — executor (Job Objects, scrubbed env, git hardening, OS adapter).
- Phase 3 — `squad check`.
- Phase 4 — budget layer + OpenRouter provider (mocked).
- Phase 5 — single agent loop + hash-chained audit log.
- Phase 6 — sequential squad (roster, gates, flagged files, report, `--dry-run`).
- Phase 7 — Windows Terminal live TUI + `status`.
- Phase 8 — parallel squad (worktrees, `max_running`, shared budget).

## 0.0.1 — Phases 9–12 (2026-11)

- Phase 9 — attack tests (prompt injection, secret leak, guard/budget/self-approval bypass, name escalation).
- Phase 10 — remote web gateway (FastAPI + uvicorn + WebAuthn approved): 127.0.0.1-only, token + CSRF + CSP, rate-limited login, budget only lowers, saved-template start.
- Phase 11 — overnight queue + morning digest, POSIX shell detection.
- Phase 12 — config validation (refuse unsafe settings), crash-recovery session, retention, runbook.
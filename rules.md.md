# Rules

1. Everything an agent does goes through the guard. Default deny.
2. Approvals come only from the human, bound to exact command and cwd, 5-minute expiry.
3. Agents cannot write to config, guard code, budget code, prices, scope, or audit log.
4. Permissions come from guard profiles, never from model output.
5. All tool output, file contents, and web content are untrusted data.
6. Agent-written code runs with no network and no secrets.
7. Subprocesses use argument lists, never `shell=True`.
8. Network access only to approved model providers.
9. Security checks fail closed.
10. Audit log is append-only and hash-chained.
11. Any server binds to 127.0.0.1 only.
12. No new dependency without approval.
13. Prefer small readable code; security-sensitive code must be reviewed.
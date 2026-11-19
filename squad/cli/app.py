"""The ``squad`` command-line application."""

from __future__ import annotations

import os
import sys
from datetime import UTC
from pathlib import Path

import typer
from rich.console import Console

from squad import __version__
from squad.cli.doctor import doctor_command

app = typer.Typer(
    name="squad",
    help="Windows Dev Squad: a guard-railed, budget-controlled multi-agent coding crew.",
    no_args_is_help=True,
    add_completion=False,
)


def _venv_squad_exe() -> str:
    """Path to the project's ``squad`` launcher for background subprocesses.

    Prefer the console-script next to the running interpreter (``.venv/Scripts``
    on Windows, ``.venv/bin`` elsewhere); fall back to ``python -m squad``.
    """
    base = Path(sys.prefix)
    candidates = [
        base / "Scripts" / "squad.exe",
        base / "Scripts" / "squad",
        base / "bin" / "squad",
    ]
    for cand in candidates:
        if cand.exists():
            return str(cand)
    return f"{sys.executable} -m squad"


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"squad {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show the version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Windows Dev Squad (squad) command-line interface."""


app.command(name="doctor")(doctor_command)


@app.command(name="check")
def check_command(
    config: str = typer.Option("squad.yaml", "--config", help="Path to squad.yaml."),
    guard: str = typer.Option("guard.yaml", "--guard", help="Path to guard.yaml."),
) -> None:
    """Run configured tests/lint/security scans under the guard and write one report."""
    from squad.checks.check import run_checks
    from squad.checks.config import load_guard_policy, load_repo_config, load_yaml
    from squad.config import validate_config
    from squad.guard import Policy
    from squad.report.report import build_report, render_report

    cwd = os.getcwd()
    repo_config = load_repo_config(config)
    guard_config = load_guard_policy(guard)
    console = Console()

    issues = validate_config(repo_config, guard_config, load_yaml("prices.yaml"))
    if issues:
        console.print("[red]unsafe config:[/red]", markup=False)
        for issue in issues:
            console.print("  - " + issue, markup=False)
        raise typer.Exit(1)

    policy = Policy(guard_config)
    results = run_checks(repo_config, policy, cwd)
    report = build_report(results, cwd)
    console.print(render_report(report), markup=False)
    if report["summary"]["failed"] or report["summary"]["denied"]:
        raise typer.Exit(1)


@app.command(name="cost")
def cost_command(
    by: str = typer.Option("day", "--by", help="Group by: day, task, agent, provider."),
    reconcile: str = typer.Option(None, "--reconcile", help="Reconcile: provider=amount (e.g. openrouter=12.34)."),
    ledger_path: str = typer.Option(None, "--ledger", help="Ledger path (default per-OS data dir)."),
    retention_days: int = typer.Option(None, "--retention-days", help="Prune ledger entries older than this many days."),
) -> None:
    """Show cost totals from the ledger, or reconcile against provider billing."""
    from squad.budget.ledger import Ledger, default_ledger_path

    console = Console()
    path = ledger_path or default_ledger_path()
    ledger = Ledger(path)
    if retention_days:
        pruned = ledger.prune(retention_days)
        if pruned:
            console.print(f"pruned {pruned} old ledger entrie(s) (retention).", markup=False)
    try:
        if reconcile:
            provider, _, amount = reconcile.partition("=")
            provider = provider.strip()
            ledger_cost = ledger.total_cost(provider)
            billing = float(amount.strip())
            gap = abs(ledger_cost - billing) / billing if billing else float("inf")
            status = "ok" if gap <= 0.10 else f"GAP {gap * 100:.1f}%"
            console.print(
                f"ledger[{provider}] = {ledger_cost:.6f}, billing = {billing:.6f}, gap = {gap * 100:.1f}% ({status})",
                markup=False,
            )
        else:
            totals = ledger.totals(by)
            console.print(f"Cost by {by}:", markup=False)
            if not totals:
                console.print("ledger is empty.", markup=False)
                raise typer.Exit(0)
            for row in totals:
                console.print(
                    f"{row['key']}: {row['cost']:.4f} ({row['tokens_in']} in / {row['tokens_out']} out)",
                    markup=False,
                )
    finally:
        ledger.close()


@app.command(name="providers")
def providers_command(
    test: bool = typer.Option(False, "--test", help="Make one tiny real-key smoke call (opt-in; never in CI)."),
    model: str = typer.Option("", "--model", help="Model to test (defaults to first allowed worker model)."),
    provider: str = typer.Option(
        "",
        "--provider",
        help="Provider to use (openai, anthropic, openrouter, groq, gemini, ollama, lmstudio, ...). Defaults to the first key found.",
    ),
) -> None:
    """Provider management. `squad providers test` makes one tiny real call."""
    import os

    console = Console()
    if not test:
        from squad.providers import factory

        names = ", ".join(factory.provider_names())
        console.print(
            f"Available providers: {names}. "
            f"Set any provider's API key (e.g. OPENAI_API_KEY, ANTHROPIC_API_KEY) "
            f"and `squad providers test` will use it. Free local endpoints "
            f"(ollama, lmstudio) need no key.\n\n"
            f"Providers are chosen by the first available key, or by "
            f"`SQUAD_LLM_PROVIDER` / `models.provider` in squad.yaml.",
            markup=False,
        )
        return

    if os.environ.get("CI"):
        console.print("[red]refusing: `providers test` must never run in CI[/red]", markup=False)
        raise typer.Exit(1)

    from squad.checks.config import load_repo_config
    from squad.providers import factory
    from squad.providers.models import all_allowed_models, role_allowed_models

    config = load_repo_config("squad.yaml")
    models_config = config.get("models") or {}
    allowed = all_allowed_models(models_config)
    target = model or next(iter(sorted(role_allowed_models(models_config, "worker"))), "")
    if not target or target not in allowed:
        console.print("[red]no allowed model configured (check squad.yaml models)[/red]", markup=False)
        raise typer.Exit(1)

    name, api_key, spec = factory.resolve_provider(preferred=provider or None, config=models_config)
    if not api_key and not spec.free:
        console.print(
            f"[red]{spec.key_env} is not set (.env or Credential Manager) — no key for provider '{name}'[/red]",
            markup=False,
        )
        raise typer.Exit(1)

    prov = factory.build_provider(name, api_key or "", allowed)
    console.print(f"testing provider={name} model={target} ...", markup=False)
    try:
        resp = prov.chat(target, [{"role": "user", "content": "ping"}], max_tokens=1)
    except Exception as exc:
        console.print(f"[red]provider test failed ({name}): {exc}[/red]", markup=False)
        raise typer.Exit(1) from None

    usage = resp.usage
    console.print(
        f"ok: provider={name} model={resp.model} "
        f"tokens_in={usage.prompt_tokens if usage else '?'} "
        f"tokens_out={usage.completion_tokens if usage else '?'}",
        markup=False,
    )


@app.command(name="audit")
def audit_command(
    path: str = typer.Option(None, "--path", help="Audit log path (default per-OS data dir)."),
    retention_days: int = typer.Option(None, "--retention-days", help="Archive audit entries older than this many days."),
) -> None:
    """Show the audit log's latest hash and integrity."""
    from squad.audit.audit import AuditLog, default_audit_path
    from squad.config.retention import archive_audit

    console = Console()
    log = AuditLog(path or default_audit_path())
    if retention_days:
        archived = archive_audit(path or default_audit_path(), retention_days)
        if archived:
            console.print(f"archived {archived} old audit entrie(s) (retention).", markup=False)
    console.print(f"latest hash: {log.latest_hash or '(empty)'}", markup=False)
    console.print(f"integrity: {'ok' if log.verify() else 'TAMPERED'}", markup=False)


@app.command(name="run")
def run_cmd(
    task: str = typer.Argument(..., help="Development task to assign to the crew."),
    config: str = typer.Option("squad.yaml", "--config", help="Path to squad.yaml."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Estimate cost/crew without calling any model."),
    agents: int = typer.Option(5, "--agents", help="Crew size (1..max_agents)."),
    names: str = typer.Option("", "--names", help="Optional comma-separated crew names."),
) -> None:
    """Run the (single or crew) agent on a task. `--dry-run` estimates without a key."""
    import os

    console = Console()
    crew_names = [n.strip() for n in names.split(",") if n.strip()] if names else None

    from squad.budget import PriceTable
    from squad.checks.config import load_repo_config, load_yaml
    from squad.crew import assemble_crew, estimate_run_cost

    crew = assemble_crew(agents, names=crew_names)

    if dry_run:
        prices = PriceTable(load_yaml("prices.yaml"))
        worker = sorted((load_repo_config(config).get("models") or {}).get("worker", []))
        model = worker[0] if worker else ""
        est = estimate_run_cost(crew, prices, model) if model else None
        console.print(f"crew ({len(crew)}): " + ", ".join(f"{a.name}({a.role})" for a in crew), markup=False)
        if est is not None:
            console.print(f"estimated cost (estimate, not a quote): ${est:.6f}", markup=False)
        else:
            console.print("estimated cost: unknown model (blocked)", markup=False)
        return

    from squad.agent import Agent
    from squad.budget import BudgetLimits, BudgetManager
    from squad.guard import Policy
    from squad.providers import factory
    from squad.providers.models import role_allowed_models

    config_data = load_repo_config(config)
    repo = config_data.get("repo") or {}
    scope = (repo.get("write_scope") or {}).get("source", [])
    test_cmd = (repo.get("check_commands") or {}).get("test")

    from squad.audit import AuditLog, default_audit_path
    from squad.budget import Ledger
    from squad.budget.ledger import default_ledger_path

    prices = PriceTable(load_yaml("prices.yaml"))
    limits = BudgetLimits.from_config(config_data)
    ledger = Ledger(default_ledger_path())
    budget = BudgetManager(limits, prices, ledger=ledger)
    audit = AuditLog(default_audit_path())

    worker = sorted(role_allowed_models(config_data.get("models") or {}, "worker"))
    model = worker[0] if worker else ""
    if not model:
        console.print("[red]no worker model configured (check squad.yaml models)[/red]", markup=False)
        raise typer.Exit(1)

    # Resolve provider + key via the factory; use the repo models provider.
    _pname, api_key, _pspec = factory.resolve_provider(config=config_data.get("models") or {})
    if not api_key:
        console.print(
            "[red]no LLM provider key set — `run` needs a provider "
            "(e.g. OPENAI_API_KEY, ANTHROPIC_API_KEY, OPENROUTER_API_KEY). "
            "See `squad providers`.[/red]",
            markup=False,
        )
        raise typer.Exit(1)
    provider = factory.build_provider(_pname, api_key, worker)
    policy = Policy(load_yaml("guard.yaml"))
    agent = Agent(
        name="coder",
        role="worker",
        model=model,
        provider=provider,
        budget=budget,
        policy=policy,
        cwd=os.getcwd(),
        write_scope=scope,
        test_command=test_cmd,
        audit=audit,
    )
    result = agent.run(task)
    console.print(f"ok={result.ok} steps={result.steps} message={result.message}", markup=False)
    from squad.config.retention import archive_audit

    archived = archive_audit(default_audit_path())
    if archived:
        console.print(f"archived {archived} old audit entrie(s) (retention).", markup=False)
    if not result.ok:
        raise typer.Exit(1)


@app.command(name="status")
def status_command(
    state: str = typer.Option("", "--state", help="JSON file of agent-card state snapshots."),
) -> None:
    """Show the live agent view (one card per agent)."""
    import json

    from squad.tui import AgentCard, render_live

    console = Console()
    if state:
        try:
            with open(state, encoding="utf-8") as fh:
                data = json.load(fh)
            cards = [
                AgentCard(
                    name=d["name"],
                    role=d.get("role", ""),
                    step=int(d.get("step", 0)),
                    status=d.get("status", "idle"),
                    cost=float(d.get("cost", 0.0)),
                    budget=float(d.get("budget", 0.0)),
                    files=tuple(d.get("files", [])),
                )
                for d in data
            ]
        except (OSError, ValueError, KeyError, TypeError):
            console.print("[red]could not read state file[/red]", markup=False)
            raise typer.Exit(2) from None
    else:
        cards = [AgentCard(name="(no active run)", role="status", status="idle")]
    console.print(render_live(cards), markup=False)


@app.command(name="queue")
def queue_command(
    task: str = typer.Argument(None, help="Task to enqueue (omit to list)."),
    queue_path: str = typer.Option(None, "--queue", help="Queue file path (default per-OS data dir)."),
    digest: bool = typer.Option(False, "--digest", help="Print the morning digest."),
) -> None:
    """List, enqueue, or digest the overnight job queue."""
    from squad.queue import JobQueue, build_digest, default_queue_path

    console = Console()
    queue = JobQueue(queue_path or default_queue_path())
    if digest:
        console.print(build_digest(queue.load()), markup=False)
    elif task:
        queue.enqueue(task)
        console.print(f"queued: {task}", markup=False)
    else:
        for job in queue.load():
            console.print(f"[{job['status']}] {job['task']}", markup=False)


@app.command(name="remote")
def remote_command(
    sub: str = typer.Argument("serve", help="on | off | revoke | serve"),
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host (must be 127.0.0.1)."),
    port: int = typer.Option(8765, "--port", help="Bind port."),
) -> None:
    """Manage the remote web gateway (127.0.0.1 only)."""
    from squad.gateway import RemoteController, create_app

    console = Console()
    if host not in ("127.0.0.1", "localhost"):
        console.print("[red]refusing: the remote gateway must bind to 127.0.0.1 only[/red]", markup=False)
        raise typer.Exit(2)

    if sub == "on":
        from squad.gateway.daemon import daemon_running, start_daemon

        if daemon_running():
            console.print("remote gateway already running.", markup=False)
            raise typer.Exit(0)
        url = start_daemon(port=port)
        console.print(f"remote gateway started: {url}", markup=False)
        console.print(
            "sessions are issued at POST /api/login; revoke with `squad remote revoke`.",
            markup=False,
        )
    elif sub == "off":
        from squad.gateway.daemon import stop_daemon

        if stop_daemon():
            console.print("remote gateway stopped.", markup=False)
        else:
            console.print("remote gateway was not running.", markup=False)
    elif sub == "revoke":
        from squad.gateway.daemon import revoke_sessions

        revoke_sessions()
        console.print(
            "remote sessions revoked (daemon restarted; new logins issue fresh sessions).",
            markup=False,
        )
    elif sub == "serve":
        import uvicorn

        controller = RemoteController()
        app = create_app(controller, login_check=lambda: True)
        console.print(f"serving on http://{host}:{port}", markup=False)
        uvicorn.run(app, host=host, port=port, log_level="warning")
    else:
        console.print(f"[red]unknown remote subcommand '{sub}'[/red]", markup=False)
        raise typer.Exit(2)


def _force_utf8_stdio() -> None:
    """Force UTF-8 on the CLI's own stdout/stderr (spec: force UTF-8 for I/O)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


# Security Guard commands (module-level, so typer can route subcommands)
security_app = typer.Typer(help="Security operations", no_args_is_help=True)


@security_app.command("check-tools")
def security_check_tools_command(
    install_missing: bool = typer.Option(False, "--install", help="Interactively prompt to install missing tools."),
) -> None:
    """Alfred's tool manager: scan for the 12 security tools from the blueprint.

    Displays a status table of found/missing tools, and optionally prompts
    per missing tool to install it (with audit logging).
    """
    import subprocess

    from rich.console import Console
    from rich.table import Table

    from squad.audit.audit import AuditLog, default_audit_path
    from squad.tools.manifest import BLUEPRINT_MANIFEST, check_all_tools

    console = Console()
    statuses = check_all_tools(BLUEPRINT_MANIFEST)

    table = Table(title="Alfred's Security Tool Manifest (12 tools)")
    table.add_column("Tool")
    table.add_column("Purpose")
    table.add_column("Status")
    table.add_column("Version / Path")

    missing = []
    for st in statuses:
        if st.installed:
            stat_str = "[green]found[/green]"
            ver_path = f"{st.version} ({st.path})"
        else:
            stat_str = "[red]NOT FOUND[/red]"
            ver_path = st.install_cmd
            missing.append(st)
        table.add_row(st.display, st.purpose, stat_str, ver_path)

    console.print(table, markup=False)
    console.print(f"\nFound {len(statuses) - len(missing)}/{len(statuses)} tools. Missing: {len(missing)}.\n")

    if missing and install_missing:
        audit = AuditLog(default_audit_path())
        for st in missing:
            ans = input(f"Install {st.display} using '{st.install_cmd}'? [y/N]: ").strip().lower()
            if ans in ("y", "yes"):
                console.print(f"Running: {st.install_cmd}...", markup=False)
                try:
                    res = subprocess.run(st.install_cmd, shell=True, capture_output=True, text=True, timeout=300)  # nosec B602  # tool installer commands (winget/choco/apt) need a shell; interactive, user-initiated
                    if res.returncode == 0:
                        console.print(f"[green]Successfully installed {st.display}[/green]", markup=False)
                        audit.append(
                            "tools.alfred_install",
                            tool=st.name,
                            command=st.install_cmd,
                            status="success",
                        )
                    else:
                        console.print(f"[red]Install returned exit code {res.returncode}[/red]", markup=False)
                        audit.append(
                            "tools.alfred_install",
                            tool=st.name,
                            command=st.install_cmd,
                            status="failed",
                            code=res.returncode,
                        )
                except Exception as exc:
                    console.print(f"[red]Install error: {exc}[/red]", markup=False)
                    audit.append(
                        "tools.alfred_install",
                        tool=st.name,
                        command=st.install_cmd,
                        status="error",
                        error=str(exc),
                    )
            else:
                console.print(f"Skipped {st.display}.", markup=False)
                audit.append("tools.alfred_install", tool=st.name, command=st.install_cmd, status="skipped")
    elif missing:
        console.print(
            "Run `squad security check-tools --install` to interactively install missing tools.",
            markup=False,
        )


@security_app.command("add-target")
def security_add_target_command() -> None:
    """Add a new authorized target.

    Prompts the user for an ownership statement and the exact target string,
    re-prompts to confirm, computes a sha256 of the record, then writes it to
    ``authorized_targets.yaml`` and the hash-chained audit log.
    """
    import hashlib
    from datetime import datetime

    from squad.security_authorized import _append_authorized

    ownership = input("Ownership statement: ").strip()
    if not ownership:
        print("[refused] ownership statement cannot be empty.")
        return

    target = input("Exact target string (URL, IP, or local path): ").strip()
    if not target:
        print("[refused] target cannot be empty.")
        return

    target2 = input("Confirm target (type it again exactly): ").strip()
    if target2 != target:
        print("[refused] target strings did not match.")
        return

    added_at = datetime.now(UTC).isoformat()
    sha256_input = target + ownership + added_at
    sha256 = hashlib.sha256(sha256_input.encode("utf-8")).hexdigest()

    record = {
        "target": target,
        "ownership_statement": ownership,
        "added_at": added_at,
        "sha256": sha256,
    }
    _append_authorized(record)

    print(f"[ok] authorized target added: {target}")
    print(f"  ownership: {ownership}")
    print(f"  added at: {added_at}")


@security_app.command("nightwing")
def security_nightwing_command(
    target: str = typer.Argument(..., help="Target: URL, IP, or authorized local path."),
    phases: str = typer.Option("ab", "--phases", help="Phases to run, e.g. 'ab', 'abc', 'c'."),
    repo: str = typer.Option("", "--repo", help="Local repo path for Phase B (default: cwd)."),
) -> None:
    """Nightwing security agent: run passive recon, static analysis, and gated active scan.

    Phases:
      a = Passive recon (HTTP headers, exposed files)
      b = Static analysis of a local repo (offline, uses devhelper)
      c = Active non-destructive scan (nmap default scripts, ZAP baseline) —
          ALWAYS requires an interactive 'go ahead' before running.
    Target must be in the authorized-targets list (see `squad security add-target`).
    """
    from squad.agent.nightwing import Nightwing

    # Phase C requires an interactive go-ahead
    def _confirm(t, cmds):
        if not cmds:
            print("[note] No supported Phase C tools found (nmap/zap/testssl.sh).")
            return False
        print(f"\n[phase-c] target: {t}")
        for c in cmds:
            print(f"    $ {c}")
        print("[phase-c] These are non-destructive recon commands. Run them? [y/N]")
        ans = input().strip().lower()
        return ans in ("y", "yes")

    nw = Nightwing(target, local_repo_path=repo or None)

    # Phase C gate: only build a result if explicitly requested
    result = None
    if "c" in phases.lower():
        # Validate authorization up-front before prompting
        from squad.security_authorized import is_authorized

        if not is_authorized(target):
            print(f"[refused] target '{target}' is not authorized.")
            return
        print(f"[phase-c] target '{target}' IS authorized.")
        result = nw.run_phase_c(confirm_commands=_confirm)
        return

    result = nw.run_all()
    print(f"\n=== Nightwing scan of {result.target} ===")
    print(f"Phase A findings: {len(result.phase_a_findings)}")
    for f in result.phase_a_findings:
        print(f"  [{f.severity.name}] {f.description} @ {f.file_or_endpoint}")
    print(f"Phase B findings: {len(result.phase_b_findings)}")
    for f in result.phase_b_findings:
        print(f"  [{f.severity.name}] {f.description} @ {f.file_or_endpoint}")
    if result.errors:
        print("Errors:")
        for e in result.errors:
            print(f"  ! {e}")


@security_app.command("report")
def security_report_command(
    target: str = typer.Argument(..., help="Target: URL, IP, or authorized local path."),
    phases: str = typer.Option("", "--phases", help="Phases to run, e.g. 'ab', 'abc' (default from squad.toml)."),
    repo: str = typer.Option("", "--repo", help="Local repo path for Phase B (default: cwd)."),
    out: str = typer.Option("", "--out", help="Write report to this file (.md/.html/.pdf)."),
    fmt: str = typer.Option("", "--format", help="Report format: md | html | pdf (default by extension)."),
) -> None:
    """Oracle report writer: run Nightwing phases, render a report, persist the run.

    Produces an executive summary, severity-sorted findings table with CWE and
    OWASP Top 10 mapping, a 'what was skipped and why' section, a compliance
    mapping, and a raw evidence appendix. Markdown by default; HTML/PDF optional.
    """
    from squad.agent.nightwing import Nightwing
    from squad.agent.oracle import Oracle
    from squad.config.squadcfg import load_config
    from squad.store.history import ScanStore

    cfg = load_config()
    if not phases:
        phases = cfg.default_phases

    nw = Nightwing(target, local_repo_path=repo or None)
    skipped: dict[str, str] = {}

    def _confirm(t, cmds):
        if not cmds:
            skipped["active-scan"] = "no supported Phase C tools installed"
            return False
        print(f"\n[phase-c] target: {t}")
        for c in cmds:
            print(f"    $ {c}")
        print("[phase-c] Non-destructive recon. Run them? [y/N]")
        ans = input().strip().lower()
        if ans not in ("y", "yes"):
            skipped["active-scan"] = "operator declined Phase C consent"
        return ans in ("y", "yes")

    # Phase A & B (authorized-gated inside run_all)
    try:
        result = nw.run_all()
    except PermissionError as e:
        print(f"[refused] {e}")
        return

    findings = list(result.phase_a_findings) + list(result.phase_b_findings)
    for e in result.errors:
        skipped.setdefault("error", e)

    # Phase C, if requested
    if "c" in phases.lower():
        try:
            findings.extend(nw.run_phase_c(confirm_commands=_confirm))
        except PermissionError as e:
            skipped["active-scan"] = str(e)

    # Persist the run for history/diff/gate.
    store = ScanStore()
    run_id = store.new_run(target, phases)
    store.add_findings(run_id, findings)
    store.finish_run(run_id)
    print(f"[ok] run {run_id} recorded ({len(findings)} findings).")

    # Determine output format
    eff_fmt = fmt or (out.rsplit(".", 1)[-1] if "." in out else "") or "md"
    eff_fmt = eff_fmt.lower()

    oracle = Oracle(findings=findings, target=target, skipped=skipped)
    if eff_fmt == "pdf":
        report_bytes = oracle.to_pdf()
        if out:
            with open(out, "wb") as fh:
                fh.write(report_bytes)
            print(f"[ok] report written to {out}")
        else:
            sys.stdout.buffer.write(report_bytes)
    elif eff_fmt == "html":
        report = oracle.to_html()
        if out:
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(report)
            print(f"[ok] report written to {out}")
        else:
            print(report)
    else:
        report = oracle.to_markdown()
        if out:
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(report)
            print(f"[ok] report written to {out}")
        else:
            print(report)

    # Optional notification
    if cfg.notify_on_complete:
        from squad.notify import scan_completed

        counts = store.count_by_severity(run_id)
        risk = "high" if counts.get("high") or counts.get("critical") else "low"
        scan_completed(target, len(findings), risk, channel=cfg.notify_channel)


@security_app.command("stop")
def security_stop_command(
    run_id: str = typer.Argument(..., help="Run id to terminate."),
) -> None:
    """Kill-switch: terminate a running scan and all its child processes."""
    from squad.agent.rate_limit import GLOBAL_KILL_SWITCH

    count = GLOBAL_KILL_SWITCH.terminate(run_id)
    if count:
        print(f"[ok] terminated {count} process(es) for run {run_id}.")
    else:
        print(f"[note] no active processes for run {run_id} (already stopped?).")
        active = GLOBAL_KILL_SWITCH.active()
        if active:
            print("  active runs:", ", ".join(f"{k}({v})" for k, v in active.items()))


@security_app.command("history")
def security_history_command(
    target: str = typer.Option("", "--target", help="Filter runs by target."),
    limit: int = typer.Option(20, "--limit", help="Max runs to list."),
) -> None:
    """List past scan runs and their severity counts."""
    from squad.store.history import ScanStore

    store = ScanStore()
    for r in store.runs(target or None, limit=limit):
        counts = store.count_by_severity(r["run_id"])
        parts = " ".join(f"{s}={counts[s]}" for s in ("critical", "high", "medium", "low", "info"))
        print(f"{r['run_id']}  {r['started_at'][:19]}  {r['target']}  [{r['phases']}]  {parts}")


@security_app.command("diff")
def security_diff_command(
    run_a: str = typer.Argument(..., help="Earlier run id."),
    run_b: str = typer.Argument(..., help="Later run id."),
) -> None:
    """Compare two runs: show new and fixed findings."""
    from squad.store.history import ScanStore

    store = ScanStore()
    d = store.diff(run_a, run_b)
    print(f"Diff {run_a} -> {run_b}\n")
    print(f"New findings ({len(d['new'])}):")
    for tool, ep, sev, desc in d["new"]:
        print(f"  + [{sev.upper()}] {tool} {ep} :: {desc}")
    print(f"\nFixed findings ({len(d['fixed'])}):")
    for tool, ep, sev, desc in d["fixed"]:
        print(f"  - [{sev.upper()}] {tool} {ep} :: {desc}")


@security_app.command("status")
def security_status_command() -> None:
    """Live overview: latest run, finding counts, active kill-switch runs."""
    from squad.agent.rate_limit import GLOBAL_KILL_SWITCH
    from squad.store.history import ScanStore

    store = ScanStore()
    s = store.status_summary()
    print(f"Total runs: {s['total_runs']}")
    print(f"Latest run: {s['latest_run']} target={s['latest_target']}")
    if s["latest_severity"]:
        print("  latest severity:", " ".join(f"{k}={v}" for k, v in s["latest_severity"].items()))
    print(
        "  open findings per recent run:",
        ", ".join(f"{k}={v}" for k, v in s["open_by_run"].items()),
    )
    active = GLOBAL_KILL_SWITCH.active()
    print(f"Active scan processes: {active or 'none'}")


@security_app.command("retest")
def security_retest_command(
    run_id: str = typer.Argument(..., help="Run id whose findings to retest."),
    tool: str = typer.Option("", "--tool", help="Only retest findings from this tool."),
    endpoint: str = typer.Option("", "--endpoint", help="Only retest findings at this endpoint."),
) -> None:
    """Mark matched findings in a run as verified (operator confirms retest)."""
    from squad.store.history import ScanStore

    store = ScanStore()
    matched = store.run_findings(run_id)
    if tool:
        matched = [f for f in matched if f["tool"] == tool]
    if endpoint:
        matched = [f for f in matched if endpoint in f["file_or_endpoint"]]
    if not matched:
        print("[note] no findings matched.")
        return
    print(f"Retesting {len(matched)} finding(s) in run {run_id}:")
    for f in matched:
        print(f"  [{f['severity'].upper()}] {f['tool']} {f['file_or_endpoint']} :: {f['description']}")
    ans = input("Confirm re-verified after retest? [y/N]: ").strip().lower()
    if ans in ("y", "yes"):
        store.set_status_by_key(run_id, tool or "__all__", endpoint or "__all__", "verified")
        print("[ok] marked verified.")
    else:
        print("[note] unchanged.")


@security_app.command("gate")
def security_gate_command(
    run_id: str = typer.Argument(..., help="Run id to gate on."),
    fail_on: str = typer.Option("high", "--fail-on", help="Fail if any finding at/above this severity is open."),
) -> None:
    """CI-style gate: exit non-zero if open findings meet/exceed a severity."""
    from squad.store.history import ScanStore

    store = ScanStore()
    passed, blockers = store.gate(run_id, fail_on=fail_on)
    for b in blockers:
        print(f"[blocker] [{b['severity'].upper()}] {b['tool']} {b['file_or_endpoint']} :: {b['description']}")
    if passed:
        print(f"[ok] gate passed (fail-on {fail_on}).")
    else:
        print(f"[fail] gate failed: {len(blockers)} blocker(s) at/above {fail_on}.")
        raise typer.Exit(1)


@security_app.command("export")
def security_export_command(
    run_id: str = typer.Argument(..., help="Run id to export."),
    fmt: str = typer.Option("csv", "--format", help="csv | jira | json."),
    out: str = typer.Option("", "--out", help="Write to file (default stdout)."),
) -> None:
    """Export a run's findings for ticketing/audit (CSV/JIRA/JSON)."""
    from squad.compliance import to_csv, to_jira_json
    from squad.security_findings import SecurityFinding, SecuritySeverity
    from squad.store.history import ScanStore

    store = ScanStore()
    rows = store.run_findings(run_id)
    findings = [
        SecurityFinding(
            tool=r["tool"],
            severity=SecuritySeverity(r["severity"]),
            description=r["description"],
            file_or_endpoint=r["file_or_endpoint"],
            evidence_snippet=r["evidence_snippet"],
            cwe=r["cwe"],
            owasp_category=r["owasp_category"],
            remediation=r["remediation"],
        )
        for r in rows
    ]
    if fmt == "csv":
        text = to_csv(findings)
    elif fmt == "jira":
        text = to_jira_json(findings)
    else:
        from squad.agent.oracle import Oracle

        run = store.get_run(run_id)
        target = run["target"] if run else ""
        text = Oracle(findings=findings, target=target).to_json()
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"[ok] exported to {out}")
    else:
        print(text)


@security_app.command("doctor")
def security_doctor_command() -> None:
    """Run the squad environment self-check (tools, DB, data dir)."""
    from squad.doctor import print_doctor

    print_doctor()


@security_app.command("role")
def security_role_command(
    set_to: str = typer.Argument(None, help="Set role: owner | operator | auditor (omit to show)."),
) -> None:
    """Show or set the operating role. auditor is read-only."""
    from squad.roles import current_role, set_role

    if set_to:
        try:
            set_role(set_to)
            print(f"[ok] role set to {set_to}.")
        except ValueError as e:
            print(f"[refused] {e}")
            raise typer.Exit(2) from None
    else:
        print(f"current role: {current_role()}")
        print("  owner: full control (targets, installs, intrusive scans)")
        print("  operator: run scans + export")
        print("  auditor: read-only signed audit export")


@security_app.command("audit-export")
def security_audit_export_command(
    path: str = typer.Option("", "--audit-path", help="Audit log path."),
    out: str = typer.Option("", "--out", help="Write signed export to file."),
) -> None:
    """Produce a signed chain-of-custody export of the audit log."""
    from squad.audit.audit import AuditLog, default_audit_path
    from squad.roles import can, current_role, export_audit

    if not can("export_audit"):
        print(f"[refused] role '{current_role()}' cannot export the audit log.")
        raise typer.Exit(2)

    log = AuditLog(path or default_audit_path())
    lines = log.entries()
    signed = export_audit(lines)
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(signed)
        print(f"[ok] signed audit export written to {out} (role {current_role()})")
    else:
        print(signed)


@security_app.command("notify")
def security_notify_command(
    run_id: str = typer.Argument(..., help="Run id to notify about."),
    channel: str = typer.Option("", "--channel", help="console | desktop."),
) -> None:
    """Send a notification for a completed scan run."""
    from squad.config.squadcfg import load_config
    from squad.notify import scan_completed
    from squad.store.history import ScanStore

    store = ScanStore()
    run = store.get_run(run_id)
    if not run:
        print(f"[refused] unknown run {run_id}")
        raise typer.Exit(2)
    counts = store.count_by_severity(run_id)
    total = sum(counts.values())
    risk = "high" if counts.get("high") or counts.get("critical") else "low"
    ch = channel or load_config().notify_channel
    scan_completed(run["target"], total, risk, channel=ch)


@security_app.command("version")
def security_version_command() -> None:
    """Show the squad version."""
    from squad.version import __version__

    print(f"squad {__version__} (security squad)")


app.add_typer(security_app, name="security")


# ---------------------------------------------------------------------------
# Developer Assistant Commands (`squad dev`)
# ---------------------------------------------------------------------------
dev_app = typer.Typer(help="Developer Assistant & Vibe Coding tools", no_args_is_help=True)


@dev_app.command("review")
def dev_review_command(
    path: str = typer.Argument(..., help="File or directory path to review."),
    output: str = typer.Option("", "--out", help="Write report to Markdown file."),
) -> None:
    """Run comprehensive developer review (Quality + Security SAST + Real-time Intel)."""
    from squad.dev import DeveloperAssistant

    assistant = DeveloperAssistant()
    try:
        res = assistant.review_code(path)
        print(res.report_markdown)
        if output:
            with open(output, "w", encoding="utf-8") as fh:
                fh.write(res.report_markdown)
            print(f"[ok] report written to {output}")
    except Exception as exc:
        print(f"[error] review failed: {exc}")
        raise typer.Exit(1) from None


@dev_app.command("testgen")
def dev_testgen_command(
    file: str = typer.Argument(..., help="Python source file to generate tests for."),
) -> None:
    """Generate unit test suite for a Python source file."""
    from squad.dev import DeveloperAssistant

    assistant = DeveloperAssistant()
    try:
        res = assistant.generate_tests(file)
        print(f"[ok] generated test suite: {res.test_file_created} ({res.tests_generated} test cases)")
        print("\n--- Generated Code ---")
        print(res.content)
    except Exception as exc:
        print(f"[error] test generation failed: {exc}")
        raise typer.Exit(1) from None


@dev_app.command("refactor")
def dev_refactor_command(
    file: str = typer.Argument(..., help="Source file to refactor."),
    write: bool = typer.Option(False, "--write", "-w", help="Overwrite file with refactored code."),
) -> None:
    """Suggest clean modern refactored code (type hints, error handling)."""
    from squad.dev import DeveloperAssistant

    assistant = DeveloperAssistant()
    try:
        refactored = assistant.refactor_code(file)
        if write:
            with open(file, "w", encoding="utf-8") as fh:
                fh.write(refactored)
            print(f"[ok] refactored code written to {file}")
        else:
            print("--- Suggested Refactored Code ---")
            print(refactored)
    except Exception as exc:
        print(f"[error] refactoring failed: {exc}")
        raise typer.Exit(1) from None


# ---------------------------------------------------------------------------
# Real-Time Intelligence Commands (`squad intel`)
# ---------------------------------------------------------------------------
intel_app = typer.Typer(help="Real-Time Security Threat & Coding Intelligence", no_args_is_help=True)


@intel_app.command("fetch")
def intel_fetch_command() -> None:
    """Fetch real-time security threat feeds and coding practices online."""
    from squad.intel import RealTimeIntelEngine

    engine = RealTimeIntelEngine()
    print("[intel] Fetching real-time security advisories & coding standards...")
    res = engine.fetch_realtime_updates()
    print(f"[ok] Real-time intel updated. Sources: {', '.join(res['sources'])}")
    print(f"     Total advisories: {res['total_advisories']}")
    print(f"     Total coding practices: {res['total_coding_practices']}")


@intel_app.command("search")
def intel_search_command(
    query: str = typer.Argument(..., help="Search term (CVE, CWE, language, framework)."),
) -> None:
    """Search real-time security advisories and coding best practices."""
    from squad.intel import RealTimeIntelEngine

    engine = RealTimeIntelEngine()
    results = engine.search_intel(query)
    if not results:
        print(f"[intel] No intelligence records matched '{query}'.")
        return

    print(f"[intel] Found {len(results)} intelligence record(s) matching '{query}':\n")
    for r in results:
        item = r["data"]
        if r["type"] == "security_advisory":
            print(f"  [!] [{item['severity']}] {item['id']}: {item['title']} ({item['cwe']})")
            print(f"   Summary: {item['summary']}")
            print(f"   Fix: {item['recommendation']}\n")
        else:
            print(f"  [i] [{item['language'].upper()}] {item['topic']}")
            print(f"   Summary: {item['summary']}")
            print(f"   Example: {item.get('example', 'N/A')}\n")


@intel_app.command("status")
def intel_status_command() -> None:
    """Show real-time intelligence feed statistics."""
    import time

    from squad.intel import RealTimeIntelEngine

    engine = RealTimeIntelEngine()
    feed = engine.intel
    age_hours = (time.time() - feed.last_updated) / 3600.0
    print("=== Real-Time Intelligence Feed Status ===")
    print(f"Last updated: {age_hours:.2f} hours ago")
    print(f"Sources: {', '.join(feed.sources)}")
    print(f"Security Advisories cached: {len(feed.security_advisories)}")
    print(f"Coding Practices cached: {len(feed.coding_practices)}")


app.add_typer(dev_app, name="dev")
app.add_typer(intel_app, name="intel")


@app.command(name="chat")
def chat_command(
    message: str = typer.Option(None, "--message", "-m", help="One-shot: handle this message and exit (no REPL)."),
    provider: str = typer.Option(
        "",
        "--provider",
        help="LLM provider for research answers (e.g. ollama, openai, openrouter, anthropic). Sets SQUAD_LLM_PROVIDER.",
    ),
) -> None:
    """Interactive chatbot: offline commands + LLM-backed research.

    Use `--provider ollama` to answer research questions with free local Ollama
    models (no API key needed) even if other provider keys are set.
    """
    if provider:
        import os

        os.environ["SQUAD_LLM_PROVIDER"] = provider
    from squad.chat import chat_loop

    chat_loop(one_shot=message)


@app.command(name="dashboard")
def dashboard_command() -> None:
    """Launch the blue-themed squad TUI dashboard (no web)."""
    from squad.dashboard import dashboard_command as _run

    _run()


def main() -> None:
    _force_utf8_stdio()
    from squad.config.keys import load_keys

    load_keys()
    app()

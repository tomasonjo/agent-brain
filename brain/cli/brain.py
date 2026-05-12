"""brain — operator CLI.

Commands:
    brain init-db        apply Neo4j schema
    brain scheduler      run APScheduler daemon (foreground)
    brain validate       validate triggers/*.yaml
    brain run <flow>     invoke a flow manually (testing)
    brain status         print system_state()
    brain mcp            run the FastMCP server (stdio)
"""

from __future__ import annotations

import json
import sys

import typer
import yaml
from rich.console import Console
from rich.table import Table

from brain.config import SETTINGS
from brain.flows import FLOWS

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()


@app.command("init-db")
def init_db() -> None:
    """Apply schema.cypher to the configured Neo4j database."""
    from brain.store import migrate

    result = migrate.apply_all()
    console.print(f"[green]OK[/green] applied {result['schema_statements_applied']} statements")


@app.command()
def scheduler() -> None:
    """Run the APScheduler daemon in the foreground."""
    from brain.scheduler.main import run

    run()


@app.command()
def validate() -> None:
    """Validate every triggers/*.yaml against the schema."""
    from brain.mcp_server.validation import validate_trigger_config, validate_trigger_id

    if not SETTINGS.triggers_dir.exists():
        console.print(f"[yellow]no triggers dir at {SETTINGS.triggers_dir}[/yellow]")
        return

    ok = 0
    bad = 0
    known = set(FLOWS.keys())
    for f in sorted(SETTINGS.triggers_dir.glob("*.yaml")):
        try:
            cfg = yaml.safe_load(f.read_text()) or {}
            tid = cfg.get("id") or f.stem
            validate_trigger_id(tid)
            validate_trigger_config(cfg, known_flows=known)
            console.print(f"[green]OK[/green] {f.name}")
            ok += 1
        except Exception as e:
            console.print(f"[red]BAD[/red] {f.name}: {e}")
            bad += 1
    console.print(f"\n{ok} ok, {bad} bad")
    if bad:
        raise typer.Exit(code=1)


@app.command("run")
def run_flow(
    flow: str = typer.Argument(..., help="Flow id, e.g. daily_brief"),
    param: list[str] = typer.Option(  # noqa: B008
        [], "--param", "-p", help="key=value (repeatable). JSON values allowed."
    ),
) -> None:
    """Invoke a flow manually. Records a :Fire in Neo4j like the scheduler would."""
    from brain.scheduler.dispatcher import dispatch

    params: dict = {}
    for kv in param:
        if "=" not in kv:
            raise typer.BadParameter(f"expected key=value, got {kv!r}")
        k, v = kv.split("=", 1)
        try:
            params[k] = json.loads(v)
        except (ValueError, json.JSONDecodeError):
            params[k] = v
    if flow not in FLOWS:
        raise typer.BadParameter(f"unknown flow: {flow}. Known: {sorted(FLOWS)}")
    console.print(f"running flow={flow} params={params}")
    dispatch(flow, f"manual:{flow}", params)
    console.print("[green]done[/green]")


@app.command()
def status() -> None:
    """Pretty-print system_state()."""
    from brain.mcp_server.server import system_state

    state = system_state()

    console.print(
        f"[bold]user[/bold]: {'exists' if state['user_exists'] else 'not onboarded'}"
    )

    counts = state["memory_counts"] or {}
    if counts:
        console.print("[bold]memory counts[/bold]")
        for k in sorted(counts):
            console.print(f"  {k}: {counts[k]}")

    triggers = state["active_triggers"]
    if triggers:
        t = Table(title="Active triggers")
        t.add_column("id")
        t.add_column("flow")
        t.add_column("schedule")
        t.add_column("fires")
        t.add_column("last fired")
        for tr in triggers:
            sched = tr.get("schedule") or {}
            stats = tr.get("stats") or {}
            t.add_row(
                tr.get("id", ""),
                tr.get("flow", ""),
                f"{sched.get('expr', '')} {sched.get('tz', '')}".strip(),
                str(stats.get("fires", 0)),
                str(stats.get("last_fired_at") or "-"),
            )
        console.print(t)

    plans = state["active_plans"]
    if plans:
        t = Table(title="Active plans")
        t.add_column("id")
        t.add_column("title")
        t.add_column("next step")
        for p in plans:
            t.add_row(p["id"], p["title"], p.get("next_step") or "-")
        console.print(t)

    fires = state["recent_fires"]
    if fires:
        t = Table(title="Recent fires")
        t.add_column("flow")
        t.add_column("at")
        t.add_column("ok")
        t.add_column("memories")
        for f in fires:
            ok_str = "ok" if f["succeeded"] else ("FAIL" if f["succeeded"] is False else "...")
            t.add_row(f["flow_id"], str(f["at"]), ok_str, str(f["memories_written"]))
        console.print(t)


@app.command()
def mcp() -> None:
    """Run the FastMCP server on stdio. Configure your client to launch this."""
    from brain.mcp_server.server import main as run_mcp

    run_mcp()


@app.command()
def dream(
    session_id: str = typer.Argument(..., help="Session whose events to distill."),
    debounce: int = typer.Option(
        60, "--debounce", help="Skip if a dream for this session ran within N seconds. 0 disables."
    ),
) -> None:
    """Distill one session's :Event chain into durable :Memory nodes."""
    from brain.scheduler.dispatcher import dispatch

    dispatch(
        "dream_session",
        "dream_session",
        {"session_id": session_id, "debounce_seconds": debounce},
    )


@app.command("dream-synthesis")
def dream_synthesis_cmd(
    days: int = typer.Option(7, "--days", help="Look back this many days."),
    max_memories: int = typer.Option(100, "--max-memories"),
) -> None:
    """Walk recent memories and write 1-3 synthesized theme notes."""
    from brain.scheduler.dispatcher import dispatch

    dispatch(
        "dream_synthesis",
        "dream_synthesis",
        {"days": days, "max_memories": max_memories},
    )


def _main() -> int:
    try:
        app()
        return 0
    except SystemExit as e:  # typer raises SystemExit
        return int(e.code or 0)


if __name__ == "__main__":
    sys.exit(_main())

from pathlib import Path
from typing import List

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agent.config import config
from agent.gemini import check_gemini_connectivity

console = Console()


def _status_row(ok: bool) -> str:
    return "[green]CONNECTED[/green]" if ok else "[red]NOT READY[/red]"


def _check(url: str, headers: dict, timeout: float = 8.0) -> tuple[bool, str]:
    try:
        resp = httpx.get(url, headers=headers, timeout=timeout)
        return resp.status_code == 200, f"status={resp.status_code}"
    except Exception as exc:
        return False, str(exc)


def _read_schedule_files() -> List[Path]:
    schedule_dir = Path(".state/runs/schedules")
    if not schedule_dir.exists():
        return []
    return sorted(schedule_dir.glob("*.json"), reverse=True)[:5]


def show_overview():
    """Show system readiness, recent runs, and recurring invoice schedules."""
    sb_url = config.SUPABASE_URL
    sb_key = config.supabase_rest_key
    if not sb_url or not sb_key:
        console.print(
            "[red]Error:[/red] missing Supabase REST credentials "
            "(SUPABASE_SERVICE_ROLE_KEY / SUPABASE_ANON_KEY)"
        )
        raise typer.Exit(1)

    headers = {"apikey": sb_key, "Authorization": f"Bearer {sb_key}"}
    console.print(Panel("[bold magenta]Agent Orchestration Overview[/bold magenta]"))

    runs = []
    skills = []
    try:
        runs_resp = httpx.get(
            f"{sb_url}/rest/v1/runs?order=created_at.desc&limit=5",
            headers=headers,
            timeout=10.0,
        )
        if runs_resp.status_code == 200:
            runs = runs_resp.json()

        skills_resp = httpx.get(
            f"{sb_url}/rest/v1/skills?select=id", headers=headers, timeout=10.0
        )
        if skills_resp.status_code == 200:
            skills = skills_resp.json()
    except Exception:
        pass

    skill_ids = sorted({s.get("id") for s in skills if s.get("id")})
    skills_table = Table(
        title="Available Skills", show_header=True, header_style="bold cyan"
    )
    skills_table.add_column("Skill ID")
    skills_table.add_column("Status")
    if skill_ids:
        for sid in skill_ids:
            skills_table.add_row(sid, "[green]Active[/green]")
    else:
        skills_table.add_row("No skills found", "[yellow]N/A[/yellow]")
    console.print(skills_table)

    runs_table = Table(title="Recent Runs", show_header=True, header_style="bold cyan")
    runs_table.add_column("Run ID")
    runs_table.add_column("Skill")
    runs_table.add_column("Status")
    runs_table.add_column("Created")
    if runs:
        for run in runs:
            status = run.get("status", "unknown")
            style = (
                "green"
                if status == "success"
                else "red"
                if status in ("failed", "error")
                else "yellow"
            )
            runs_table.add_row(
                str(run.get("id", ""))[:8],
                str(run.get("skill_id") or "N/A"),
                f"[{style}]{status}[/{style}]",
                str(run.get("created_at", ""))[:16].replace("T", " "),
            )
    else:
        runs_table.add_row("-", "-", "[yellow]No recent runs[/yellow]", "-")
    console.print(runs_table)

    dep_table = Table(
        title="Integration Status", show_header=True, header_style="bold cyan"
    )
    dep_table.add_column("Service")
    dep_table.add_column("Status")
    dep_table.add_column("Details")

    supabase_ok, supabase_details = _check(f"{sb_url}/rest/v1/", headers)

    if config.DUST_API_KEY and config.DUST_WORKSPACE_ID:
        dust_ok, dust_details = _check(
            f"https://dust.tt/api/v1/w/{config.DUST_WORKSPACE_ID}/assistant/agent_configurations",
            {"Authorization": f"Bearer {config.DUST_API_KEY}"},
        )
    else:
        dust_ok, dust_details = False, "missing DUST_API_KEY or DUST_WORKSPACE_ID"

    gemini_ok, gemini_details = check_gemini_connectivity(
        config.gemini_api_key, timeout=8.0
    )

    dep_table.add_row("Supabase", _status_row(supabase_ok), supabase_details)
    dep_table.add_row("Dust", _status_row(dust_ok), dust_details)
    dep_table.add_row("Gemini", _status_row(gemini_ok), gemini_details)
    console.print(dep_table)

    schedule_files = _read_schedule_files()
    schedule_table = Table(
        title="Recurring Invoice Jobs", show_header=True, header_style="bold cyan"
    )
    schedule_table.add_column("Job File")
    schedule_table.add_column("Status")
    if schedule_files:
        for path in schedule_files:
            schedule_table.add_row(path.name, "[green]Scheduled[/green]")
    else:
        schedule_table.add_row("No scheduled jobs", "[yellow]N/A[/yellow]")
    console.print(schedule_table)

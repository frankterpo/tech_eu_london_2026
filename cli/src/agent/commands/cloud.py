import time
from typing import Dict, Tuple

import httpx
import typer
from rich.console import Console
from rich.table import Table

from agent.config import config
from agent.gemini import check_gemini_connectivity

console = Console()


def _check_supabase() -> Tuple[bool, str]:
    key = config.supabase_rest_key
    if not config.SUPABASE_URL or not key:
        return (
            False,
            "missing SUPABASE_URL or Supabase REST key "
            "(SUPABASE_SERVICE_ROLE_KEY / SUPABASE_ANON_KEY)",
        )

    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    try:
        resp = httpx.get(
            f"{config.SUPABASE_URL}/rest/v1/", headers=headers, timeout=10.0
        )
        if resp.status_code == 200:
            return True, "ok"
        return False, f"status={resp.status_code}"
    except Exception as exc:
        return False, str(exc)


def _check_dust() -> Tuple[bool, str]:
    if not config.DUST_API_KEY or not config.DUST_WORKSPACE_ID:
        return False, "missing DUST_API_KEY or DUST_WORKSPACE_ID"
    url = f"https://dust.tt/api/v1/w/{config.DUST_WORKSPACE_ID}/assistant/agent_configurations"
    headers = {"Authorization": f"Bearer {config.DUST_API_KEY}"}
    try:
        resp = httpx.get(url, headers=headers, timeout=10.0)
        if resp.status_code == 200:
            return True, "ok"
        return False, f"status={resp.status_code}"
    except Exception as exc:
        return False, str(exc)


def _check_gemini() -> Tuple[bool, str]:
    return check_gemini_connectivity(config.gemini_api_key, timeout=10.0)


def _print_dependency_status(statuses: Dict[str, Tuple[bool, str]]) -> None:
    table = Table(
        title="Cloud Dependency Checks", show_header=True, header_style="bold cyan"
    )
    table.add_column("Dependency")
    table.add_column("Status")
    table.add_column("Details")

    for name, (ok, details) in statuses.items():
        label = "[green]OK[/green]" if ok else "[red]FAIL[/red]"
        table.add_row(name, label, details)
    console.print(table)


def smoke_cloud(
    timeout_seconds: int = typer.Option(
        60, "--timeout-seconds", min=15, max=300, help="Worker smoke timeout."
    ),
):
    """Run cloud smoke: dependency checks + Worker /smoke execution."""
    statuses = {
        "Supabase": _check_supabase(),
        "Dust": _check_dust(),
        "Gemini": _check_gemini(),
    }
    _print_dependency_status(statuses)

    if not config.WORKER_URL:
        console.print("[red]Error:[/red] WORKER_URL not set in .env")
        raise typer.Exit(1)

    console.print(
        f"[bold blue]Running worker smoke at {config.WORKER_URL}...[/bold blue]"
    )
    started = time.perf_counter()
    timeout = httpx.Timeout(
        connect=10.0,
        read=float(timeout_seconds),
        write=min(30.0, float(timeout_seconds)),
        pool=20.0,
    )

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(f"{config.WORKER_URL}/smoke")
            resp.raise_for_status()
            payload = resp.json()

        run_id = payload.get("run_id")
        artifacts = payload.get("artifacts") or {}
        smoke_png = artifacts.get("smoke_png")
        if not run_id or not smoke_png:
            raise RuntimeError(f"Unexpected worker response: {payload}")

        elapsed = time.perf_counter() - started
        console.print(f"  [green]✓[/green] Run ID: [bold]{run_id}[/bold]")
        console.print(f"  [green]✓[/green] Artifact: {smoke_png}")
        console.print(f"  [green]✓[/green] Completed in {elapsed:.1f}s")
        console.print("[bold green]Cloud smoke test passed.[/bold green]")
    except Exception as exc:
        console.print(f"  [red]✗[/red] Worker smoke failed: {exc}")
        raise typer.Exit(1)

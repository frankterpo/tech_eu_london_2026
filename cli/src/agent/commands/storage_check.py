import os
from typing import Any, Dict, Optional

import httpx
import typer
from rich.console import Console
from rich.table import Table

from agent.supabase_auth import get_supabase_key

console = Console()


def _list_objects(
    sb_url: str, sb_key: str, bucket: str, prefix: str, limit: int = 10
) -> list[dict]:
    resp = httpx.post(
        f"{sb_url}/storage/v1/object/list/{bucket}",
        headers={
            "apikey": sb_key,
            "Authorization": f"Bearer {sb_key}",
            "Content-Type": "application/json",
        },
        json={
            "prefix": prefix,
            "limit": limit,
            "offset": 0,
            "sortBy": {"column": "created_at", "order": "desc"},
        },
        timeout=20.0,
    )
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


def _render_list(title: str, rows: list[dict]) -> None:
    table = Table(title=title, show_header=True, header_style="bold cyan")
    table.add_column("Name")
    table.add_column("Created")
    table.add_column("Size")
    if not rows:
        table.add_row("(none)", "-", "-")
    else:
        for item in rows:
            md: Dict[str, Any] = item.get("metadata") or {}
            table.add_row(
                str(item.get("name") or ""),
                str(item.get("created_at") or "")[:19].replace("T", " "),
                str(md.get("size") or "-"),
            )
    console.print(table)


def check_storage(
    run_id: Optional[str] = typer.Option(
        None, "--run-id", help="Optional run_id to inspect artifacts path."
    ),
):
    """Check Supabase Storage visibility for artifacts/auth/seeds and run folders."""
    sb_url = os.getenv("SUPABASE_URL")
    sb_key = get_supabase_key()
    if not sb_url or not sb_key:
        console.print(
            "[red]Error:[/red] missing SUPABASE_URL or Supabase REST key "
            "(SUPABASE_SERVICE_ROLE_KEY / SUPABASE_ANON_KEY)."
        )
        raise typer.Exit(1)

    console.print(f"[bold]Project:[/bold] {sb_url}")
    console.print(f"[bold]Key prefix:[/bold] {sb_key[:12]}...")

    try:
        seeds = _list_objects(sb_url, sb_key, "artifacts", "seeds/", limit=10)
        auth = _list_objects(sb_url, sb_key, "auth", "", limit=10)
        _render_list("Artifacts / seeds", seeds)
        _render_list("Auth bucket", auth)
        if run_id:
            modern = _list_objects(sb_url, sb_key, "artifacts", f"runs/{run_id}/", limit=20)
            legacy = _list_objects(sb_url, sb_key, "artifacts", f"{run_id}/", limit=20)
            _render_list(f"Artifacts / runs/{run_id}", modern)
            _render_list(f"Artifacts / {run_id} (legacy)", legacy)
    except Exception as exc:
        console.print(f"[red]Storage check failed:[/red] {exc}")
        raise typer.Exit(1)

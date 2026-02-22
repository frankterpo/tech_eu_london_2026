import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from agent.logger import EventLogger
from agent.skill_acquisition import synthesize_skill_for_prompt

console = Console()


def extrapolate(
    prompt: str = typer.Argument(..., help="Natural-language workflow request."),
    platform_id: str = typer.Option(
        "envoice", "--platform-id", help="Platform map identifier."
    ),
    agent_id: str = typer.Option(
        "gemini-pro",
        "--agent-id",
        help="Dust assistant configuration ID (used when available).",
    ),
    skill_id: Optional[str] = typer.Option(
        None, "--skill-id", help="Optional fixed ID for the generated skill."
    ),
):
    """Generate a new skill from platform memory (with AI + deterministic fallback)."""
    EventLogger.console_log(
        "Agent Extrapolator",
        f"Generating skill from platform map [bold]{platform_id}[/bold]...",
        "bold magenta",
    )
    result = synthesize_skill_for_prompt(
        prompt=prompt,
        platform_id=platform_id,
        agent_id=agent_id,
        preferred_skill_id=skill_id,
    )

    spec = result["skill_spec"]
    seed_path = Path(result["seed_path"])
    console.print(f"[green]Skill generated:[/green] {result['skill_id']}")
    console.print(f"[green]Seed path:[/green] {seed_path}")
    if result.get("seed_storage_key"):
        console.print(f"[green]Seed storage:[/green] {result['seed_storage_key']}")
    console.print(
        f"[green]Steps:[/green] {len(spec.get('steps') or [])} | "
        f"Required slots: {len((spec.get('slots_schema') or {}).get('required') or [])}"
    )
    console.print(json.dumps(spec, indent=2), markup=False)

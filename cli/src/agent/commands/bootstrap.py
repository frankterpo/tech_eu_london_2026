from rich.console import Console
from agent.config import config

console = Console()


def run():
    """Validate environment and create necessary directories."""
    console.print("[bold blue]Bootstrapping agent...[/bold blue]")

    # Directories
    dirs = [
        config.ARTIFACT_DIR,
        config.RUNS_DIR,
        config.AUTH_DIR,
        config.RUNS_DIR / "schedules",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        console.print(f"  [green]✓[/green] Created {d}")

    console.print("[bold green]Bootstrap complete.[/bold green]")

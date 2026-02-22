import typer
import asyncio
from rich.console import Console
from playwright.async_api import async_playwright
from agent.config import config

console = Console()


async def smoke_test():
    console.print("[bold blue]Running local smoke test...[/bold blue]")

    # 1. Playwright Smoke
    console.print("  [yellow]Testing Playwright...[/yellow]")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=config.HEADLESS)
            page = await browser.new_page()
            await page.goto("about:blank")

            artifact_path = config.ARTIFACT_DIR / "smoke.png"
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(artifact_path))
            await browser.close()
    except Exception as e:
        error_text = str(e).strip()
        error_summary = error_text.splitlines()[0] if error_text else type(e).__name__
        console.print(f"  [red]✗[/red] Playwright smoke failed: {error_summary}")
        raise typer.Exit(code=1)

    if artifact_path.exists():
        console.print(f"  [green]✓[/green] Screenshot saved to {artifact_path}")
    else:
        console.print("  [red]✗[/red] Failed to save screenshot")
        raise typer.Exit(code=1)

    console.print("[bold green]Local smoke test passed.[/bold green]")


def run_local():
    """Run local smoke test (Playwright screenshot)."""
    asyncio.run(smoke_test())

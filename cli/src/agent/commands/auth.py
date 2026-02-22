import json
import os
from pathlib import Path
import typer
from rich.console import Console
from playwright.sync_api import sync_playwright
import httpx
from agent.supabase_auth import get_supabase_key


# Find .env in the workspace root
def load_env_robust():
    current = Path.cwd()
    for _ in range(5):
        env_path = current / ".env"
        if env_path.exists():
            from dotenv import load_dotenv

            load_dotenv(dotenv_path=env_path)
            return env_path
        current = current.parent
    return None


load_env_robust()

console = Console()


def save_auth(name: str):
    """Launch headed browser to capture Envoice auth state and upload to Supabase."""
    base_url = os.getenv("ENVOICE_BASE_URL", "https://app.envoice.eu")
    auth_dir = Path(".state/auth")
    auth_dir.mkdir(parents=True, exist_ok=True)
    auth_path = auth_dir / f"{name}.json"

    console.print(f"[bold blue]Starting auth capture for '{name}'...[/bold blue]")
    console.print(f"  URL: {base_url}")

    try:
        with sync_playwright() as p:
            # We need headed mode for the user to log in
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()

            page.goto(base_url)

            console.print(
                "\n[yellow]Please log in to Envoice in the browser window.[/yellow]"
            )
            console.print(
                "[yellow]The CLI will wait until you are logged in (URL contains '/dashboard' or '/invoices').[/yellow]"
            )

            # Wait for navigation to a post-login page
            try:
                page.wait_for_url("**/dashboard**", timeout=300000)  # 5 minute timeout
            except Exception:
                try:
                    page.wait_for_url("**/invoices**", timeout=1000)
                except Exception:
                    console.print(
                        "[red]Timeout waiting for login. Please try again.[/red]"
                    )
                    browser.close()
                    raise typer.Exit(1)

            console.print("[green]✓ Login detected![/green]")

            # Save storage state
            storage = context.storage_state()
            with open(auth_path, "w") as f:
                json.dump(storage, f, indent=2)

            console.print(f"  ✓ Local auth state saved to {auth_path}")
            browser.close()
    except typer.Exit:
        raise
    except Exception as e:
        error_text = str(e).strip()
        error_summary = error_text.splitlines()[0] if error_text else type(e).__name__
        console.print(f"[red]Browser launch/capture failed:[/red] {error_summary}")
        raise typer.Exit(1)

    # Upload to Supabase
    sb_url = os.getenv("SUPABASE_URL")
    sb_key = get_supabase_key()

    if not sb_url or not sb_key:
        console.print(
            "[red]Error: SUPABASE_URL or SUPABASE_API_KEY not set. Cannot upload.[/red]"
        )
        raise typer.Exit(1)

    console.print("[bold blue]Uploading auth state to Supabase...[/bold blue]")
    console.print(f"  (Using key: {sb_key[:10]}...)")

    with open(auth_path, "rb") as f:
        file_content = f.read()

    headers = {
        "apikey": sb_key,
        "Authorization": f"Bearer {sb_key}",
        "x-upsert": "true",
    }

    upload_url = f"{sb_url}/storage/v1/object/auth/{name}.json"

    try:
        response = httpx.post(
            upload_url, headers=headers, content=file_content, timeout=30.0
        )
        if response.status_code in (200, 201):
            console.print(
                f"  [green]✓[/green] Auth state uploaded to Supabase: [bold]auth/{name}.json[/bold]"
            )
        else:
            console.print(
                f"  [red]✗[/red] Upload failed: {response.status_code} {response.text}"
            )
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"  [red]✗[/red] Upload error: {str(e)}")
        raise typer.Exit(1)

    console.print("\n[bold green]Auth capture and upload complete![/bold green]")

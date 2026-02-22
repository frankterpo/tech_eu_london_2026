import os
import typer
from rich.console import Console
import httpx
import json
import jsonpatch
from pathlib import Path
from jsonschema import ValidationError, validate
from agent.seed_sync import sync_seed_to_supabase
from agent.supabase_auth import get_supabase_key

console = Console()


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


def apply_patch(skill_id: str, eval_key: str):
    """Apply a JSON patch from an evaluation to a skill and update Supabase."""
    sb_url = os.getenv("SUPABASE_URL")
    sb_key = get_supabase_key()
    supabase_enabled = bool(sb_url and sb_key)

    console.print(
        f"[bold blue]Applying patch to skill '{skill_id}' using eval '{eval_key}'...[/bold blue]"
    )

    headers = (
        {
            "apikey": sb_key,
            "Authorization": f"Bearer {sb_key}",
        }
        if sb_key
        else {}
    )

    try:
        # 1. Fetch Eval from Storage
        eval_data = None
        eval_storage_key = eval_key.replace("artifacts/", "", 1)

        if supabase_enabled:
            try:
                eval_url = f"{sb_url}/storage/v1/object/authenticated/artifacts/{eval_storage_key}"
                eval_resp = httpx.get(eval_url, headers=headers, timeout=20.0)
                eval_resp.raise_for_status()
                eval_data = eval_resp.json()
            except Exception as fetch_exc:
                console.print(
                    f"[yellow]Supabase eval fetch failed ({fetch_exc}); trying local eval cache.[/yellow]"
                )

        if eval_data is None:
            run_id = Path(eval_storage_key).stem
            local_eval = Path(".state/runs/evals") / f"{run_id}.json"
            if not local_eval.exists():
                console.print(
                    f"[red]Error:[/red] Evaluation not found in Supabase or local cache ({local_eval})."
                )
                raise typer.Exit(1)
            with open(local_eval, "r", encoding="utf-8") as f:
                eval_data = json.load(f)

        patch_ops = eval_data.get("patch", [])

        if not patch_ops:
            console.print(
                "[yellow]No patch operations found in evaluation. Nothing to apply.[/yellow]"
            )
            return

        # 2. Fetch current Skill from DB
        # For now, we'll look in seeds/ folder. Later we fetch from DB.
        seed_path = Path(f"seeds/{skill_id}.json")
        if not seed_path.exists():
            console.print(f"[red]Error: Skill seed not found at {seed_path}[/red]")
            raise typer.Exit(1)

        with open(seed_path, "r") as f:
            skill_spec = json.load(f)

        # 3. Apply Patch
        patch = jsonpatch.JsonPatch(patch_ops)
        patched_skill = patch.apply(skill_spec)

        # Guardrail: keep slots schema from being unintentionally erased by noisy LLM patches.
        original_props = (
            skill_spec.get("slots_schema", {}).get("properties", {})
            if isinstance(skill_spec.get("slots_schema"), dict)
            else {}
        )
        patched_props = (
            patched_skill.get("slots_schema", {}).get("properties", {})
            if isinstance(patched_skill.get("slots_schema"), dict)
            else {}
        )
        if original_props and not patched_props:
            patched_skill["slots_schema"] = skill_spec["slots_schema"]

        # Validate patched skill before persisting.
        schema_path = Path("schemas/SkillSpec.schema.json")
        if schema_path.exists():
            with open(schema_path, "r", encoding="utf-8") as sf:
                skill_schema = json.load(sf)
            validate(instance=patched_skill, schema=skill_schema)

        # Increment version
        patched_skill["version"] = skill_spec.get("version", 1) + 1

        console.print(
            f"  [green]✓[/green] Patch applied. New version: {patched_skill['version']}"
        )

        # 4. Save patched skill back to seeds (and later to DB)
        with open(seed_path, "w") as f:
            json.dump(patched_skill, f, indent=2)
        try:
            storage_key = sync_seed_to_supabase(skill_id, seed_path, source="patch")
            if storage_key:
                console.print(f"  Supabase seed sync: [bold]{storage_key}[/bold]")
        except Exception as sync_exc:
            console.print(f"  [yellow]Seed sync skipped ({sync_exc})[/yellow]")

        console.print(
            f"\n[bold green]✓ Skill '{skill_id}' patched successfully![/bold green]"
        )
        console.print(f"  Updated seed: [bold]{seed_path}[/bold]")

    except ValidationError as e:
        console.print(f"  [red]✗[/red] Patch validation failed: {e.message}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"  [red]✗[/red] Patch application failed: {str(e)}")
        raise typer.Exit(1)

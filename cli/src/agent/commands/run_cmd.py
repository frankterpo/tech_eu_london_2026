import os
import json
import uuid
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
import httpx
from agent.executor import SkillExecutor
from agent.logger import EventLogger
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


def run_skill(skill_id: str, input_file: Optional[Path] = None) -> str:
    """Execute a skill using local Playwright and sync results to Supabase."""
    sb_url = os.getenv("SUPABASE_URL")
    sb_key = get_supabase_key()

    if not sb_url or not sb_key:
        console.print("[red]Error: SUPABASE_URL or SUPABASE_API_KEY not set.[/red]")
        raise typer.Exit(1)

    # 1. Load Skill Spec
    seed_path = Path(f"seeds/{skill_id}.json")
    if not seed_path.exists():
        EventLogger.console_log(
            "System", f"Skill seed not found at {seed_path}", "bold red"
        )
        raise typer.Exit(1)

    with open(seed_path, "r") as f:
        skill_spec = json.load(f)

    # 2. Load Input Slots
    slots = {}
    if input_file:
        if not input_file.exists():
            EventLogger.console_log(
                "System", f"Input file not found at {input_file}", "bold red"
            )
            raise typer.Exit(1)
        with open(input_file, "r") as f:
            slots = json.load(f)

    # 3. Initialize Run in Supabase
    EventLogger.console_log(
        "Agent Orchestrator",
        f"I am initializing a new run for skill [bold]{skill_id}[/bold]...",
    )
    headers = {
        "apikey": sb_key,
        "Authorization": f"Bearer {sb_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

    run_data = {
        "status": "running",
        "skill_id": skill_id,
        "skill_version": skill_spec.get("version", 1),
        "slots": slots,
    }

    try:
        response = httpx.post(f"{sb_url}/rest/v1/runs", headers=headers, json=run_data)
        response.raise_for_status()
        run_row = response.json()[0]
        run_id = run_row["id"]
        EventLogger.console_log(
            "Agent Orchestrator", f"Run ID [bold]{run_id}[/bold] created in Supabase."
        )
        EventLogger.log(
            "run_initialized",
            f"Run ID: {run_id}",
            {"skill_id": skill_id, "slots": slots},
        )
    except Exception:
        run_id = str(uuid.uuid4())
        EventLogger.console_log(
            "Agent Orchestrator",
            f"Failed to sync with Supabase, proceeding with local run ID: {run_id}",
            "bold yellow",
        )

    # 4. Execute Skill
    executor = SkillExecutor(run_id)
    try:
        report = executor.execute(skill_spec, slots)
    except Exception as e:
        EventLogger.console_log(
            "Agent Orchestrator",
            f"Executor crashed unexpectedly: {str(e)}",
            "bold red",
        )
        report = {
            "status": "failed",
            "error": str(e),
            "artifacts": {},
        }

    if report["status"] == "success":
        EventLogger.console_log(
            "Agent Orchestrator", "Skill execution was successful!", "bold green"
        )
        EventLogger.log("run_success", f"Run ID: {run_id}")
    else:
        error_summary = str(report.get("error") or "unknown error")
        EventLogger.console_log(
            "Agent Orchestrator",
            f"Skill execution failed: {error_summary}",
            "bold red",
        )
        EventLogger.log("run_failed", f"Run ID: {run_id}", {"error": error_summary})

    # 5. Upload Artifacts to Supabase
    EventLogger.console_log(
        "Agent Orchestrator",
        "I am uploading the execution artifacts (video, trace, logs) to Supabase...",
    )
    uploaded_artifacts = {}

    for key, local_path in report["artifacts"].items():
        if not os.path.exists(local_path):
            continue

        file_name = os.path.basename(local_path)
        storage_path = f"artifacts/{run_id}/{file_name}"

        with open(local_path, "rb") as f:
            file_content = f.read()

        content_type = "application/octet-stream"
        if file_name.endswith(".png"):
            content_type = "image/png"
        elif file_name.endswith(".json"):
            content_type = "application/json"
        elif file_name.endswith(".webm"):
            content_type = "video/webm"
        elif file_name.endswith(".zip"):
            content_type = "application/zip"

        upload_url = f"{sb_url}/storage/v1/object/{storage_path}"
        headers["Content-Type"] = content_type
        headers["x-upsert"] = "true"

        try:
            resp = httpx.post(
                upload_url, headers=headers, content=file_content, timeout=60.0
            )
            if resp.status_code in (200, 201):
                uploaded_artifacts[key] = storage_path
            else:
                EventLogger.console_log(
                    "Agent Orchestrator", f"Failed to upload {file_name}", "bold red"
                )
        except Exception as e:
            EventLogger.console_log(
                "Agent Orchestrator",
                f"Error uploading {file_name}: {str(e)}",
                "bold red",
            )

    # 6. Update Run Row
    EventLogger.console_log(
        "Agent Orchestrator", "I am finalizing the run status in Supabase."
    )
    final_data = {
        "status": report["status"],
        "artifacts": uploaded_artifacts,
        "error": report.get("error"),
    }

    try:
        update_url = f"{sb_url}/rest/v1/runs?id=eq.{run_id}"
        headers["Content-Type"] = "application/json"
        if "x-upsert" in headers:
            del headers["x-upsert"]

        resp = httpx.patch(update_url, headers=headers, json=final_data)
        resp.raise_for_status()
    except Exception as e:
        EventLogger.console_log(
            "Agent Orchestrator", f"Failed to update run status: {str(e)}", "bold red"
        )

    EventLogger.console_log(
        "Agent Orchestrator",
        "Run complete. System is ready for evaluation.",
        "bold green",
    )
    return run_id

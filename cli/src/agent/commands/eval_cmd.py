import os
import typer
from rich.console import Console
import httpx
import json
from pathlib import Path
from agent.logger import EventLogger
from agent.dust_client import DustClient
from agent.supabase_auth import get_supabase_key

console = Console()


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


def _heuristic_evaluation(report: dict) -> dict:
    status = str(report.get("status", "")).lower()
    validation_errors = report.get("validation_errors") or []
    skill_id = str(report.get("skill_id") or "")
    created_invoice_id = report.get("created_invoice_id")

    expects_invoice_id = (
        "invoice" in skill_id and "extract" not in skill_id and "bulk" not in skill_id
    )

    if validation_errors:
        return {
            "decision": "failure",
            "failure_class": "validation_error",
            "reasons": [
                f"Run report contains {len(validation_errors)} validation errors."
            ],
            "patch": [],
            "source": "heuristic",
        }

    if expects_invoice_id and not created_invoice_id:
        return {
            "decision": "failure",
            "failure_class": "missing_created_record",
            "reasons": [
                "Invoice workflow finished without a created invoice id in run report."
            ],
            "patch": [],
            "source": "heuristic",
        }

    if status == "success":
        return {
            "decision": "success",
            "failure_class": None,
            "reasons": ["Run report status is success."],
            "patch": [],
            "source": "heuristic",
        }
    return {
        "decision": "failure",
        "failure_class": "runtime_error",
        "reasons": [str(report.get("error") or "Run report indicates failure.")],
        "patch": [],
        "source": "heuristic",
    }


def evaluate_run(run_id: str):
    """Evaluate a run using Dust.tt to identify failures and propose patches."""
    sb_url = os.getenv("SUPABASE_URL")
    sb_key = get_supabase_key()
    supabase_enabled = bool(sb_url and sb_key)

    EventLogger.console_log(
        "Agent Evaluator", f"Evaluating run '{run_id}' via Dust.tt..."
    )

    # 1. Fetch Run Report from Supabase
    headers = {"apikey": sb_key, "Authorization": f"Bearer {sb_key}"} if sb_key else {}
    report = None
    skill_spec = {}

    if supabase_enabled:
        try:
            response = httpx.get(
                f"{sb_url}/rest/v1/runs?id=eq.{run_id}", headers=headers, timeout=20.0
            )
            response.raise_for_status()
            rows = response.json()
            if rows:
                run_data = rows[0]
                artifacts = run_data.get("artifacts", {})
                report_path = artifacts.get("run_report_json")
                skill_id = run_data.get("skill_id")

                if report_path:
                    report_key = report_path.replace("artifacts/", "", 1)
                    report_url = f"{sb_url}/storage/v1/object/authenticated/artifacts/{report_key}"
                    report_resp = httpx.get(report_url, headers=headers, timeout=20.0)
                    report_resp.raise_for_status()
                    report = report_resp.json()

                if skill_id:
                    seed_path = Path(f"seeds/{skill_id}.json")
                    if seed_path.exists():
                        with open(seed_path, "r", encoding="utf-8") as f:
                            skill_spec = json.load(f)
        except Exception as e:
            EventLogger.console_log(
                "Agent Evaluator",
                f"Supabase fetch failed ({e}); falling back to local run report.",
                "bold yellow",
            )

    if report is None:
        local_report_path = Path(".state/artifacts") / run_id / "run_report.json"
        if not local_report_path.exists():
            console.print(
                f"[red]Error:[/red] Could not load run report for '{run_id}' from Supabase or {local_report_path}."
            )
            raise typer.Exit(1)
        with open(local_report_path, "r", encoding="utf-8") as f:
            report = json.load(f)
        EventLogger.console_log(
            "Agent Evaluator",
            f"Using local run report at {local_report_path}.",
            "bold yellow",
        )

    # 2. Call Dust.tt for evaluation
    try:
        dust = DustClient()
        eval_data = dust.evaluate_run(report, skill_spec)
        reasons = eval_data.get("reasons", [])
        if isinstance(reasons, str):
            reasons = [reasons]
        elif not isinstance(reasons, list):
            reasons = [str(reasons)]
        eval_data["reasons"] = reasons

        EventLogger.console_log(
            "Agent Evaluator",
            f"✓ Evaluation complete! Decision: [bold]{eval_data.get('decision')}[/bold]",
        )
        EventLogger.console_log("Agent Evaluator", f"Reasons: {', '.join(reasons)}")
    except Exception as e:
        EventLogger.console_log(
            "Agent Evaluator",
            f"Dust.tt evaluation unavailable ({e}); using heuristic evaluator.",
            "bold yellow",
        )
        eval_data = _heuristic_evaluation(report)

    eval_key = f"evals/{run_id}.json"
    local_eval_path = Path(".state/runs/evals") / f"{run_id}.json"
    local_eval_path.parent.mkdir(parents=True, exist_ok=True)
    with open(local_eval_path, "w", encoding="utf-8") as f:
        json.dump(eval_data, f, indent=2)

    EventLogger.console_log(
        "Agent Evaluator",
        f"✓ Evaluation saved locally: [bold]{local_eval_path}[/bold]",
    )

    if supabase_enabled:
        try:
            upload_headers = {
                "apikey": sb_key,
                "Authorization": f"Bearer {sb_key}",
                "Content-Type": "application/json",
                "x-upsert": "true",
            }
            upload_url = f"{sb_url}/storage/v1/object/artifacts/{eval_key}"
            httpx.post(
                upload_url,
                headers=upload_headers,
                content=json.dumps(eval_data),
                timeout=20.0,
            ).raise_for_status()

            httpx.patch(
                f"{sb_url}/rest/v1/runs?id=eq.{run_id}",
                headers={
                    "apikey": sb_key,
                    "Authorization": f"Bearer {sb_key}",
                    "Content-Type": "application/json",
                },
                json={"eval_key": eval_key},
                timeout=20.0,
            ).raise_for_status()

            EventLogger.console_log(
                "Agent Evaluator",
                f"✓ Evaluation saved to Supabase: [bold]{eval_key}[/bold]",
            )
        except Exception as e:
            EventLogger.console_log(
                "Agent Evaluator",
                f"Supabase sync skipped ({e}). Local evaluation is available.",
                "bold yellow",
            )

    EventLogger.log(
        "run_evaluated",
        f"Run ID: {run_id}",
        {"decision": eval_data.get("decision")},
    )
    return eval_data

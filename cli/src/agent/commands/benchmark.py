import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import typer
from rich.console import Console
from rich.table import Table

from agent.logger import EventLogger

console = Console()


def _load_run_report(run_id: str) -> Dict:
    path = Path(".state/artifacts") / run_id / "run_report.json"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def summarize_benchmark_results(
    skill_id: str,
    runs: List[Dict],
    started_at: str,
    ended_at: str,
) -> Dict:
    total = len(runs)
    success_count = sum(1 for r in runs if r.get("decision") == "success")
    failure_count = total - success_count
    success_rate = (success_count / total) if total else 0.0
    failure_classes = Counter(
        str(r.get("failure_class") or "unknown")
        for r in runs
        if r.get("decision") != "success"
    )

    return {
        "skill_id": skill_id,
        "started_at": started_at,
        "ended_at": ended_at,
        "total_runs": total,
        "success_count": success_count,
        "failure_count": failure_count,
        "success_rate": success_rate,
        "failure_classes": dict(failure_classes),
        "runs": runs,
    }


def run_benchmark(
    skill_id: str = typer.Argument(..., help="Skill ID to benchmark."),
    input_file: Optional[Path] = typer.Option(
        None,
        "--input-file",
        help="JSON file with slot values to use for every run.",
    ),
    runs: int = typer.Option(
        3,
        "--runs",
        min=1,
        max=20,
        help="How many executions to run.",
    ),
    min_success_rate: float = typer.Option(
        1.0,
        "--min-success-rate",
        min=0.0,
        max=1.0,
        help="Minimum success rate required for benchmark pass.",
    ),
    auto_patch: bool = typer.Option(
        False,
        "--auto-patch/--no-auto-patch",
        help="Apply patch automatically when evaluation fails with a non-empty patch.",
    ),
    stop_on_failure: bool = typer.Option(
        False,
        "--stop-on-failure/--no-stop-on-failure",
        help="Stop benchmark after first failed run.",
    ),
    headless: bool = typer.Option(
        True,
        "--headless/--headed",
        help="Force browser mode for benchmark runs.",
    ),
):
    """Run repeated execution/evaluation cycles and score skill reliability."""
    seed_path = Path(f"seeds/{skill_id}.json")
    if not seed_path.exists():
        console.print(f"[red]Error:[/red] skill seed not found: {seed_path}")
        raise typer.Exit(1)

    if input_file is not None and not input_file.exists():
        console.print(f"[red]Error:[/red] input file not found: {input_file}")
        raise typer.Exit(1)

    from agent.commands.eval_cmd import evaluate_run
    from agent.commands.patch import apply_patch
    from agent.commands.run_cmd import run_skill

    started_at = datetime.now(timezone.utc).isoformat()
    previous_headless = os.getenv("HEADLESS")
    os.environ["HEADLESS"] = "1" if headless else "0"
    EventLogger.console_log(
        "Agent Benchmark",
        f"Starting benchmark for [bold]{skill_id}[/bold] with {runs} run(s).",
        "bold magenta",
    )
    EventLogger.log("benchmark_started", f"Skill: {skill_id}", {"runs": runs})

    run_rows: List[Dict] = []
    try:
        for idx in range(1, runs + 1):
            EventLogger.console_log(
                "Agent Benchmark",
                f"Run {idx}/{runs}: executing skill...",
                "bold cyan",
            )
            run_id = run_skill(skill_id, input_file)
            eval_data = evaluate_run(run_id)
            report = _load_run_report(run_id)

            decision = str(eval_data.get("decision") or "failure")
            failure_class = eval_data.get("failure_class")
            run_rows.append(
                {
                    "iter": idx,
                    "run_id": run_id,
                    "decision": decision,
                    "failure_class": failure_class,
                    "final_url": report.get("final_url"),
                    "created_invoice_id": report.get("created_invoice_id"),
                    "validation_error_count": len(report.get("validation_errors") or []),
                    "status": report.get("status"),
                }
            )

            if (
                auto_patch
                and decision != "success"
                and isinstance(eval_data.get("patch"), list)
                and len(eval_data.get("patch")) > 0
            ):
                eval_key = f"evals/{run_id}.json"
                EventLogger.console_log(
                    "Agent Benchmark",
                    f"Applying auto-patch from {eval_key}...",
                    "bold yellow",
                )
                apply_patch(skill_id, eval_key)

            if stop_on_failure and decision != "success":
                EventLogger.console_log(
                    "Agent Benchmark",
                    "Stopping early due to failed run.",
                    "bold yellow",
                )
                break
    finally:
        if previous_headless is None:
            os.environ.pop("HEADLESS", None)
        else:
            os.environ["HEADLESS"] = previous_headless

    ended_at = datetime.now(timezone.utc).isoformat()
    summary = summarize_benchmark_results(skill_id, run_rows, started_at, ended_at)

    out_dir = Path(".state/benchmarks")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"{skill_id.replace('/', '_')}_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Iter")
    table.add_column("Run ID")
    table.add_column("Decision")
    table.add_column("Failure Class")
    table.add_column("Created ID")
    table.add_column("Validation Errors")
    for row in run_rows:
        decision_colored = (
            f"[green]{row['decision']}[/green]"
            if row["decision"] == "success"
            else f"[red]{row['decision']}[/red]"
        )
        table.add_row(
            str(row["iter"]),
            str(row["run_id"])[:8],
            decision_colored,
            str(row.get("failure_class") or ""),
            str(row.get("created_invoice_id") or ""),
            str(row.get("validation_error_count") or 0),
        )

    console.print(table)
    console.print(
        f"\n[bold]Success rate:[/bold] {summary['success_rate']:.2%} "
        f"({summary['success_count']}/{summary['total_runs']})"
    )
    console.print(f"[bold]Saved benchmark:[/bold] {out_path}")
    EventLogger.log(
        "benchmark_completed",
        f"Skill: {skill_id}",
        {
            "success_rate": summary["success_rate"],
            "total_runs": summary["total_runs"],
            "output": str(out_path),
        },
    )

    if summary["success_rate"] < min_success_rate:
        console.print(
            f"[red]Benchmark failed[/red]: success rate {summary['success_rate']:.2%} "
            f"< required {min_success_rate:.2%}"
        )
        raise typer.Exit(2)

    console.print("[green]Benchmark passed.[/green]")

import json
import os
import queue
import re
import shutil
import subprocess
import threading
from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer
from rich.console import Console
from rich.table import Table

from agent.logger import EventLogger

console = Console()
RUN_ID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


@dataclass
class SwarmTask:
    id: str
    prompt: Optional[str] = None
    skill_id: Optional[str] = None
    input_file: Optional[str] = None
    task_type: str = "ask"
    platform_id: str = "envoice"
    auto_acquire: bool = True
    learn: bool = True


class SwarmMode(str, Enum):
    learn = "learn"
    execute = "execute"


def _slug(value: str, limit: int = 32) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (s[:limit].strip("-") or "task")


def _normalize_tasks(tasks_payload: Any, *, default_prompt_task_type: str) -> List[SwarmTask]:
    if isinstance(tasks_payload, dict):
        tasks_raw = tasks_payload.get("tasks", [])
    elif isinstance(tasks_payload, list):
        tasks_raw = tasks_payload
    else:
        tasks_raw = []

    tasks: List[SwarmTask] = []
    for idx, raw in enumerate(tasks_raw, start=1):
        if not isinstance(raw, dict):
            continue
        task = SwarmTask(
            id=str(raw.get("id") or f"task_{idx}"),
            prompt=raw.get("prompt"),
            skill_id=raw.get("skill_id"),
            input_file=raw.get("input_file"),
            task_type=str(raw.get("task_type") or ""),
            platform_id=str(raw.get("platform_id") or "envoice"),
            auto_acquire=bool(raw.get("auto_acquire", True)),
            learn=bool(raw.get("learn", True)),
        )
        if not task.task_type:
            if task.prompt:
                task.task_type = default_prompt_task_type
            elif task.skill_id:
                task.task_type = "run"
            else:
                task.task_type = "ask"
        if task.prompt or task.skill_id:
            tasks.append(task)
    return tasks


def _load_tasks(
    tasks_file: Optional[Path], prompts: List[str], *, default_prompt_task_type: str
) -> List[SwarmTask]:
    tasks: List[SwarmTask] = []
    if tasks_file:
        if not tasks_file.exists():
            raise RuntimeError(f"Tasks file not found: {tasks_file}")
        with open(tasks_file, "r", encoding="utf-8") as f:
            payload = json.load(f)
        tasks.extend(
            _normalize_tasks(payload, default_prompt_task_type=default_prompt_task_type)
        )
    for idx, prompt in enumerate(prompts, start=1):
        tasks.append(
            SwarmTask(
                id=f"prompt_{idx}",
                prompt=prompt,
                task_type=default_prompt_task_type,
            )
        )
    return tasks


def _ensure_symlink(dst: Path, src: Path) -> None:
    if dst.exists() or dst.is_symlink():
        return
    dst.symlink_to(src.resolve(), target_is_directory=src.is_dir())


def _prepare_sandbox(
    repo_root: Path, sandbox_root: Path, worker_name: str, auth_name: str
) -> Path:
    sandbox = sandbox_root / worker_name
    sandbox.mkdir(parents=True, exist_ok=True)

    _ensure_symlink(sandbox / "seeds", repo_root / "seeds")
    _ensure_symlink(sandbox / "schemas", repo_root / "schemas")

    state_dir = sandbox / ".state"
    (state_dir / "auth").mkdir(parents=True, exist_ok=True)
    (state_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    (state_dir / "runs").mkdir(parents=True, exist_ok=True)
    (state_dir / "swarm").mkdir(parents=True, exist_ok=True)

    src_auth = repo_root / ".state" / "auth" / f"{auth_name}.json"
    dst_auth = state_dir / "auth" / f"{auth_name}.json"
    if src_auth.exists() and not dst_auth.exists():
        shutil.copy2(src_auth, dst_auth)
    return sandbox


def _command_for_task(task: SwarmTask) -> List[str]:
    if task.prompt and task.task_type in {"extrapolate", "learn"}:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        skill_id = f"{task.platform_id}.swarm.{_slug(task.id)}.{ts}"
        return [
            "agent",
            "extrapolate",
            task.prompt,
            "--platform-id",
            task.platform_id,
            "--skill-id",
            skill_id,
        ]

    if task.prompt and task.task_type in {"ask", "execute"}:
        cmd = [
            "agent",
            "ask",
            task.prompt,
            "--yes",
            "--platform-id",
            task.platform_id,
        ]
        cmd.append("--auto-acquire" if task.auto_acquire else "--no-auto-acquire")
        cmd.append("--learn" if task.learn else "--no-learn")
        return cmd

    if task.skill_id and task.task_type in {"run", "execute"}:
        cmd = ["agent", "run", task.skill_id]
        if task.input_file:
            cmd.append(task.input_file)
        return cmd
    if task.skill_id and task.task_type == "benchmark":
        cmd = [
            "agent",
            "benchmark",
            task.skill_id,
            "--runs",
            "1",
            "--stop-on-failure",
            "--headless",
        ]
        if task.input_file:
            cmd.extend(["--input-file", task.input_file])
        return cmd
    raise RuntimeError(
        f"Task '{task.id}' has unsupported task_type='{task.task_type}' or missing fields."
    )


def _run_task_in_sandbox(
    task: SwarmTask,
    sandbox: Path,
    *,
    headless: bool,
    timeout_seconds: int,
) -> Dict[str, Any]:
    cmd = _command_for_task(task)
    env = os.environ.copy()
    env["HEADLESS"] = "1" if headless else "0"
    started = datetime.now(timezone.utc).isoformat()
    proc = subprocess.run(
        cmd,
        cwd=str(sandbox),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    ended = datetime.now(timezone.utc).isoformat()
    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    run_ids = sorted(set(RUN_ID_RE.findall(output)))
    run_statuses: Dict[str, str] = {}
    for run_id in run_ids:
        report_path = sandbox / ".state" / "artifacts" / run_id / "run_report.json"
        if not report_path.exists():
            continue
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                run_statuses[run_id] = str((json.load(f) or {}).get("status") or "")
        except Exception:
            continue
    report_failed = any(
        status.lower() not in {"success", "succeeded"} for status in run_statuses.values()
    )
    task_ok = proc.returncode == 0 and not report_failed

    swarm_dir = sandbox / ".state" / "swarm"
    swarm_dir.mkdir(parents=True, exist_ok=True)
    log_path = swarm_dir / f"{task.id}.log"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(output)

    return {
        "task_id": task.id,
        "prompt": task.prompt,
        "skill_id": task.skill_id,
        "command": cmd,
        "sandbox": str(sandbox),
        "exit_code": proc.returncode,
        "task_ok": task_ok,
        "run_ids": run_ids,
        "run_statuses": run_statuses,
        "started_at": started,
        "ended_at": ended,
        "log_path": str(log_path),
    }


def run_swarm(
    tasks_file: Optional[Path] = typer.Option(
        None,
        "--tasks-file",
        help="Path to JSON tasks file. Format: {\"tasks\":[{\"id\":\"...\",\"prompt\":\"...\"}]}",
    ),
    prompt: List[str] = typer.Option(
        None,
        "--prompt",
        help="Inline prompt task (repeat --prompt for multiple tasks).",
    ),
    mode: SwarmMode = typer.Option(
        SwarmMode.learn,
        "--mode",
        case_sensitive=False,
        help="`learn`: generate skills only (no invoice execution). `execute`: run prompt tasks via agent ask.",
    ),
    workers: int = typer.Option(
        2,
        "--workers",
        min=1,
        max=20,
        help="Number of isolated sandbox workers.",
    ),
    sandbox_root: Path = typer.Option(
        Path(".sandboxes"),
        "--sandbox-root",
        help="Root directory for worker sandboxes.",
    ),
    headless: bool = typer.Option(
        True,
        "--headless/--headed",
        help="Run worker browser sessions headless or headed.",
    ),
    timeout_seconds: int = typer.Option(
        1800,
        "--timeout-seconds",
        min=60,
        max=7200,
        help="Per-task subprocess timeout.",
    ),
    auth_name: str = typer.Option(
        "envoice",
        "--auth-name",
        help="Auth state name to seed each sandbox from .state/auth/<name>.json",
    ),
):
    """Run prompt/skill tasks across isolated worker sandboxes."""
    prompts = prompt or []
    default_prompt_task_type = "extrapolate" if mode == SwarmMode.learn else "ask"
    tasks = _load_tasks(
        tasks_file, prompts, default_prompt_task_type=default_prompt_task_type
    )
    if not tasks:
        console.print(
            "[red]No tasks to run.[/red] Provide --tasks-file and/or --prompt entries."
        )
        raise typer.Exit(1)

    repo_root = Path.cwd()
    sandbox_root.mkdir(parents=True, exist_ok=True)

    worker_sandboxes: List[Path] = []
    for i in range(workers):
        worker_name = f"worker_{i + 1}"
        worker_sandboxes.append(
            _prepare_sandbox(repo_root, sandbox_root, worker_name, auth_name)
        )

    EventLogger.console_log(
        "Agent Swarm",
        f"Starting swarm with {workers} worker(s), {len(tasks)} task(s), mode={mode.value}.",
        "bold magenta",
    )

    q: queue.Queue[SwarmTask] = queue.Queue()
    for task in tasks:
        q.put(task)

    results: List[Dict[str, Any]] = []
    results_lock = threading.Lock()

    def _worker_loop(worker_idx: int) -> None:
        sandbox = worker_sandboxes[worker_idx]
        while True:
            try:
                task = q.get_nowait()
            except queue.Empty:
                return
            try:
                result = _run_task_in_sandbox(
                    task,
                    sandbox,
                    headless=headless,
                    timeout_seconds=timeout_seconds,
                )
            except Exception as exc:
                result = {
                    "task_id": task.id,
                    "prompt": task.prompt,
                    "skill_id": task.skill_id,
                    "sandbox": str(sandbox),
                    "exit_code": 1,
                    "run_ids": [],
                    "error": str(exc),
                }
            with results_lock:
                results.append(result)
            q.task_done()

    threads = [threading.Thread(target=_worker_loop, args=(i,)) for i in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    results = sorted(results, key=lambda x: str(x.get("task_id")))
    success_count = sum(1 for r in results if bool(r.get("task_ok")))
    failure_count = len(results) - success_count

    summary_table = Table(show_header=True, header_style="bold cyan")
    summary_table.add_column("Task")
    summary_table.add_column("Exit")
    summary_table.add_column("Run IDs")
    summary_table.add_column("Sandbox")
    summary_table.add_column("Log")
    for row in results:
        task_ok = bool(row.get("task_ok"))
        exit_code = int(row.get("exit_code", 1))
        exit_col = (
            f"[green]{exit_code}[/green]" if task_ok else f"[red]{exit_code}[/red]"
        )
        summary_table.add_row(
            str(row.get("task_id")),
            exit_col,
            ", ".join(row.get("run_ids") or [])[:120],
            Path(str(row.get("sandbox") or "")).name,
            str(row.get("log_path") or "-"),
        )
    console.print(summary_table)
    console.print(
        f"[bold]Swarm summary:[/bold] success={success_count} failed={failure_count} total={len(results)}"
    )

    out_dir = Path(".state/swarm")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"swarm_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "workers": workers,
                "tasks_total": len(tasks),
                "success_count": success_count,
                "failure_count": failure_count,
                "sandbox_root": str(sandbox_root),
                "results": results,
            },
            f,
            indent=2,
        )
    console.print(f"[green]Swarm report:[/green] {out_path}")
    EventLogger.log(
        "swarm_completed",
        "Swarm run completed",
        {
            "workers": workers,
            "tasks_total": len(tasks),
            "success_count": success_count,
            "failure_count": failure_count,
            "report_path": str(out_path),
        },
    )

    if failure_count > 0:
        raise typer.Exit(2)

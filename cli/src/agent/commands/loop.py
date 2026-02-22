import typer
from rich.console import Console
from rich.table import Table
import json
from pathlib import Path

from agent.logger import EventLogger
from agent.dust_client import DustClient
from agent.invoice_utils import parse_invoice_prompt

console = Console()


def run_loop(
    prompt: str = typer.Argument(
        ..., help="The natural language prompt to start the loop"
    ),
    iters: int = typer.Option(3, "--iters", help="Maximum number of iterations to run"),
):
    """Run the full route -> run -> eval -> patch loop for N iterations."""
    if iters < 1 or iters > 10:
        console.print("[red]Error:[/red] --iters must be between 1 and 10.")
        raise typer.Exit(1)

    EventLogger.console_log(
        "Agent Loop",
        f"Starting training loop for: [italic]{prompt}[/italic]",
        "bold magenta",
    )
    EventLogger.log("loop_started", prompt, {"iters": iters})

    try:
        EventLogger.console_log(
            "Agent Loop",
            "Step 1: Routing prompt to identify the correct skill via Dust.tt...",
        )

        try:
            dust = DustClient()
            route_data = dust.route_prompt(prompt)
        except Exception as route_exc:
            EventLogger.console_log(
                "Agent Loop",
                f"Dust routing unavailable ({route_exc}); using deterministic invoice fallback.",
                "bold yellow",
            )
            route_data = {
                "skill_id": "envoice.sales_invoice.existing",
                "slots": parse_invoice_prompt(prompt),
            }

        skill_id = route_data["skill_id"]
        slots = route_data.get("slots", {})
        if not isinstance(slots, dict):
            slots = {}
    except Exception as e:
        EventLogger.console_log("Agent Loop", f"Routing failed: {str(e)}", "bold red")
        raise typer.Exit(1)

    EventLogger.console_log(
        "Agent Loop",
        f"I've identified skill [bold]{skill_id}[/bold]. Starting iterations...",
    )

    history = []

    for i in range(iters):
        EventLogger.console_log(
            "Agent Loop", f"Iteration {i + 1}/{iters}", "bold magenta"
        )

        # 2. Run
        EventLogger.console_log("Agent Loop", "Step 2: Executing browser automation...")
        temp_input = Path(".state/temp_slots.json")
        temp_input.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_input, "w") as f:
            json.dump(slots, f)

        from agent.commands.run_cmd import run_skill
        from agent.commands.eval_cmd import evaluate_run
        from agent.commands.patch import apply_patch

        try:
            run_id = run_skill(skill_id, temp_input)
        except Exception as e:
            EventLogger.console_log("Agent Loop", f"Run failed: {str(e)}", "bold red")
            break

        # 3. Eval
        try:
            EventLogger.console_log(
                "Agent Loop", "Step 3: Evaluating run results via Dust.tt/Gemini..."
            )
            eval_data = evaluate_run(run_id)

            history.append(
                {
                    "iter": i + 1,
                    "run_id": run_id,
                    "decision": eval_data.get("decision"),
                    "failure_class": eval_data.get("failure_class"),
                }
            )

            if eval_data.get("decision") == "success":
                EventLogger.console_log(
                    "Agent Loop",
                    "Goal achieved! The skill is now perfected.",
                    "bold green",
                )
                EventLogger.log("loop_success", f"Skill {skill_id} perfected.")
                break

            # 4. Patch
            EventLogger.console_log(
                "Agent Loop", "Step 4: Applying self-healing patch to the skill..."
            )
            eval_key = f"evals/{run_id}.json"
            apply_patch(skill_id, eval_key)
            EventLogger.log(
                "skill_patched", f"Skill {skill_id} patched.", {"run_id": run_id}
            )
        except Exception as e:
            EventLogger.console_log(
                "Agent Loop", f"Evaluation/Patching failed: {str(e)}", "bold red"
            )
            break

    # Final Summary
    if history:
        console.print("\n[bold magenta]Training Loop Summary[/bold magenta]")
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Iter")
        table.add_column("Run ID")
        table.add_column("Decision")
        table.add_column("Failure Class")

        for h in history:
            table.add_row(
                str(h["iter"]),
                h["run_id"][:8],
                f"[green]{h['decision']}[/green]"
                if h["decision"] == "success"
                else f"[red]{h['decision']}[/red]",
                str(h["failure_class"]),
            )

        console.print(table)

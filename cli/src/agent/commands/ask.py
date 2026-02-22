import json
import typer
from pathlib import Path
from rich.console import Console
from typing import Optional

from agent.commands.run_cmd import run_skill
from agent.dust_client import DustClient
from agent.invoice_utils import parse_invoice_prompt, validate_vat_id
from agent.logger import EventLogger
from agent.scheduler import frequencies_for_period, save_recurring_job
from agent.skill_acquisition import synthesize_skill_for_prompt

console = Console()


def ask(
    prompt: str,
    platform_id: str = typer.Option(
        "envoice",
        "--platform-id",
        help="Platform memory identifier used for skill acquisition.",
    ),
    agent_id: str = typer.Option(
        "gemini-pro",
        "--agent-id",
        help="Dust assistant configuration ID.",
    ),
    auto_acquire: bool = typer.Option(
        True,
        "--auto-acquire/--no-auto-acquire",
        help="Synthesize a new skill from platform memory if routing has no usable skill.",
    ),
    learn: bool = typer.Option(
        True,
        "--learn/--no-learn",
        help="Run evaluate+patch after execution for one-step auto-heal.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Execute immediately without interactive confirmation.",
    ),
):
    """Ask the agent to perform a task using natural language."""
    EventLogger.console_log(
        "Agent Router", f"I've received your request: [italic]{prompt}[/italic]"
    )
    EventLogger.log("user_prompt", prompt)

    try:
        EventLogger.console_log(
            "Agent Router",
            "I am analyzing the request to find the right skill via Dust.tt...",
        )

        try:
            dust = DustClient()
            route_data = dust.route_prompt(prompt)
        except Exception as route_exc:
            EventLogger.console_log(
                "Agent Router",
                f"Dust routing unavailable ({route_exc}); using deterministic invoice fallback.",
                "bold yellow",
            )
            route_data = {
                "skill_id": "envoice.sales_invoice.existing",
                "slots": parse_invoice_prompt(prompt),
                "confidence": 0.4,
            }

        skill_id: Optional[str] = route_data.get("skill_id")
        slots = route_data.get("slots", {})
        if not isinstance(slots, dict):
            slots = {}

        deterministic_slots = parse_invoice_prompt(prompt)
        for key, value in deterministic_slots.items():
            # Trust deterministic extraction for canonical invoice fields.
            if key in {"amount", "currency", "period", "tax_rule", "vat_id"}:
                slots[key] = value
            else:
                slots.setdefault(key, value)

        vat_id = slots.get("vat_id")
        if vat_id:
            EventLogger.console_log(
                "Agent Router", f"Checking VAT ID via VIES endpoint network: {vat_id}"
            )
            vat_result = validate_vat_id(str(vat_id))
            slots["vat_check"] = vat_result
            EventLogger.log("vat_check", f"VAT result for {vat_id}", vat_result)

        seed_exists = bool(skill_id and Path(f"seeds/{skill_id}.json").exists())
        if (not skill_id or not seed_exists) and auto_acquire:
            EventLogger.console_log(
                "Agent Router",
                "No usable routed skill found. Starting multi-agent skill acquisition from platform memory...",
                "bold yellow",
            )
            acquired = synthesize_skill_for_prompt(
                prompt=prompt,
                platform_id=platform_id,
                agent_id=agent_id,
                preferred_skill_id=skill_id if skill_id and not seed_exists else None,
            )
            skill_id = acquired["skill_id"]
            EventLogger.console_log(
                "Agent Router",
                f"✓ Acquired new skill [bold]{skill_id}[/bold] at {acquired['seed_path']}",
                "bold green",
            )
            EventLogger.log(
                "skill_acquired_from_prompt",
                f"Skill: {skill_id}",
                {"prompt": prompt, "seed_path": acquired["seed_path"]},
            )

        if not skill_id:
            EventLogger.console_log(
                "Agent Router",
                "I couldn't identify or acquire a skill for this request.",
                "bold red",
            )
            raise typer.Exit(1)

        EventLogger.console_log(
            "Agent Router",
            f"I've identified the skill [bold]{skill_id}[/bold] with parameters: {json.dumps(slots)}",
        )
        EventLogger.log("route_identified", f"Skill: {skill_id}", {"slots": slots})

        # 2. Execute the identified skill
        confirm = yes
        if not yes:
            try:
                confirm = typer.confirm("\nProceed with execution?")
            except Exception:
                EventLogger.console_log(
                    "Agent Router",
                    "No interactive input available; re-run with --yes to execute automatically.",
                    "bold yellow",
                )
                confirm = False

        if confirm:
            temp_input = Path(".state/temp_slots.json")
            temp_input.parent.mkdir(parents=True, exist_ok=True)
            with open(temp_input, "w") as f:
                json.dump(slots, f)

            run_id = run_skill(skill_id, temp_input)

            if learn:
                try:
                    from agent.commands.eval_cmd import evaluate_run
                    from agent.commands.patch import apply_patch

                    eval_data = evaluate_run(run_id)
                    if (
                        eval_data.get("decision") == "failure"
                        and isinstance(eval_data.get("patch"), list)
                        and len(eval_data.get("patch")) > 0
                    ):
                        eval_key = f"evals/{run_id}.json"
                        EventLogger.console_log(
                            "Agent Router",
                            f"Applying auto-heal patch from {eval_key}...",
                            "bold yellow",
                        )
                        apply_patch(skill_id, eval_key)
                        EventLogger.log(
                            "skill_auto_patched",
                            f"Auto-patched {skill_id}",
                            {"run_id": run_id, "eval_key": eval_key},
                        )
                except Exception as learn_exc:
                    EventLogger.console_log(
                        "Agent Router",
                        f"Learning pass skipped ({learn_exc})",
                        "bold yellow",
                    )

            period = str(slots.get("period", "")).lower()
            schedule_frequencies = frequencies_for_period(period)
            if schedule_frequencies:
                created_paths = []
                for frequency in schedule_frequencies:
                    job_path = save_recurring_job(skill_id, prompt, slots, frequency)
                    created_paths.append(str(job_path))
                readable = ", ".join(schedule_frequencies)
                EventLogger.console_log(
                    "Agent Router",
                    f"Recurring schedules created ([bold]{readable}[/bold]): {', '.join(created_paths)}",
                    "bold green",
                )
                EventLogger.log(
                    "recurrence_scheduled",
                    f"{period} schedule for {skill_id}",
                    {"job_paths": created_paths},
                )
        else:
            EventLogger.console_log(
                "Agent Router", "Execution cancelled by user.", "bold yellow"
            )

    except Exception as e:
        EventLogger.console_log(
            "Agent Router",
            f"I encountered an error during routing: {str(e)}",
            "bold red",
        )
        raise typer.Exit(1)

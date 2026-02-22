import json
import os
from pathlib import Path
import typer
import time
from rich.console import Console
from playwright.sync_api import sync_playwright
from jsonschema import ValidationError, validate
from agent.logger import EventLogger
from agent.dust_client import DustClient
from agent.platform_memory import (
    load_platform_map,
    merge_platform_signals,
    platform_map_digest,
    save_platform_map,
)
from agent.trace_mining import (
    build_trace_summary,
    infer_skill_from_events,
    install_user_interaction_recorder,
    parse_trace_zip_actions,
)
from agent.seed_sync import sync_seed_to_supabase
from agent.skill_spec_utils import normalize_skill_spec

console = Console()


def mine_workflow(
    name: str,
    platform_id: str = typer.Option(
        "envoice",
        "--platform-id",
        help="Logical platform identifier for persistent platform memory.",
    ),
    agent_id: str = typer.Option(
        "gemini-pro",
        "--agent-id",
        help="Dust assistant configuration ID for multi-agent mining steps.",
    ),
    max_minutes: int = typer.Option(
        15,
        "--max-minutes",
        min=1,
        max=60,
        help="Safety timeout for manual recording window.",
    ),
    headless: bool = typer.Option(
        os.getenv("HEADLESS", "1") == "1",
        "--headless/--headed",
        help="Run miner browser headless or headed.",
    ),
):
    """Record a manual workflow and use Gemini/Dust.tt to mine a SkillSpec."""
    base_url = os.getenv("ENVOICE_BASE_URL", "https://app.envoice.eu")
    auth_path = Path(".state/auth/envoice.json")
    interaction_events = []
    trace_path = Path(".state/artifacts") / f"mine_{name}.zip"

    EventLogger.console_log(
        "Agent Miner", f"Starting Workflow Mining: [bold]{name}[/bold]", "bold magenta"
    )
    EventLogger.console_log(
        "Agent Miner", "I will record your manual actions to generate a SkillSpec..."
    )

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context_kwargs = {}
            if auth_path.exists():
                context_kwargs["storage_state"] = str(auth_path)

            context = browser.new_context(**context_kwargs)
            install_user_interaction_recorder(context, interaction_events)
            page = context.new_page()

            # Start tracing to capture actions
            context.tracing.start(screenshots=True, snapshots=True, sources=True)

            page.goto(base_url)

            if headless:
                console.print(
                    "\n[yellow]Headless mode active: capturing a short automated trace window.[/yellow]"
                )
                page.wait_for_timeout(3000)
            else:
                console.print(
                    "\n[yellow]Perform the actions you want to mine into a skill.[/yellow]"
                )
                console.print(
                    f"[yellow]Close the browser window when finished (auto-timeout in {max_minutes} min).[/yellow]"
                )

                # Keep alive until closed or timeout.
                deadline = time.time() + max_minutes * 60
                while browser.is_connected() and time.time() < deadline:
                    try:
                        page.wait_for_timeout(1000)
                    except Exception:
                        break

            # Stop tracing and save
            trace_path.parent.mkdir(parents=True, exist_ok=True)
            context.tracing.stop(path=str(trace_path))

            if browser.is_connected():
                EventLogger.console_log(
                    "Agent Miner",
                    f"Recording window completed; closing browser (max {max_minutes} min).",
                    "bold yellow",
                )
                browser.close()
    except Exception as e:
        error_text = str(e).strip()
        error_summary = error_text.splitlines()[0] if error_text else type(e).__name__
        EventLogger.console_log(
            "Agent Miner",
            f"Browser recording failed: {error_summary}",
            "bold red",
        )
        raise typer.Exit(1)

    trace_events = parse_trace_zip_actions(trace_path)
    combined_events = interaction_events if interaction_events else trace_events
    trace_summary = build_trace_summary(interaction_events, trace_events)

    EventLogger.console_log(
        "Agent Miner",
        f"Captured {len(interaction_events)} user events and {len(trace_events)} trace API events.",
    )
    EventLogger.console_log(
        "Agent Miner", "Running multi-agent mining chain: mapper -> planner -> writer -> critic..."
    )

    try:
        dust = DustClient()
        platform_map = load_platform_map(platform_id)
        digest = platform_map_digest(platform_map)

        mined = dust.multi_agent_mine_workflow(
            skill_id=name,
            base_url=base_url,
            trace_summary=trace_summary,
            interaction_events=combined_events,
            platform_map_digest=digest,
            agent_id=agent_id,
        )
        skill_spec = mined.get("skill_spec") or {}
        if not isinstance(skill_spec, dict) or not skill_spec.get("steps"):
            raise RuntimeError("Multi-agent mining returned empty skill spec.")
        skill_spec = normalize_skill_spec(
            skill_spec,
            default_id=name,
            default_base_url=base_url,
        )
    except Exception as e:
        EventLogger.console_log(
            "Agent Miner",
            f"Multi-agent mining unavailable ({e}); using deterministic event parser fallback.",
            "bold yellow",
        )
        skill_spec = infer_skill_from_events(name, base_url, combined_events)
        mined = {
            "platform_mapper": {"fallback": True},
            "workflow_planner": {"fallback": True},
            "skill_writer": {"fallback": True},
            "skill_critic": {"fallback": True},
        }

    skill_spec = normalize_skill_spec(
        skill_spec,
        default_id=name,
        default_base_url=base_url,
    )
    if not skill_spec.get("steps"):
        skill_spec = infer_skill_from_events(name, base_url, combined_events)

    # Validate skill before persisting.
    try:
        schema_path = Path("schemas/SkillSpec.schema.json")
        if schema_path.exists():
            with open(schema_path, "r", encoding="utf-8") as sf:
                skill_schema = json.load(sf)
            validate(instance=skill_spec, schema=skill_schema)
    except ValidationError as ve:
        EventLogger.console_log(
            "Agent Miner",
            f"Generated skill failed schema validation ({ve.message}); using deterministic fallback.",
            "bold yellow",
        )
        skill_spec = infer_skill_from_events(name, base_url, combined_events)

    try:
        # Save to seeds
        seed_path = Path(f"seeds/{name}.json")
        with open(seed_path, "w", encoding="utf-8") as f:
            json.dump(skill_spec, f, indent=2)
        try:
            storage_key = sync_seed_to_supabase(name, seed_path, source="mine")
            if storage_key:
                EventLogger.console_log(
                    "Agent Miner",
                    f"✓ Seed synced to Supabase: [bold]{storage_key}[/bold]",
                )
        except Exception as sync_exc:
            EventLogger.console_log(
                "Agent Miner",
                f"Seed sync skipped ({sync_exc})",
                "bold yellow",
            )

        # Persist platform memory incrementally.
        platform_map = load_platform_map(platform_id)
        platform_map = merge_platform_signals(
            platform_map=platform_map,
            base_url=base_url,
            interaction_events=combined_events,
            skill_id=name,
            source="mine",
        )
        map_path = save_platform_map(platform_id, platform_map)

        mine_report = Path(".state/artifacts") / f"mine_{name}.json"
        with open(mine_report, "w", encoding="utf-8") as rf:
            json.dump(
                {
                    "skill_id": name,
                    "platform_id": platform_id,
                    "trace_zip": str(trace_path),
                    "events_captured": len(interaction_events),
                    "trace_events_captured": len(trace_events),
                    "platform_map_path": str(map_path),
                    "multi_agent_outputs": mined,
                    "trace_summary": trace_summary,
                },
                rf,
                indent=2,
            )

        EventLogger.console_log(
            "Agent Miner",
            f"✓ SkillSpec generated and saved to [bold]{seed_path}[/bold]",
        )
        EventLogger.console_log(
            "Agent Miner",
            f"✓ Platform memory updated: [bold]{map_path}[/bold]",
        )
        EventLogger.log("skill_mined", f"Skill: {name}", {"seed_path": str(seed_path)})

    except Exception as e:
        EventLogger.console_log("Agent Miner", f"✗ Mining failed: {str(e)}", "bold red")
        raise typer.Exit(1)

    EventLogger.console_log(
        "Agent Miner",
        "Workflow mining complete! You can now run this skill.",
        "bold green",
    )

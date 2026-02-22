import os
import json
import typer
from pathlib import Path
from typing import Optional, Dict, Any, List
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.prompt import Prompt
from dotenv import load_dotenv
import httpx

from agent.dust_client import DustClient
from agent.logger import EventLogger
from agent.supabase_auth import get_supabase_key

console = Console()

SKILLS_DIR = Path("seeds")


# ---------------------------------------------------------------------------
# Supabase thread persistence
# ---------------------------------------------------------------------------


def _sb_headers() -> Dict[str, str]:
    key = get_supabase_key()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _sb_url() -> str:
    return os.getenv("SUPABASE_URL", "")


def create_thread(dust_conversation_id: str, title: str) -> Dict[str, Any]:
    """Insert a new thread row and return it (with UUID)."""
    payload = {
        "dust_conversation_id": dust_conversation_id,
        "title": title,
        "turn_count": 0,
    }
    resp = httpx.post(
        f"{_sb_url()}/rest/v1/threads",
        headers=_sb_headers(),
        json=payload,
        timeout=10.0,
    )
    rows = resp.json()
    return rows[0] if isinstance(rows, list) and rows else rows


def update_thread_turn(thread_id: str, turn: int):
    httpx.patch(
        f"{_sb_url()}/rest/v1/threads?id=eq.{thread_id}",
        headers=_sb_headers(),
        json={"turn_count": turn, "updated_at": "now()"},
        timeout=10.0,
    )


def save_message(
    thread_id: str, role: str, content: str, metadata: Dict[str, Any] = None
):
    httpx.post(
        f"{_sb_url()}/rest/v1/thread_messages",
        headers=_sb_headers(),
        json={
            "thread_id": thread_id,
            "role": role,
            "content": content,
            "metadata": metadata or {},
        },
        timeout=10.0,
    )


def get_latest_thread() -> Optional[Dict[str, Any]]:
    """Fetch the most recently updated thread."""
    resp = httpx.get(
        f"{_sb_url()}/rest/v1/threads?order=updated_at.desc&limit=1",
        headers=_sb_headers(),
        timeout=10.0,
    )
    rows = resp.json()
    return rows[0] if isinstance(rows, list) and rows else None


def list_threads(limit: int = 10) -> List[Dict[str, Any]]:
    resp = httpx.get(
        f"{_sb_url()}/rest/v1/threads?order=updated_at.desc&limit={limit}",
        headers=_sb_headers(),
        timeout=10.0,
    )
    rows = resp.json()
    return rows if isinstance(rows, list) else []


def get_thread_by_id(thread_id: str) -> Optional[Dict[str, Any]]:
    resp = httpx.get(
        f"{_sb_url()}/rest/v1/threads?id=eq.{thread_id}",
        headers=_sb_headers(),
        timeout=10.0,
    )
    rows = resp.json()
    return rows[0] if isinstance(rows, list) and rows else None


def get_thread_messages(thread_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    resp = httpx.get(
        f"{_sb_url()}/rest/v1/thread_messages?thread_id=eq.{thread_id}&order=created_at.asc&limit={limit}",
        headers=_sb_headers(),
        timeout=10.0,
    )
    rows = resp.json()
    return rows if isinstance(rows, list) else []


# ---------------------------------------------------------------------------
# Skills context builder
# ---------------------------------------------------------------------------


def _load_skills_context() -> str:
    skills = []
    if SKILLS_DIR.exists():
        for f in sorted(SKILLS_DIR.glob("envoice.*.json")):
            try:
                spec = json.loads(f.read_text())
                slot_keys = list(
                    spec.get("slots_schema", {}).get("properties", {}).keys()
                )
                skills.append(
                    f"- **{spec['id']}** v{spec.get('version', 1)}: "
                    f"{spec.get('description', spec.get('name', ''))} "
                    f"[slots: {', '.join(slot_keys)}]"
                )
            except Exception:
                continue
    return "\n".join(skills) if skills else "(no skills loaded)"


SYSTEM_PROMPT = """You are the Invoice 1-Shot Agent assistant. You help users understand, create, modify, and execute Envoice automation skills.

You have deep knowledge of:
1. The Envoice platform (app.envoice.eu) — its Select2 dropdowns, invoice forms, tax rules, customer management.
2. The SkillSpec format — JSON files with steps (goto, click, fill, select2, select2_tax, fill_date, handle_cookies, wait, screenshot, evaluate, check_validation).
3. The agent's capabilities: `agent ask`, `agent run`, `agent loop`, `agent mine`, `agent eval`, `agent patch`.

Current skills available:
{skills}

When the user asks to create or modify a skill, output the full SkillSpec JSON.
When the user asks to run something, tell them the exact CLI command.
When the user asks about Envoice UI, reference real selectors and DOM patterns.
Be concise and actionable. You are a power-user copilot, not a tutorial."""


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


def start_chat(
    new: bool = typer.Option(False, "--new", help="Start a fresh conversation thread"),
    resume: Optional[str] = typer.Option(
        None, "--resume", help="Resume a thread by UUID"
    ),
    history: bool = typer.Option(False, "--history", help="List recent threads"),
):
    """Interactive chat with the agent about skills, Envoice, and automation."""
    load_dotenv(Path(__file__).parents[4] / ".env")

    if not _sb_url() or not get_supabase_key():
        console.print(
            "[red]SUPABASE_URL and a Supabase key are required for chat persistence.[/red]"
        )
        raise typer.Exit(1)

    # /history mode
    if history:
        _show_history()
        return

    skills_ctx = _load_skills_context()
    system = SYSTEM_PROMPT.format(skills=skills_ctx)

    # Determine which thread to use
    thread_row = None
    if resume:
        thread_row = get_thread_by_id(resume)
        if not thread_row:
            console.print(f"[red]Thread {resume} not found.[/red]")
            raise typer.Exit(1)
    elif not new:
        thread_row = get_latest_thread()

    console.print(
        Panel(
            "[bold]Invoice 1-Shot Agent Chat[/bold]\n"
            "Talk to the agent about your skills, ask it to create new ones,\n"
            "or get help with Envoice automation.\n\n"
            "[dim]Commands:  /new  |  /skills  |  /history  |  /run <cmd>  |  /quit[/dim]",
            border_style="cyan",
        )
    )

    if thread_row:
        tid = thread_row["id"]
        console.print(
            f"[dim]Resuming thread [bold]{tid[:8]}[/bold] ({thread_row.get('title', '—')})[/dim]"
        )
        # Show last few messages for context
        msgs = get_thread_messages(tid, limit=6)
        if msgs:
            console.print("[dim]Recent context:[/dim]")
            for m in msgs[-4:]:
                role_style = "green" if m["role"] == "user" else "cyan"
                snippet = (
                    (m["content"][:120] + "…")
                    if len(m["content"]) > 120
                    else m["content"]
                )
                console.print(f"  [{role_style}]{m['role']}[/{role_style}]: {snippet}")
            console.print()
    else:
        console.print("[dim]Starting new thread…[/dim]\n")

    try:
        dust = DustClient()
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    conversation_id = thread_row["dust_conversation_id"] if thread_row else None
    thread_id = thread_row["id"] if thread_row else None
    turn = thread_row.get("turn_count", 0) if thread_row else 0

    while True:
        try:
            user_input = Prompt.ask("[bold green]you[/bold green]")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        if not user_input.strip():
            continue

        cmd = user_input.strip()

        if cmd == "/quit":
            console.print("[dim]Goodbye.[/dim]")
            break

        if cmd == "/new":
            conversation_id = None
            thread_id = None
            turn = 0
            console.print(
                "[cyan]Thread reset. Next message starts a new thread.[/cyan]\n"
            )
            continue

        if cmd == "/skills":
            console.print(
                Panel(
                    Markdown(_load_skills_context()),
                    title="Available Skills",
                    border_style="blue",
                )
            )
            continue

        if cmd == "/history":
            _show_history()
            continue

        if cmd.startswith("/run "):
            os.system(cmd[5:])
            continue

        # Build message content
        if turn == 0 and not conversation_id:
            content = f"{system}\n\n---\n\nUser: {user_input}"
        else:
            content = user_input

        EventLogger.log(
            "chat_message", f"User: {user_input[:100]}", {"thread_id": thread_id}
        )

        with console.status("[cyan]Agent is thinking…[/cyan]"):
            try:
                if conversation_id:
                    result = dust.reply_in_thread(conversation_id, content)
                else:
                    result = dust.create_conversation(
                        content, title=f"Chat: {user_input[:30]}"
                    )
                    conversation_id = result["conversation_id"]
                    # Create a new thread in Supabase
                    thread_row = create_thread(
                        dust_conversation_id=conversation_id,
                        title=user_input[:80],
                    )
                    thread_id = thread_row["id"]
                    console.print(f"[dim]Thread created: {thread_id}[/dim]")

                agent_reply = result.get("message", "")
                turn += 1

                # Persist to Supabase
                if thread_id:
                    save_message(thread_id, "user", user_input)
                    save_message(
                        thread_id,
                        "agent",
                        agent_reply,
                        {"dust_conversation_id": conversation_id},
                    )
                    update_thread_turn(thread_id, turn)

            except Exception as e:
                console.print(f"\n[red]Error: {e}[/red]\n")
                continue

        console.print()
        console.print(
            Panel(
                Markdown(agent_reply),
                title="[bold cyan]agent[/bold cyan]",
                border_style="cyan",
            )
        )
        console.print()

        EventLogger.log(
            "chat_reply",
            f"Agent replied ({len(agent_reply)} chars)",
            {"thread_id": thread_id, "conversation_id": conversation_id},
        )


def _show_history():
    """Display recent threads from Supabase."""
    threads = list_threads(limit=15)
    if not threads:
        console.print("[dim]No threads found.[/dim]")
        return

    table = Table(title="Recent Chat Threads", border_style="cyan")
    table.add_column("UUID", style="bold", max_width=36)
    table.add_column("Title", max_width=50)
    table.add_column("Turns", justify="right")
    table.add_column("Updated", max_width=20)

    for t in threads:
        table.add_row(
            t["id"],
            (t.get("title") or "—")[:50],
            str(t.get("turn_count", 0)),
            (t.get("updated_at") or "")[:19],
        )

    console.print(table)
    console.print("[dim]Resume with: agent chat --resume <UUID>[/dim]")

import os
import httpx
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv
from agent.supabase_auth import get_supabase_key


# Find .env in the workspace root
def load_env_robust():
    current = Path.cwd()
    for _ in range(5):
        env_path = current / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=env_path)
            return env_path
        current = current.parent
    return None


load_env_robust()


class EventLogger:
    @staticmethod
    def log(event_type: str, details: str, metadata: Dict[str, Any] = None):
        """Log a system event to Supabase for QA and audit trail."""
        sb_url = os.getenv("SUPABASE_URL")
        sb_key = get_supabase_key()

        if not sb_url or not sb_key:
            return

        headers = {
            "apikey": sb_key,
            "Authorization": f"Bearer {sb_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "event_type": event_type,
            "details": details,
            "metadata": metadata or {},
        }

        try:
            # Check if events table exists, if not this will just fail silently
            httpx.post(
                f"{sb_url}/rest/v1/events", headers=headers, json=payload, timeout=5.0
            )
        except Exception:
            pass

    @staticmethod
    def console_log(agent_name: str, message: str, style: str = "bold cyan"):
        """Print a formatted log to the console."""
        from rich.console import Console

        console = Console()
        console.print(f"[{style}]{agent_name}:[/{style}] {message}")

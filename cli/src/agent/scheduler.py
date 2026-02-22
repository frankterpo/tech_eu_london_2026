import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def _add_months(dt: datetime, months: int) -> datetime:
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    # Use day 1 for predictable billing schedules.
    return dt.replace(year=year, month=month, day=1)


def compute_next_run(frequency: str, now: Optional[datetime] = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    anchor = now.replace(minute=0, second=0, microsecond=0)

    if frequency == "weekly":
        return anchor + timedelta(days=7)
    if frequency == "monthly":
        return _add_months(anchor, 1)
    if frequency == "quarterly":
        return _add_months(anchor, 3)
    if frequency == "annual":
        return _add_months(anchor, 12)
    return anchor


def cron_for_frequency(frequency: str) -> Optional[str]:
    if frequency == "weekly":
        return "0 9 * * 1"
    if frequency == "monthly":
        return "0 9 1 * *"
    if frequency == "quarterly":
        return "0 9 1 */3 *"
    if frequency == "annual":
        return "0 9 1 1 *"
    return None


def frequencies_for_period(period: str) -> list[str]:
    normalized = (period or "").strip().lower()
    if normalized == "monthly":
        # Monthly invoices should also prime adjacent cadences for learning/orchestration.
        return ["weekly", "monthly", "quarterly", "annual"]
    if normalized in {"weekly", "quarterly", "annual"}:
        return [normalized]
    return []


def save_recurring_job(
    skill_id: str,
    prompt: str,
    slots: Dict[str, Any],
    frequency: str,
) -> Path:
    next_run = compute_next_run(frequency)
    cron = cron_for_frequency(frequency)

    job = {
        "skill_id": skill_id,
        "prompt": prompt,
        "frequency": frequency,
        "slots": slots,
        "next_run_at": next_run.isoformat(),
        "cron_utc": cron,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    jobs_dir = Path(".state/runs/schedules")
    jobs_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    filename = f"{timestamp}_{skill_id.replace('.', '_')}_{frequency.lower()}.json"
    path = jobs_dir / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(job, f, indent=2)
    return path

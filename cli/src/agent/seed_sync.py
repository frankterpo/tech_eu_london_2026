import os
import json
from pathlib import Path
from typing import Optional

import httpx

from agent.supabase_auth import get_supabase_key


def _seed_storage_path(skill_id: str) -> str:
    safe_id = skill_id.strip().replace("/", "__")
    return f"artifacts/seeds/{safe_id}.json"


def _upsert_skill_row(
    sb_url: str,
    sb_key: str,
    *,
    skill_id: str,
    seed_path: Path,
) -> None:
    with open(seed_path, "r", encoding="utf-8") as f:
        spec = json.load(f)

    sid = str(spec.get("id") or skill_id)
    version = int(spec.get("version") or 1)
    payload = {"id": sid, "version": version, "spec": spec}
    headers = {
        "apikey": sb_key,
        "Authorization": f"Bearer {sb_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    resp = httpx.post(f"{sb_url}/rest/v1/skills", headers=headers, json=payload, timeout=20.0)
    resp.raise_for_status()


def sync_seed_to_supabase(
    skill_id: str,
    seed_path: Path,
    *,
    source: str = "unknown",
) -> Optional[str]:
    sb_url = os.getenv("SUPABASE_URL")
    sb_key = get_supabase_key()
    if not sb_url or not sb_key:
        return None
    if not seed_path.exists():
        return None

    storage_path = _seed_storage_path(skill_id)
    upload_url = f"{sb_url}/storage/v1/object/{storage_path}"
    headers = {
        "apikey": sb_key,
        "Authorization": f"Bearer {sb_key}",
        "Content-Type": "application/json",
        "x-upsert": "true",
        "x-seed-source": source,
    }
    with open(seed_path, "rb") as f:
        body = f.read()

    resp = httpx.post(upload_url, headers=headers, content=body, timeout=20.0)
    resp.raise_for_status()
    _upsert_skill_row(sb_url, sb_key, skill_id=skill_id, seed_path=seed_path)
    return storage_path

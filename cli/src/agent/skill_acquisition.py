import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from jsonschema import ValidationError, validate

from agent.dust_client import DustClient
from agent.platform_memory import (
    load_platform_map,
    merge_platform_signals,
    platform_map_digest,
    save_platform_map,
)


def _slugify(text: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if not slug:
        slug = "generated"
    return slug[:max_len].strip("-") or "generated"


def _existing_skill_ids() -> List[str]:
    seed_dir = Path("seeds")
    if not seed_dir.exists():
        return []
    return sorted(path.stem for path in seed_dir.glob("*.json"))


def _load_skill_schema() -> Optional[Dict[str, Any]]:
    schema_path = Path("schemas/SkillSpec.schema.json")
    if not schema_path.exists():
        return None
    with open(schema_path, "r", encoding="utf-8") as sf:
        return json.load(sf)


def _ensure_unique_skill_id(candidate: str) -> str:
    existing = set(_existing_skill_ids())
    if candidate not in existing:
        return candidate
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{candidate}_{ts}"


def synthesize_skill_for_prompt(
    *,
    prompt: str,
    platform_id: str = "envoice",
    agent_id: str = "gemini-pro",
    preferred_skill_id: Optional[str] = None,
) -> Dict[str, Any]:
    platform_map = load_platform_map(platform_id)
    digest = platform_map_digest(platform_map)
    available_skill_ids = _existing_skill_ids()

    if preferred_skill_id:
        target_skill_id = preferred_skill_id
    else:
        target_skill_id = _ensure_unique_skill_id(
            f"{platform_id}.auto.{_slugify(prompt, max_len=36)}"
        )

    dust = DustClient()
    generated = dust.synthesize_skill_from_prompt(
        skill_id=target_skill_id,
        prompt=prompt,
        platform_map_digest=digest,
        available_skill_ids=available_skill_ids,
        agent_id=agent_id,
    )
    skill_spec = generated.get("skill_spec") or {}
    if not isinstance(skill_spec, dict):
        raise RuntimeError("Synthesized skill is not a JSON object.")

    skill_spec["id"] = _ensure_unique_skill_id(
        str(skill_spec.get("id") or target_skill_id)
    )
    skill_spec.setdefault("version", 1)
    skill_spec.setdefault("name", f"Auto-generated skill for: {prompt[:48]}")
    skill_spec.setdefault("description", "Synthesized from prompt and platform map.")
    skill_spec.setdefault("steps", [])
    skill_spec.setdefault("slots_schema", {"type": "object", "properties": {}})

    if not skill_spec.get("steps"):
        raise RuntimeError("Synthesized skill has no steps.")

    schema = _load_skill_schema()
    if schema is not None:
        try:
            validate(instance=skill_spec, schema=schema)
        except ValidationError as exc:
            raise RuntimeError(f"Synthesized skill failed schema validation: {exc.message}")

    seed_path = Path("seeds") / f"{skill_spec['id']}.json"
    seed_path.parent.mkdir(parents=True, exist_ok=True)
    with open(seed_path, "w", encoding="utf-8") as f:
        json.dump(skill_spec, f, indent=2)

    platform_map = merge_platform_signals(
        platform_map=platform_map,
        base_url=str(skill_spec.get("base_url") or ""),
        interaction_events=[],
        skill_id=skill_spec["id"],
        source="synth",
    )
    map_path = save_platform_map(platform_id, platform_map)

    return {
        "skill_id": skill_spec["id"],
        "seed_path": str(seed_path),
        "platform_map_path": str(map_path),
        "skill_spec": skill_spec,
        "agent_outputs": generated,
    }

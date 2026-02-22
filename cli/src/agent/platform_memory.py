import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List
from urllib.parse import urlparse

STATE_PLATFORM_DIR = Path(".state/platform_maps")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_slug(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in value.strip())
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_") or "default"


def _platform_map_path(platform_id: str) -> Path:
    STATE_PLATFORM_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_PLATFORM_DIR / f"{_safe_slug(platform_id)}.json"


def load_platform_map(platform_id: str) -> Dict[str, Any]:
    path = _platform_map_path(platform_id)
    if not path.exists():
        return {
            "platform_id": platform_id,
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
            "base_urls": [],
            "signals": {"selectors": {}, "actions": {}, "paths": {}},
            "recent_events": [],
            "skills": [],
            "mimic_sessions": [],
        }

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("platform_id", platform_id)
    data.setdefault("base_urls", [])
    data.setdefault("signals", {"selectors": {}, "actions": {}, "paths": {}})
    data.setdefault("recent_events", [])
    data.setdefault("skills", [])
    data.setdefault("mimic_sessions", [])
    return data


def save_platform_map(platform_id: str, platform_map: Dict[str, Any]) -> Path:
    path = _platform_map_path(platform_id)
    platform_map["platform_id"] = platform_id
    platform_map["updated_at"] = _utc_now_iso()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(platform_map, f, indent=2)
    return path


def _normalize_recent_events(events: Iterable[Dict[str, Any]], cap: int = 300) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for event in events:
        normalized.append(
            {
                "type": event.get("type"),
                "url": event.get("url"),
                "selector": event.get("selector"),
                "text": event.get("text"),
                "value": event.get("value"),
                "ts": event.get("ts"),
            }
        )
    return normalized[-cap:]


def merge_platform_signals(
    platform_map: Dict[str, Any],
    base_url: str,
    interaction_events: List[Dict[str, Any]],
    skill_id: str,
    source: str,
) -> Dict[str, Any]:
    signals = platform_map.setdefault(
        "signals", {"selectors": {}, "actions": {}, "paths": {}}
    )
    selector_counter = Counter(signals.get("selectors", {}))
    action_counter = Counter(signals.get("actions", {}))
    path_counter = Counter(signals.get("paths", {}))

    if base_url and base_url not in platform_map.get("base_urls", []):
        platform_map.setdefault("base_urls", []).append(base_url)

    for event in interaction_events:
        event_type = str(event.get("type") or "").strip()
        selector = str(event.get("selector") or "").strip()
        url = str(event.get("url") or "").strip()

        if event_type:
            action_counter[event_type] += 1
        if selector:
            selector_counter[selector] += 1
        if url:
            parsed = urlparse(url)
            path = parsed.path or "/"
            if parsed.query:
                path = f"{path}?{parsed.query}"
            path_counter[path] += 1

    signals["selectors"] = dict(selector_counter.most_common(200))
    signals["actions"] = dict(action_counter.most_common(100))
    signals["paths"] = dict(path_counter.most_common(200))

    existing_skill_ids = {str(item.get("id")) for item in platform_map.get("skills", [])}
    if skill_id and skill_id not in existing_skill_ids:
        platform_map.setdefault("skills", []).append(
            {"id": skill_id, "source": source, "captured_at": _utc_now_iso()}
        )

    platform_map["recent_events"] = _normalize_recent_events(
        list(platform_map.get("recent_events", [])) + interaction_events
    )
    platform_map.setdefault("mimic_sessions", []).append(
        {
            "captured_at": _utc_now_iso(),
            "event_count": len(interaction_events),
            "skill_id": skill_id,
            "source": source,
        }
    )
    platform_map["mimic_sessions"] = platform_map["mimic_sessions"][-100:]
    return platform_map


def platform_map_digest(platform_map: Dict[str, Any], top_n: int = 30) -> Dict[str, Any]:
    signals = platform_map.get("signals", {})
    selectors = dict(list((signals.get("selectors") or {}).items())[:top_n])
    actions = dict(list((signals.get("actions") or {}).items())[:top_n])
    paths = dict(list((signals.get("paths") or {}).items())[:top_n])

    return {
        "platform_id": platform_map.get("platform_id"),
        "base_urls": platform_map.get("base_urls", [])[:5],
        "top_actions": actions,
        "top_selectors": selectors,
        "top_paths": paths,
        "known_skills": [s.get("id") for s in platform_map.get("skills", []) if s.get("id")],
        "recent_event_count": len(platform_map.get("recent_events") or []),
    }

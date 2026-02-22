from typing import Any, Dict, List

SUPPORTED_ACTIONS = {
    "goto",
    "click",
    "fill",
    "fill_date",
    "fill_if_visible",
    "select_option",
    "select2",
    "select2_tax",
    "wait",
    "wait_for_url",
    "screenshot",
    "evaluate",
    "check_validation",
    "handle_cookies",
    "foreach",
}


def _normalize_step(step: Dict[str, Any]) -> Dict[str, Any]:
    action = str(step.get("action") or "").strip()
    params = step.get("params")
    if not isinstance(params, dict):
        params = {}
    args = step.get("args")
    if not isinstance(args, dict):
        args = {}

    def _pick(key: str) -> Any:
        if key in step and step.get(key) is not None:
            return step.get(key)
        if key in params and params.get(key) is not None:
            return params.get(key)
        if key in args and args.get(key) is not None:
            return args.get(key)
        return None

    # Map common aliases to runtime actions.
    if action in {"navigate", "open_url"}:
        action = "goto"
    elif action == "wait_for_selector":
        action = "wait"

    normalized: Dict[str, Any] = {"action": action}

    selector = _pick("selector")
    value = _pick("value")

    # Canonical url handling.
    if action == "goto" and value is None:
        value = _pick("url")
    if action == "wait_for_url" and value is None:
        value = _pick("url")

    # Canonical wait duration handling.
    timeout = _pick("timeout")
    if timeout is None and action == "wait":
        timeout = _pick("duration")

    search = _pick("search")
    result = _pick("result")
    store_as = _pick("store_as")
    items = _pick("items")
    skill = _pick("skill")
    optional = _pick("optional")
    skip_if_exists = _pick("skip_if_exists")

    if selector is not None:
        normalized["selector"] = str(selector)
    if value is not None:
        normalized["value"] = str(value)
    if timeout is not None:
        try:
            normalized["timeout"] = int(timeout)
        except Exception:
            pass
    if search is not None:
        normalized["search"] = str(search)
    if result is not None:
        normalized["result"] = str(result)
    if store_as is not None:
        normalized["store_as"] = str(store_as)
    if items is not None:
        normalized["items"] = str(items)
    if skill is not None:
        normalized["skill"] = str(skill)
    if optional is not None:
        normalized["optional"] = bool(optional)
    if skip_if_exists is not None:
        normalized["skip_if_exists"] = bool(skip_if_exists)

    return normalized


def _arguments_to_slots_schema(arguments: List[Dict[str, Any]]) -> Dict[str, Any]:
    properties: Dict[str, Any] = {}
    required: List[str] = []
    for arg in arguments:
        name = str(arg.get("name") or "").strip()
        if not name:
            continue
        arg_type = str(arg.get("type") or "string").strip().lower() or "string"
        description = str(arg.get("description") or "").strip()
        prop: Dict[str, Any] = {"type": "string" if arg_type not in {"string", "number", "integer", "boolean"} else arg_type}
        if description:
            prop["description"] = description
        properties[name] = prop
        if arg.get("required", True):
            required.append(name)
    return {"type": "object", "required": required, "properties": properties}


def normalize_skill_spec(
    skill_spec: Dict[str, Any],
    *,
    default_id: str,
    default_base_url: str,
) -> Dict[str, Any]:
    normalized = dict(skill_spec) if isinstance(skill_spec, dict) else {}
    normalized["id"] = str(normalized.get("id") or default_id)
    normalized["name"] = str(normalized.get("name") or f"Skill {normalized['id']}")
    normalized["description"] = str(
        normalized.get("description") or "Auto-generated workflow skill."
    )
    normalized["base_url"] = str(normalized.get("base_url") or default_base_url)
    normalized["version"] = int(normalized.get("version") or 1)

    steps = normalized.get("steps")
    if not isinstance(steps, list):
        steps = []

    runtime_steps: List[Dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        normalized_step = _normalize_step(step)
        action = normalized_step.get("action")
        if action not in SUPPORTED_ACTIONS:
            continue
        runtime_steps.append(normalized_step)

    normalized["steps"] = runtime_steps

    slots_schema = normalized.get("slots_schema")
    if not isinstance(slots_schema, dict):
        args = normalized.get("arguments")
        if isinstance(args, list):
            slots_schema = _arguments_to_slots_schema(
                [item for item in args if isinstance(item, dict)]
            )
        else:
            slots_schema = {"type": "object", "properties": {}}

    slots_schema.setdefault("type", "object")
    slots_schema.setdefault("properties", {})
    normalized["slots_schema"] = slots_schema
    return normalized

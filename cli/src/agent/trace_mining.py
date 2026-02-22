import json
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

RECORDER_INIT_SCRIPT = r"""
(() => {
  if (window.__agentRecorderInstalled) return;
  window.__agentRecorderInstalled = true;

  const MAX_VAL = 120;
  const clamp = (v) => {
    if (!v) return "";
    const s = String(v).replace(/\s+/g, " ").trim();
    return s.length > MAX_VAL ? s.slice(0, MAX_VAL) : s;
  };

  const cssPath = (el) => {
    if (!el || !(el instanceof Element)) return "";
    if (el.id) return `${el.tagName.toLowerCase()}#${el.id}`;
    const parts = [];
    let node = el;
    let depth = 0;
    while (node && node.nodeType === 1 && depth < 5) {
      let part = node.tagName.toLowerCase();
      if (node.name) part += `[name='${node.name}']`;
      else if (node.classList && node.classList.length) {
        part += "." + Array.from(node.classList).slice(0, 2).join(".");
      } else if (node.parentElement) {
        const siblings = Array.from(node.parentElement.children).filter(
          (x) => x.tagName === node.tagName
        );
        if (siblings.length > 1) {
          part += `:nth-of-type(${siblings.indexOf(node) + 1})`;
        }
      }
      parts.unshift(part);
      node = node.parentElement;
      depth += 1;
    }
    return parts.join(" > ");
  };

  const emit = (payload) => {
    try {
      if (typeof window.__agentEmit === "function") {
        window.__agentEmit({
          ...payload,
          url: location.href,
          title: document.title || "",
          ts: Date.now()
        });
      }
    } catch (e) {
      // Ignore telemetry failures.
    }
  };

  emit({ type: "page_loaded" });

  document.addEventListener("click", (e) => {
    const target = (e.target && e.target.closest)
      ? (e.target.closest("button,a,input,select,textarea,[role='button'],[onclick]") || e.target)
      : e.target;
    emit({
      type: "click",
      selector: cssPath(target),
      tag: target && target.tagName ? target.tagName.toLowerCase() : "",
      text: clamp(target && target.innerText ? target.innerText : target && target.value ? target.value : "")
    });
  }, true);

  document.addEventListener("input", (e) => {
    const target = e.target;
    if (!target || !target.tagName) return;
    const tag = target.tagName.toLowerCase();
    if (tag !== "input" && tag !== "textarea" && tag !== "select") return;
    let value = "";
    if (tag === "select") {
      const idx = target.selectedIndex;
      if (idx >= 0 && target.options && target.options[idx]) {
        value = target.options[idx].text || target.options[idx].value || "";
      }
    } else {
      value = target.type === "password" ? "<redacted>" : (target.value || "");
    }
    emit({
      type: "input",
      selector: cssPath(target),
      tag,
      input_type: target.type || "",
      value: clamp(value)
    });
  }, true);

  document.addEventListener("change", (e) => {
    const target = e.target;
    if (!target || !target.tagName) return;
    const tag = target.tagName.toLowerCase();
    if (tag !== "input" && tag !== "textarea" && tag !== "select") return;
    let value = "";
    if (tag === "select") {
      const idx = target.selectedIndex;
      if (idx >= 0 && target.options && target.options[idx]) {
        value = target.options[idx].text || target.options[idx].value || "";
      }
    } else {
      value = target.type === "password" ? "<redacted>" : (target.value || "");
    }
    emit({
      type: "change",
      selector: cssPath(target),
      tag,
      input_type: target.type || "",
      value: clamp(value)
    });
  }, true);

  window.addEventListener("submit", (e) => {
    const target = e.target;
    emit({
      type: "submit",
      selector: cssPath(target),
      tag: target && target.tagName ? target.tagName.toLowerCase() : ""
    });
  }, true);
})();
"""


def install_user_interaction_recorder(context: Any, sink: List[Dict[str, Any]]) -> None:
    def _emit(_source: Any, payload: Any) -> None:
        if isinstance(payload, dict):
            sink.append(payload)

    context.expose_binding("__agentEmit", _emit)
    context.add_init_script(RECORDER_INIT_SCRIPT)


def parse_trace_zip_actions(trace_zip_path: Path, max_events: int = 2000) -> List[Dict[str, Any]]:
    if not trace_zip_path.exists():
        return []

    events: List[Dict[str, Any]] = []
    with zipfile.ZipFile(trace_zip_path, "r") as zf:
        if "trace.trace" not in zf.namelist():
            return []

        with zf.open("trace.trace", "r") as trace_file:
            for raw_line in trace_file:
                try:
                    event = json.loads(raw_line.decode("utf-8"))
                except Exception:
                    continue

                if event.get("type") != "before":
                    continue

                method = str(event.get("method") or "")
                klass = str(event.get("class") or "")
                params = event.get("params") or {}
                if not isinstance(params, dict):
                    params = {}

                if method not in {
                    "goto",
                    "click",
                    "fill",
                    "type",
                    "selectOption",
                    "waitForSelector",
                    "waitForURL",
                    "press",
                }:
                    continue

                parsed: Dict[str, Any] = {
                    "type": f"api_{method}",
                    "class": klass,
                    "selector": params.get("selector"),
                    "url": params.get("url"),
                    "value": params.get("value"),
                    "key": params.get("key"),
                    "ts": event.get("startTime"),
                }
                if method == "selectOption":
                    parsed["value"] = (
                        params.get("value")
                        or params.get("label")
                        or params.get("index")
                        or params.get("values")
                    )

                events.append(parsed)
                if len(events) >= max_events:
                    break
    return events


def build_trace_summary(
    interaction_events: List[Dict[str, Any]],
    trace_events: List[Dict[str, Any]],
    max_lines: int = 120,
) -> str:
    lines: List[str] = []
    stream = interaction_events if interaction_events else trace_events
    for idx, event in enumerate(stream[:max_lines], start=1):
        evt_type = str(event.get("type") or "unknown")
        url = str(event.get("url") or "")
        selector = str(event.get("selector") or "")
        value = str(event.get("value") or event.get("text") or "")

        bits = [f"{idx:03d}. {evt_type}"]
        if selector:
            bits.append(f"selector={selector}")
        if value:
            bits.append(f"value={value}")
        if url:
            bits.append(f"url={url}")
        lines.append(" | ".join(bits))

    if not lines:
        return "No actionable events captured."
    return "\n".join(lines)


def _selector_to_slot_name(selector: str, fallback_index: int) -> str:
    if not selector:
        return f"field_{fallback_index}"

    name_match = re.search(r"\[name=['\"]([^'\"]+)['\"]\]", selector)
    if name_match:
        raw = name_match.group(1)
    else:
        id_match = re.search(r"#([A-Za-z0-9_\-]+)", selector)
        raw = id_match.group(1) if id_match else selector

    raw = raw.replace("sales_invoice__", "")
    raw = re.sub(r"\[\d+\]\[", "_", raw)
    raw = raw.replace("[", "_").replace("]", "")
    raw = re.sub(r"[^A-Za-z0-9_]+", "_", raw).strip("_").lower()
    if not raw:
        raw = f"field_{fallback_index}"
    return raw


def _looks_like_date(selector: str, value: str) -> bool:
    text = f"{selector} {value}".lower()
    if "date" in text or "deadline" in text or "due" in text:
        return True
    if re.match(r"^\d{2}[./-]\d{2}[./-]\d{4}$", value):
        return True
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return True
    return False


def _step_key(step: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        step.get("action"),
        step.get("selector"),
        step.get("value"),
        step.get("search"),
        step.get("result"),
    )


def infer_skill_from_events(
    skill_id: str,
    base_url: str,
    interaction_events: List[Dict[str, Any]],
) -> Dict[str, Any]:
    # Use active interaction stream first; if empty, fallback to API events.
    stream = [e for e in interaction_events if isinstance(e, dict)]
    first_url = ""
    for event in stream:
        url = str(event.get("url") or "")
        if url.startswith("http"):
            first_url = url
            break
    goto_url = first_url or base_url

    steps: List[Dict[str, Any]] = [{"action": "goto", "value": goto_url}]
    slot_props: Dict[str, Any] = {}
    required: List[str] = []
    slot_idx = 1
    last_select2_container = ""

    for event in stream:
        evt_type = str(event.get("type") or "")
        selector = str(event.get("selector") or "")
        value = str(event.get("value") or "").strip()
        text = str(event.get("text") or "").strip()
        tag = str(event.get("tag") or "").strip().lower()

        if evt_type == "click":
            if "select2-selection" in selector:
                last_select2_container = selector
                continue

            if selector:
                steps.append({"action": "click", "selector": selector})
            elif text:
                steps.append({"action": "click", "selector": f"text={text}"})
            continue

        if evt_type not in {"input", "change"}:
            continue
        if not selector:
            continue
        if value in {"", "<redacted>"}:
            continue

        if "select2-search__field" in selector and last_select2_container:
            slot_name = _selector_to_slot_name(last_select2_container, slot_idx)
            slot_idx += 1
            slot_props.setdefault(
                slot_name, {"type": "string", "description": f"Value for {slot_name}"}
            )
            slot_props[slot_name]["default"] = value
            if slot_name not in required:
                required.append(slot_name)

            steps.append(
                {
                    "action": "select2",
                    "selector": last_select2_container,
                    "search": "input.select2-search__field",
                    "value": f"{{{{{slot_name}}}}}",
                    "result": ".select2-results__option--highlighted",
                }
            )
            last_select2_container = ""
            continue

        slot_name = _selector_to_slot_name(selector, slot_idx)
        slot_idx += 1
        slot_props.setdefault(
            slot_name, {"type": "string", "description": f"Value for {slot_name}"}
        )
        slot_props[slot_name]["default"] = value
        if slot_name not in required:
            required.append(slot_name)

        if tag == "select" or "select" in selector:
            steps.append(
                {
                    "action": "select_option",
                    "selector": selector,
                    "value": f"{{{{{slot_name}}}}}",
                }
            )
        elif _looks_like_date(selector, value):
            steps.append(
                {
                    "action": "fill_date",
                    "selector": selector,
                    "value": f"{{{{{slot_name}}}}}",
                }
            )
        else:
            steps.append(
                {"action": "fill", "selector": selector, "value": f"{{{{{slot_name}}}}}"}
            )

    # Remove back-to-back duplicates from noisy inputs.
    compact_steps: List[Dict[str, Any]] = []
    seen_prev: Optional[Tuple[Any, ...]] = None
    for step in steps:
        key = _step_key(step)
        if key == seen_prev:
            continue
        compact_steps.append(step)
        seen_prev = key

    compact_steps.append({"action": "screenshot"})

    parsed = urlparse(goto_url if goto_url.startswith("http") else base_url)
    skill_name = f"Mined workflow on {parsed.netloc or 'platform'}"
    return {
        "id": skill_id,
        "version": 1,
        "name": skill_name,
        "description": "Auto-mined from real mimic interaction events.",
        "base_url": f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else base_url,
        "steps": compact_steps,
        "slots_schema": {
            "type": "object",
            "required": required,
            "properties": slot_props,
        },
    }

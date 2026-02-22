from typing import Any, Dict, List, Optional


def _sorted_selectors(platform_map: Dict[str, Any]) -> List[str]:
    selectors = platform_map.get("signals", {}).get("selectors", {}) or {}
    if isinstance(selectors, dict):
        return [k for k, _ in sorted(selectors.items(), key=lambda x: x[1], reverse=True)]
    return []


def _pick_selector(selectors: List[str], needles: List[str]) -> Optional[str]:
    lowered = [(s, s.lower()) for s in selectors]
    for needle in needles:
        n = needle.lower()
        for raw, low in lowered:
            if n in low:
                return raw
    return None


def _candidate_add_path(prompt: str, paths: List[str]) -> str:
    p = prompt.lower()
    sales_needles = ["/desktop/sale/add", "/desktop/sale/new"]
    purchase_needles = [
        "/desktop/purchase/add",
        "/desktop/purchase/new",
        "/desktop/purchase",
    ]
    target = purchase_needles if "purchase" in p else sales_needles
    lowered = [(x, x.lower()) for x in paths]
    for needle in target:
        for raw, low in lowered:
            if needle in low:
                return raw
    for raw, low in lowered:
        if "/desktop/" in low and ("add" in low or "new" in low) and "edit" not in low:
            return raw
    if "purchase" in p:
        return "/desktop/purchase/add"
    return "/desktop/sale/add"


def _base_url(platform_map: Dict[str, Any], default_base_url: str) -> str:
    base_urls = platform_map.get("base_urls") or []
    if base_urls and isinstance(base_urls[0], str) and base_urls[0]:
        return str(base_urls[0]).rstrip("/")
    return default_base_url.rstrip("/")


def _add_slot(
    slots: Dict[str, Any],
    required: List[str],
    name: str,
    description: str,
    *,
    is_required: bool = True,
) -> str:
    if name not in slots:
        slots[name] = {"type": "string", "description": description}
    if is_required and name not in required:
        required.append(name)
    return name


def _canonical_invoice_selector(field: str, picked: Optional[str]) -> Optional[str]:
    p = (picked or "").lower()
    if field == "description":
        if not picked or ("sales_invoice__row[0]" in p and "[description]" not in p):
            return "input[name='sales_invoice__row[0][description]']:visible"
        if "[description]" in p and ":visible" not in p:
            return f"{picked}:visible"
        return picked
    if field == "amount":
        if not picked or ("sales_invoice__row[0]" in p and "[item_amount]" not in p):
            return "input[name='sales_invoice__row[0][item_amount]']:visible"
        if "[item_amount]" in p and ":visible" not in p:
            return f"{picked}:visible"
        return picked
    if field == "quantity":
        if not picked or ("sales_invoice__row[0]" in p and "[item_qty]" not in p):
            return "input[name='sales_invoice__row[0][item_qty]']:visible"
        return picked
    if field == "due_days":
        if picked and "#due_days" in p and "#sales_invoice__due_days" not in p:
            return "input#sales_invoice__due_days"
        return picked
    return picked


def extrapolate_skill_from_platform_map(
    *,
    prompt: str,
    platform_map: Dict[str, Any],
    skill_id: str,
    default_base_url: str,
) -> Dict[str, Any]:
    selectors = _sorted_selectors(platform_map)
    paths = list((platform_map.get("signals", {}).get("paths", {}) or {}).keys())
    base = _base_url(platform_map, default_base_url)
    add_path = _candidate_add_path(prompt, paths)
    target_url = add_path if add_path.startswith("http") else f"{base}{add_path}"

    steps: List[Dict[str, Any]] = [{"action": "goto", "value": target_url}]
    slot_props: Dict[str, Any] = {}
    required: List[str] = []

    customer_select2 = _pick_selector(
        selectors,
        [
            "select2-buyercompanyid-container",
            "buyercompanyid",
            "select2-companyid-container",
        ],
    )
    invoice_date = _pick_selector(selectors, ["sales_invoice__invoice_date", "invoice_date"])
    transaction_date = _pick_selector(
        selectors, ["sales_invoice__transaction_date", "transaction_date"]
    )
    due_days = _pick_selector(selectors, ["sales_invoice__due_days", "due_days"])
    description = _pick_selector(
        selectors, ["row[0][description]", "row_description", "description"]
    )
    amount = _pick_selector(
        selectors,
        ["row[0][item_amount]", "row_item_amount", "item_amount", "amount"],
    )
    qty = _pick_selector(selectors, ["row[0][item_qty]", "item_qty", "quantity"])
    save_btn = _pick_selector(
        selectors,
        ["save", "btn-warning", "btn-primary", "submit", "sales_invoice__save"],
    )

    due_days = _canonical_invoice_selector("due_days", due_days)
    description = _canonical_invoice_selector("description", description)
    amount = _canonical_invoice_selector("amount", amount)
    qty = _canonical_invoice_selector("quantity", qty)

    if customer_select2:
        slot = _add_slot(slot_props, required, "customer", "Customer name")
        steps.append({"action": "click", "selector": customer_select2})
        steps.append(
            {
                "action": "select2",
                "selector": customer_select2,
                "search": "input.select2-search__field",
                "value": f"{{{{{slot}}}}}",
                "result": ".select2-results__option--highlighted",
            }
        )

    if invoice_date:
        slot = _add_slot(slot_props, required, "invoice_date", "Invoice issue date (DD.MM.YYYY)")
        steps.append({"action": "fill_date", "selector": invoice_date, "value": f"{{{{{slot}}}}}"})

    if transaction_date:
        slot = _add_slot(
            slot_props, required, "delivery_date", "Delivery/transaction date (DD.MM.YYYY)"
        )
        steps.append({"action": "fill_date", "selector": transaction_date, "value": f"{{{{{slot}}}}}"})

    if due_days:
        slot = _add_slot(
            slot_props,
            required,
            "due_days",
            "Payment terms in days",
            is_required=False,
        )
        steps.append(
            {"action": "fill_if_visible", "selector": due_days, "value": f"{{{{{slot}}}}}"}
        )

    if description:
        slot = _add_slot(slot_props, required, "description", "Invoice line description")
        steps.append({"action": "fill", "selector": description, "value": f"{{{{{slot}}}}}"})

    if qty:
        slot = _add_slot(
            slot_props,
            required,
            "quantity",
            "Invoice line quantity",
            is_required=False,
        )
        steps.append(
            {"action": "fill_if_visible", "selector": qty, "value": f"{{{{{slot}}}}}"}
        )

    if amount:
        slot = _add_slot(slot_props, required, "amount", "Invoice line amount")
        steps.append({"action": "fill", "selector": amount, "value": f"{{{{{slot}}}}}"})

    if save_btn:
        steps.append({"action": "click", "selector": save_btn})

    steps.append({"action": "check_validation"})
    steps.append({"action": "screenshot"})

    return {
        "id": skill_id,
        "version": 1,
        "name": f"Extrapolated skill for: {prompt[:48]}",
        "description": "Synthesized from platform map memory signals.",
        "base_url": base,
        "steps": steps,
        "slots_schema": {
            "type": "object",
            "required": required,
            "properties": slot_props,
        },
    }

import re
from typing import Any, Dict, Optional

import httpx

from agent.config import config

_CURRENCY_MAP = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
}

_FREQUENCY_PATTERNS = {
    "weekly": r"\b(weekly|every week)\b",
    "monthly": r"\b(monthly|every month)\b",
    "quarterly": r"\b(quarterly|every quarter)\b",
    "annual": r"\b(annual|annually|yearly|every year)\b",
}

_TAX_RULE_PATTERNS = {
    "reverse_charge": r"\b(reverse charge)\b",
    "standard": r"\b(standard tax|standard vat|standard)\b",
    "reduced": r"\b(reduced tax|reduced vat|reduced)\b",
    "zero_rated": r"\b(zero[- ]rated|zero vat|vat exempt)\b",
}

_EU_VAT_PREFIXES = {
    "AT",
    "BE",
    "BG",
    "CY",
    "CZ",
    "DE",
    "DK",
    "EE",
    "EL",
    "ES",
    "FI",
    "FR",
    "HR",
    "HU",
    "IE",
    "IT",
    "LT",
    "LU",
    "LV",
    "MT",
    "NL",
    "PL",
    "PT",
    "RO",
    "SE",
    "SI",
    "SK",
}


def _extract_amount_and_currency(prompt: str) -> Dict[str, Any]:
    symbol_match = re.search(r"([$€£])\s*([0-9]+(?:[.,][0-9]{1,2})?)", prompt)
    if symbol_match:
        symbol = symbol_match.group(1)
        amount = float(symbol_match.group(2).replace(",", "."))
        return {"amount": amount, "currency": _CURRENCY_MAP.get(symbol, "EUR")}

    code_match = re.search(
        r"\b([0-9]+(?:[.,][0-9]{1,2})?)\s*(USD|EUR|GBP|CHF|SEK|NOK|DKK)\b",
        prompt,
        flags=re.IGNORECASE,
    )
    if code_match:
        amount = float(code_match.group(1).replace(",", "."))
        return {"amount": amount, "currency": code_match.group(2).upper()}

    return {}


def _extract_frequency(prompt: str) -> Optional[str]:
    text = prompt.lower()
    for frequency, pattern in _FREQUENCY_PATTERNS.items():
        if re.search(pattern, text):
            return frequency
    return None


def _extract_tax_rule(prompt: str) -> Optional[str]:
    text = prompt.lower()
    for tax_rule, pattern in _TAX_RULE_PATTERNS.items():
        if re.search(pattern, text):
            return tax_rule
    return None


def _extract_vat_id(prompt: str) -> Optional[str]:
    # Broad EU VAT ID format: country prefix + alnum payload.
    match = re.search(r"\b([A-Z]{2}[A-Z0-9]{6,14})\b", prompt.upper())
    if match:
        candidate = match.group(1)
        prefix = candidate[:2]
        payload = candidate[2:]
        if prefix in _EU_VAT_PREFIXES and any(ch.isdigit() for ch in payload):
            return candidate
    return None


def parse_invoice_prompt(prompt: str) -> Dict[str, Any]:
    slots: Dict[str, Any] = {}
    slots.update(_extract_amount_and_currency(prompt))

    frequency = _extract_frequency(prompt)
    if frequency:
        slots["period"] = frequency

    tax_rule = _extract_tax_rule(prompt)
    if tax_rule:
        slots["tax_rule"] = tax_rule

    vat_id = _extract_vat_id(prompt)
    if vat_id:
        slots["vat_id"] = vat_id

    return slots


def validate_vat_id(vat_id: str) -> Dict[str, Any]:
    url = config.VAT_CHECK_API_URL
    params = {"vat_number": vat_id}

    try:
        response = httpx.get(url, params=params, timeout=15.0)
        response.raise_for_status()
        payload = response.json()
        return {
            "checked": True,
            "provider": "vatcomply(vies)",
            "vat_id": vat_id,
            "valid": bool(payload.get("valid")),
            "country_code": payload.get("country_code"),
            "name": payload.get("name"),
            "address": payload.get("address"),
        }
    except Exception as exc:
        return {
            "checked": True,
            "provider": "vatcomply(vies)",
            "vat_id": vat_id,
            "valid": None,
            "error": str(exc),
        }

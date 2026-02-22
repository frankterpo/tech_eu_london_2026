from typing import Optional, Tuple

import httpx

GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def _extract_google_error(resp: httpx.Response) -> Optional[str]:
    try:
        payload = resp.json()
    except Exception:
        return None

    err = payload.get("error")
    if not isinstance(err, dict):
        return None

    message = str(err.get("message") or "").strip()
    status = str(err.get("status") or "").strip()
    if status and message:
        return f"{status}: {message}"
    if message:
        return message
    if status:
        return status
    return None


def check_gemini_connectivity(
    api_key: Optional[str], timeout: float = 10.0
) -> Tuple[bool, str]:
    if not api_key:
        return False, "missing GEMINI_API_KEY (or GOOGLE_API_KEY)"

    attempts = [
        (GEMINI_MODELS_URL, {"x-goog-api-key": api_key}),
        (f"{GEMINI_MODELS_URL}?key={api_key}", {}),
    ]
    failures: list[str] = []

    for url, headers in attempts:
        try:
            resp = httpx.get(url, headers=headers, timeout=timeout)
        except Exception as exc:
            failures.append(str(exc))
            continue

        if resp.status_code == 200:
            return True, "ok"

        details = _extract_google_error(resp)
        if details:
            normalized = details.lower()
            if "reported as leaked" in normalized:
                return (
                    False,
                    "PERMISSION_DENIED: key flagged as leaked; rotate GEMINI_API_KEY",
                )
            failures.append(details)
        else:
            failures.append(f"status={resp.status_code}")

    if not failures:
        return False, "unknown error"
    return False, failures[0]

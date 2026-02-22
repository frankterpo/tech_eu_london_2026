import httpx

from agent.gemini import check_gemini_connectivity


def test_gemini_check_missing_key():
    ok, details = check_gemini_connectivity(None)
    assert ok is False
    assert "missing GEMINI_API_KEY" in details


def test_gemini_check_leaked_key_message(monkeypatch):
    def fake_get(url, headers=None, timeout=10.0):
        request = httpx.Request("GET", url, headers=headers)
        return httpx.Response(
            403,
            request=request,
            json={
                "error": {
                    "code": 403,
                    "message": "Your API key was reported as leaked. Please use another API key.",
                    "status": "PERMISSION_DENIED",
                }
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    ok, details = check_gemini_connectivity("AIzaSy-test")
    assert ok is False
    assert "flagged as leaked" in details


def test_gemini_check_falls_back_to_query_param(monkeypatch):
    calls = []

    def fake_get(url, headers=None, timeout=10.0):
        calls.append((url, headers))
        request = httpx.Request("GET", url, headers=headers)
        if headers and headers.get("x-goog-api-key"):
            return httpx.Response(
                403,
                request=request,
                json={"error": {"status": "PERMISSION_DENIED", "message": "blocked"}},
            )
        return httpx.Response(200, request=request, json={"models": []})

    monkeypatch.setattr(httpx, "get", fake_get)
    ok, details = check_gemini_connectivity("AIzaSy-test")
    assert ok is True
    assert details == "ok"
    assert len(calls) == 2

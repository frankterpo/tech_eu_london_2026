from agent.supabase_auth import get_supabase_access_token, get_supabase_rest_key


def test_supabase_rest_key_prefers_service_role(monkeypatch):
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "eyJ.service")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "eyJ.anon")
    monkeypatch.setenv("SUPABASE_API_KEY", "sbp_legacy_pat")
    assert get_supabase_rest_key() == "eyJ.service"


def test_supabase_rest_key_ignores_pat_api_key(monkeypatch):
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_API_KEY", "sbp_legacy_pat")
    assert get_supabase_rest_key() is None


def test_supabase_access_token_prefers_access_token(monkeypatch):
    monkeypatch.setenv("SUPABASE_ACCESS_TOKEN", "sbp_access_token")
    monkeypatch.setenv("SUPABASE_API_KEY", "sbp_legacy_pat")
    assert get_supabase_access_token() == "sbp_access_token"


def test_supabase_access_token_falls_back_to_pat_api_key(monkeypatch):
    monkeypatch.delenv("SUPABASE_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("SUPABASE_API_KEY", "sbp_legacy_pat")
    assert get_supabase_access_token() == "sbp_legacy_pat"

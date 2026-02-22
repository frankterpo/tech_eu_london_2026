import os
from typing import Optional


def _clean_env(name: str) -> Optional[str]:
    value = os.getenv(name)
    if not value:
        return None
    value = value.strip()
    return value or None


def _looks_like_jwt(value: str) -> bool:
    return value.startswith("eyJ") or value.count(".") == 2


def _looks_like_pat(value: str) -> bool:
    return value.startswith("sbp_")


def get_supabase_rest_key() -> Optional[str]:
    """
    Return a key suitable for PostgREST/Storage calls.
    Priority: service_role > anon > legacy SUPABASE_API_KEY (JWT only).
    """
    service = _clean_env("SUPABASE_SERVICE_ROLE_KEY")
    if service:
        return service
    anon = _clean_env("SUPABASE_ANON_KEY")
    if anon:
        return anon
    legacy = _clean_env("SUPABASE_API_KEY")
    if legacy and _looks_like_jwt(legacy):
        return legacy
    return None


def get_supabase_access_token() -> Optional[str]:
    """
    Return Supabase CLI access token.
    Priority: SUPABASE_ACCESS_TOKEN > legacy SUPABASE_API_KEY (PAT form).
    """
    token = _clean_env("SUPABASE_ACCESS_TOKEN")
    if token:
        return token
    legacy = _clean_env("SUPABASE_API_KEY")
    if legacy and _looks_like_pat(legacy):
        return legacy
    return None


def get_supabase_key() -> Optional[str]:
    """
    Backward-compatible alias used by runtime code paths.
    """
    return get_supabase_rest_key()

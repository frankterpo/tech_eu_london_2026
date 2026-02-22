import os
from typing import Optional


def get_supabase_key() -> Optional[str]:
    return (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
        or os.getenv("SUPABASE_API_KEY")
    )

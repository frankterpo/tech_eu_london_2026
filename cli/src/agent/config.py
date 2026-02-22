from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class EnvConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parents[3] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    GEMINI_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"

    CLOUDFLARE_API_TOKEN: str
    CLOUDFLARE_ACCOUNT_ID: str

    SUPABASE_URL: str
    SUPABASE_API_KEY: str
    SUPABASE_ANON_KEY: Optional[str] = None

    DUST_API_KEY: Optional[str] = None
    DUST_WORKSPACE_ID: Optional[str] = None

    ENVOICE_BASE_URL: str = "https://app.envoice.eu"
    ENVOICE_USERNAME: Optional[str] = None
    ENVOICE_PASSWORD: Optional[str] = None

    VAT_CHECK_API_URL: str = "https://api.vatcomply.com/vat"

    ARTIFACT_DIR: Path = Path(".state/artifacts")
    RUNS_DIR: Path = Path(".state/runs")
    AUTH_DIR: Path = Path(".state/auth")

    HEADLESS: bool = True
    WORKER_URL: Optional[str] = None

    @property
    def gemini_api_key(self) -> Optional[str]:
        key = self.GEMINI_API_KEY or self.GOOGLE_API_KEY
        if not key:
            return None
        key = key.strip()
        return key or None


config = EnvConfig()

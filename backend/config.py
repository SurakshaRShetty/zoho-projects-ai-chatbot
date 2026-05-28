from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central configuration loaded from .env file.
    Pydantic validates types and raises on startup if required vars are missing.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Zoho OAuth ────────────────────────────────────────────
    zoho_client_id: str
    zoho_client_secret: str
    zoho_redirect_uri: str = "http://localhost:8000/auth/callback"
    zoho_accounts_url: str = "https://accounts.zoho.com"
    zoho_api_base_url: str = "https://projectsapi.zoho.com"

    # ── App Security ─────────────────────────────────────────
    secret_key: str
    encryption_key: str
    access_token_expire_minutes: int = 1440  # 24 hours

    # ── Database ─────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./zoho_chatbot.db"

    # ── LLM ──────────────────────────────────────────────────
    llm_provider: str = "groq"
    groq_api_key: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    llm_model: str = "llama-3.3-70b-versatile"

    # ── App ───────────────────────────────────────────────────
    app_env: str = "development"
    backend_port: int = 8000
    frontend_url: str = "http://localhost:3000"
    allowed_origins: str = "http://localhost:3000"

    @property
    def allowed_origins_list(self) -> list[str]:
        """Split comma-separated origins into a list for CORS middleware."""
        return [o.strip() for o in self.allowed_origins.split(",")]

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    """
    Returns a cached singleton Settings instance.
    @lru_cache means .env is read once at startup, not on every request.
    """
    return Settings()


# Module-level singleton — import this everywhere
settings = get_settings()

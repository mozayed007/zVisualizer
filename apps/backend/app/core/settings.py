from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.errors import ServiceUnavailableAppError

PROJECT_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = PROJECT_ROOT / "apps" / "backend"
ROOT_ENV_PATH = PROJECT_ROOT / ".env"
BACKEND_ENV_PATH = BACKEND_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT_ENV_PATH, BACKEND_ENV_PATH),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "visualizer-agent"
    environment: Literal["development", "test", "production"] = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    frontend_origin: str = "http://localhost:5173"

    # Gemini Developer API: https://generativelanguage.googleapis.com/v1beta/models/{model}
    # Authenticate with GOOGLE_API_KEY or GEMINI_API_KEY (same as official docs' x-goog-api-key).
    google_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    )
    google_model_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_MODEL_NAME", "GEMINI_MODEL_NAME"),
    )
    google_fallback_model_name: str | None = Field(
        default="gemini-3.1-pro-preview",
        validation_alias=AliasChoices(
            "GOOGLE_FALLBACK_MODEL_NAME",
            "GEMINI_FALLBACK_MODEL_NAME",
        ),
    )
    google_visual_recovery_model_name: str | None = Field(
        default="gemini-3.1-pro-preview",
        validation_alias=AliasChoices(
            "GOOGLE_VISUAL_RECOVERY_MODEL_NAME",
            "GEMINI_VISUAL_RECOVERY_MODEL_NAME",
        ),
    )
    google_temperature: float = 0.2
    # Side-by-side SVG + prose + tool JSON needs headroom; 2048 truncates show_widget often.
    google_max_output_tokens: int = 12288
    # google-genai / PydanticAI currently support minimal|low|medium|high; keep xhigh
    # as a backwards-compatible env value and normalize it to high at request time.
    google_thinking_level: Literal["minimal", "low", "medium", "high", "xhigh"] = "high"
    google_retry_attempts: int = 2
    google_retry_backoff_ms: int = 700
    google_requests_per_minute_limit: int = 15
    google_tokens_per_minute_limit: int = 250_000
    google_requests_per_day_limit: int = 500
    google_max_input_tokens: int = 120_000
    google_reserved_output_tokens: int = 12_288
    google_max_history_tokens: int = 90_000

    max_conversation_turns: int = 200
    max_message_chars: int = 60_000
    enable_widget_cache: bool = True
    enable_learner_profiles: bool = True
    agent_load_full_skill_docs_on_session_start: bool = False

    chat_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("CHAT_API_KEY"),
    )
    database_path: Path = Field(
        default=PROJECT_ROOT / "data" / "conversations.db",
        validation_alias=AliasChoices("DATABASE_PATH", "CONVERSATIONS_DB_PATH"),
    )

    agent_config_path: Path = PROJECT_ROOT / "config" / "agent.visual.yaml"
    docs_root: Path = PROJECT_ROOT / "docs"

    @field_validator("database_path", mode="before")
    @classmethod
    def expand_database_path(cls, value: object) -> object:
        if isinstance(value, str):
            return Path(value)
        return value

    def require_google_api_key(self) -> str:
        if self.google_api_key is None:
            raise ServiceUnavailableAppError(
                "GOOGLE_API_KEY or GEMINI_API_KEY must be set in the process "
                "environment, workspace .env, or apps/backend/.env."
            )
        return self.google_api_key.get_secret_value()

    def resolve_google_model_name(self, configured_model: str | None) -> str:
        return configured_model or self.google_model_name or "gemini-3.1-flash-lite-preview"

    def resolve_google_thinking_config(self) -> dict[str, bool | str]:
        thinking_level = self.google_thinking_level
        if thinking_level == "xhigh":
            thinking_level = "high"
        return {
            "include_thoughts": True,
            "thinking_level": thinking_level,
        }

    def resolve_google_fallback_model_name(self, primary_model: str) -> str | None:
        if (
            self.google_fallback_model_name
            and self.google_fallback_model_name != primary_model
        ):
            return self.google_fallback_model_name
        return None

    def resolve_google_visual_recovery_model_name(self, primary_model: str) -> str | None:
        if (
            self.google_visual_recovery_model_name
            and self.google_visual_recovery_model_name != primary_model
        ):
            return self.google_visual_recovery_model_name
        return None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

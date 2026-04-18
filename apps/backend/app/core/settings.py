from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.core.errors import ServiceUnavailableAppError

PROJECT_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = PROJECT_ROOT / "apps" / "backend"
ROOT_ENV_PATH = PROJECT_ROOT / ".env"
BACKEND_ENV_PATH = BACKEND_ROOT / ".env"
DEFAULT_GOOGLE_ALLOWED_URL_DOMAINS = [
    "github.com",
    "*.github.com",
    "medium.com",
    "*.medium.com",
    "dev.to",
    "arxiv.org",
    "docs.python.org",
    "developer.mozilla.org",
    "x.com",
    "twitter.com",
    "wikipedia.org",
    "*.wikipedia.org",
]


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
        default="gemini-3-flash-preview",
        validation_alias=AliasChoices(
            "GOOGLE_FALLBACK_MODEL_NAME",
            "GEMINI_FALLBACK_MODEL_NAME",
        ),
    )
    google_visual_recovery_model_name: str | None = Field(
        default="gemini-3-flash-preview",
        validation_alias=AliasChoices(
            "GOOGLE_VISUAL_RECOVERY_MODEL_NAME",
            "GEMINI_VISUAL_RECOVERY_MODEL_NAME",
        ),
    )
    google_live_model_name: str | None = Field(
        default="gemini-3.1-flash-live-preview",
        validation_alias=AliasChoices("GOOGLE_LIVE_MODEL_NAME", "GEMINI_LIVE_MODEL_NAME"),
    )
    google_live_voice_name: str = Field(
        default="Charon",
        validation_alias=AliasChoices("GOOGLE_LIVE_VOICE_NAME", "GEMINI_LIVE_VOICE_NAME"),
    )
    google_live_language_code: str | None = Field(
        default="en-US",
        validation_alias=AliasChoices(
            "GOOGLE_LIVE_LANGUAGE_CODE",
            "GEMINI_LIVE_LANGUAGE_CODE",
        ),
    )
    google_live_thinking_level: Literal["minimal", "low", "medium", "high"] = Field(
        default="minimal",
        validation_alias=AliasChoices(
            "GOOGLE_LIVE_THINKING_LEVEL",
            "GEMINI_LIVE_THINKING_LEVEL",
        ),
    )
    google_service_tier: Literal[
        "SERVICE_TIER_STANDARD",
        "SERVICE_TIER_PRIORITY",
        "SERVICE_TIER_FLEX",
    ] = Field(
        default="SERVICE_TIER_PRIORITY",
        validation_alias=AliasChoices("GOOGLE_SERVICE_TIER", "GEMINI_SERVICE_TIER"),
    )
    google_temperature: float = 0.2
    # Side-by-side SVG + prose + tool JSON needs headroom; 2048 truncates show_widget often.
    google_max_output_tokens: int = 12288
    # google-genai / PydanticAI currently support minimal|low|medium|high; keep xhigh
    # as a backwards-compatible env value and normalize it to high at request time.
    google_thinking_level: Literal["minimal", "low", "medium", "high", "xhigh"] = "high"
    google_retry_attempts: int = 4
    google_retry_backoff_ms: int = 1500
    google_requests_per_minute_limit: int = 15
    google_tokens_per_minute_limit: int = 250_000
    google_requests_per_day_limit: int = 500
    google_max_input_tokens: int = 120_000
    google_reserved_output_tokens: int = 12_288
    google_max_history_tokens: int = 90_000
    google_enable_web_search: bool = True
    google_enable_url_context: bool = True
    google_allowed_url_domains: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: list(DEFAULT_GOOGLE_ALLOWED_URL_DOMAINS)
    )
    google_extra_allowed_url_domains: Annotated[list[str], NoDecode] = Field(
        default_factory=list
    )

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

    agent_config_dir: Path = PROJECT_ROOT / "config"
    agent_config_path: Path = PROJECT_ROOT / "config" / "agent.visual.yaml"
    default_agent_id: str = "visualizer"
    docs_root: Path = PROJECT_ROOT / "docs"
    svg_library_root: Path = PROJECT_ROOT / "data" / "SVGs_Organized"
    svg_preview_renderer_command: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SVG_PREVIEW_RENDERER_COMMAND"),
    )
    svg_preview_renderer_timeout_ms: int = Field(
        default=4000,
        validation_alias=AliasChoices("SVG_PREVIEW_RENDERER_TIMEOUT_MS"),
    )

    @field_validator("database_path", mode="before")
    @classmethod
    def expand_database_path(cls, value: object) -> object:
        if isinstance(value, str):
            return Path(value)
        return value

    @field_validator("svg_library_root", mode="before")
    @classmethod
    def expand_svg_library_root(cls, value: object) -> object:
        if isinstance(value, str):
            return Path(value)
        return value

    @field_validator("google_allowed_url_domains", "google_extra_allowed_url_domains", mode="before")
    @classmethod
    def parse_google_domain_lists(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
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
        configured = self.google_fallback_model_name
        if configured == "gemini-3.1-flash-lite-preview":
            configured = "gemini-3-flash-preview"
        if (
            configured
            and configured != primary_model
        ):
            return configured
        if primary_model.startswith("gemini-3.1-pro-preview"):
            return "gemini-2.5-pro"
        if primary_model.startswith("gemini-3.1-flash"):
            return "gemini-2.5-flash"
        return None

    def resolve_google_allowed_url_domains(self) -> list[str]:
        merged_domains = [
            *self.google_allowed_url_domains,
            *self.google_extra_allowed_url_domains,
        ]
        normalized: list[str] = []
        seen: set[str] = set()
        for domain in merged_domains:
            cleaned = domain.strip().lower().rstrip(".")
            if cleaned.startswith("."):
                cleaned = cleaned[1:]
            if not cleaned:
                continue
            if cleaned not in seen:
                seen.add(cleaned)
                normalized.append(cleaned)
        return normalized

    def resolve_google_visual_recovery_model_name(self, primary_model: str) -> str | None:
        configured = self.google_visual_recovery_model_name
        if configured == "gemini-3.1-flash-lite-preview":
            configured = "gemini-3-flash-preview"
        if (
            configured
            and configured != primary_model
        ):
            return configured
        if primary_model.startswith("gemini-3.1-pro-preview"):
            return "gemini-2.5-pro"
        if primary_model.startswith("gemini-3.1-flash"):
            return "gemini-2.5-flash"
        return None

    def resolve_google_live_model_name(self) -> str:
        return self.google_live_model_name or "gemini-3.1-flash-live-preview"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

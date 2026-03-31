from pydantic import SecretStr

from app.core.errors import RateLimitAppError, ValidationAppError
from app.core.settings import Settings
from app.services.model_limits import GeminiRateLimiter


def build_settings() -> Settings:
    return Settings(
        google_api_key=SecretStr("test-key"),
        google_requests_per_minute_limit=2,
        google_tokens_per_minute_limit=100,
        google_requests_per_day_limit=3,
        google_max_input_tokens=20,
        google_reserved_output_tokens=10,
    )


def test_rate_limiter_rejects_large_prompt() -> None:
    limiter = GeminiRateLimiter(build_settings())

    try:
        limiter.check_and_reserve(estimated_input_tokens=21, client_id="c1")
    except ValidationAppError as exc:
        assert exc.code == "VALIDATION_ERROR"
    else:
        raise AssertionError("Expected ValidationAppError")


def test_rate_limiter_buckets_are_per_client() -> None:
    limiter = GeminiRateLimiter(build_settings())

    limiter.check_and_reserve(estimated_input_tokens=5, client_id="a")
    limiter.check_and_reserve(estimated_input_tokens=5, client_id="a")
    limiter.check_and_reserve(estimated_input_tokens=5, client_id="b")
    limiter.check_and_reserve(estimated_input_tokens=5, client_id="b")


def test_rate_limiter_enforces_requests_per_minute() -> None:
    limiter = GeminiRateLimiter(build_settings())

    limiter.check_and_reserve(estimated_input_tokens=5, client_id="c1")
    limiter.check_and_reserve(estimated_input_tokens=5, client_id="c1")

    try:
        limiter.check_and_reserve(estimated_input_tokens=5, client_id="c1")
    except RateLimitAppError as exc:
        assert exc.code == "RATE_LIMITED"
    else:
        raise AssertionError("Expected RateLimitAppError")


def test_settings_configured_model_wins_over_environment_override(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_MODEL_NAME", "gemini-3-flash-preview")
    settings = Settings(
        google_api_key=SecretStr("test-key"),
    )

    assert (
        settings.resolve_google_model_name("gemini-3.1-flash-lite-preview")
        == "gemini-3.1-flash-lite-preview"
    )


def test_settings_build_google_thinking_config() -> None:
    settings = Settings(
        google_api_key=SecretStr("test-key"),
        google_thinking_level="medium",
    )

    assert settings.resolve_google_thinking_config() == {
        "include_thoughts": True,
        "thinking_level": "medium",
    }


def test_settings_normalize_legacy_xhigh_thinking_level() -> None:
    settings = Settings(
        google_api_key=SecretStr("test-key"),
        google_thinking_level="xhigh",
    )

    assert settings.resolve_google_thinking_config() == {
        "include_thoughts": True,
        "thinking_level": "high",
    }


def test_settings_merge_and_normalize_allowed_url_domains() -> None:
    settings = Settings(
        google_api_key=SecretStr("test-key"),
        google_allowed_url_domains=" GitHub.com ,*.WIKIPEDIA.org,github.com ",
        google_extra_allowed_url_domains="blog.example.com, *.Wikipedia.org ",
    )

    assert settings.resolve_google_allowed_url_domains() == [
        "github.com",
        "*.wikipedia.org",
        "blog.example.com",
    ]

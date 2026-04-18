from __future__ import annotations

from typing import Any, cast

from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.google import GoogleModel, GoogleModelSettings
from pydantic_ai.models import ModelRequestParameters


# ServiceTier mapping for google-genai >=1.75.
# The SDK's GenerateContentConfig.service_tier now accepts lowercase string
# literals ('unspecified' | 'flex' | 'standard' | 'priority') instead of the
# legacy integer enum values (0 / 1 / 2). We keep the historical settings keys
# so existing environment configuration continues to work.
SERVICE_TIER_ENUM_MAP: dict[str, str] = {
    "SERVICE_TIER_UNSPECIFIED": "unspecified",
    "SERVICE_TIER_STANDARD": "standard",
    "SERVICE_TIER_PRIORITY": "priority",
    "SERVICE_TIER_FLEX": "flex",
}


class PriorityGoogleModel(GoogleModel):
    async def _build_content_and_config(
        self,
        messages: list[ModelMessage],
        model_settings: GoogleModelSettings,
        model_request_parameters: ModelRequestParameters,
    ) -> tuple[list[Any], dict[str, Any]]:
        contents, config = await super()._build_content_and_config(
            messages,
            model_settings,
            model_request_parameters,
        )
        service_tier = cast(dict[str, Any], model_settings).get("google_service_tier")
        if service_tier:
            # Map the historical SERVICE_TIER_* settings value to the lowercase
            # string literal required by google-genai >=1.75.
            service_tier_value = SERVICE_TIER_ENUM_MAP.get(service_tier, service_tier)
            cast(dict[str, Any], config)["service_tier"] = service_tier_value
        return cast(list[Any], contents), cast(dict[str, Any], config)

from __future__ import annotations

from typing import Any, cast

from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.google import GoogleModel, GoogleModelSettings

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
        # pydantic-ai's `google_service_tier` expects Vertex-specific values
        # (e.g. pt_then_on_demand) and can assert on legacy SDK enum names.
        # We use the SDK-level `service_tier` instead, so remove the pydantic-ai
        # key before calling `super()` and inject the mapped SDK value after.
        settings_dict = cast(dict[str, Any], model_settings).copy()
        service_tier = settings_dict.pop("google_service_tier", None)

        contents, config = await super()._build_content_and_config(
            messages,
            cast(GoogleModelSettings, settings_dict),
            model_request_parameters,
        )
        if service_tier:
            # Map the historical SERVICE_TIER_* settings value to the lowercase
            # string literal required by google-genai >=1.75.
            service_tier_value = SERVICE_TIER_ENUM_MAP.get(service_tier, service_tier)
            cast(dict[str, Any], config)["service_tier"] = service_tier_value
        return cast(list[Any], contents), cast(dict[str, Any], config)

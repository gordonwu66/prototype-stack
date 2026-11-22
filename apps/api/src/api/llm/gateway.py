from collections.abc import AsyncIterator, Sequence

from pydantic import BaseModel

from api.config import Settings, settings
from api.llm.providers import (
    AnthropicProvider,
    OpenAICompatibleProvider,
    OpenAIResponsesProvider,
)
from api.llm.types import Effort, LLMMessage, Provider, StreamEvent


class ModelSpec(BaseModel):
    id: str  # "<provider>/<model>", what clients send
    provider: str
    model: str
    supports_effort: bool


class Gateway:
    """Routes a model id to the SDK client that serves it."""

    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}
        self._models: dict[str, ModelSpec] = {}

    @classmethod
    def from_settings(cls, s: Settings) -> Gateway:
        gateway = cls()
        if s.anthropic_api_key:
            gateway.register(
                "anthropic",
                AnthropicProvider(s.anthropic_api_key.get_secret_value()),
                s.anthropic_models,
                supports_effort=True,
            )
        if s.openai_api_key:
            gateway.register(
                "openai",
                OpenAIResponsesProvider(api_key=s.openai_api_key.get_secret_value()),
                s.openai_models,
                supports_effort=True,
            )
        if s.openweight_base_url:
            key = s.openweight_api_key.get_secret_value() if s.openweight_api_key else "unused"
            gateway.register(
                "openweight",
                OpenAICompatibleProvider(api_key=key, base_url=s.openweight_base_url),
                s.openweight_models,
                supports_effort=False,
            )
        return gateway

    def register(
        self, name: str, provider: Provider, models: Sequence[str], *, supports_effort: bool
    ) -> None:
        self._providers[name] = provider
        for model in models:
            spec = ModelSpec(
                id=f"{name}/{model}", provider=name, model=model, supports_effort=supports_effort
            )
            self._models[spec.id] = spec

    @property
    def models(self) -> list[ModelSpec]:
        return list(self._models.values())

    def get(self, model_id: str) -> ModelSpec | None:
        return self._models.get(model_id)

    def stream(
        self,
        spec: ModelSpec,
        messages: Sequence[LLMMessage],
        *,
        system: str | None,
        effort: Effort | None,
        cache_key: str | None,
    ) -> AsyncIterator[StreamEvent]:
        return self._providers[spec.provider].stream(
            model=spec.model,
            messages=messages,
            system=system,
            effort=effort if spec.supports_effort else None,
            cache_key=cache_key,
        )


gateway = Gateway.from_settings(settings)

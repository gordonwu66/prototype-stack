from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel

Role = Literal["user", "assistant"]
Effort = Literal["low", "medium", "high", "xhigh", "max"]
StopReason = Literal["end_turn", "max_tokens", "refusal", "cancelled", "error"]


class Usage(BaseModel):
    # Every prompt token, cached or not, so the count means the same for every provider.
    input_tokens: int
    # How many of input_tokens were read from the provider's prompt cache.
    cached_input_tokens: int = 0
    output_tokens: int


@dataclass(frozen=True, slots=True)
class LLMMessage:
    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class TextDelta:
    text: str


@dataclass(frozen=True, slots=True)
class ReasoningDelta:
    text: str


@dataclass(frozen=True, slots=True)
class StreamEnd:
    stop_reason: StopReason
    # The model that actually served the turn; differs from the requested one after a fallback.
    model: str
    usage: Usage | None


StreamEvent = TextDelta | ReasoningDelta | StreamEnd


class Provider(Protocol):
    """Streams one completion as provider-neutral events, ending with a StreamEnd.

    `cache_key` names the conversation, for providers that route prompt-cache lookups
    on it; requests with the same key share a growing prefix.
    """

    def stream(
        self,
        *,
        model: str,
        messages: Sequence[LLMMessage],
        system: str | None,
        effort: Effort | None,
        cache_key: str | None,
    ) -> AsyncIterator[StreamEvent]: ...

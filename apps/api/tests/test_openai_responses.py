from collections.abc import AsyncIterator, Sequence
from typing import Any, cast

import pytest
from openai import omit
from openai.types.responses import (
    Response,
    ResponseCompletedEvent,
    ResponseError,
    ResponseErrorEvent,
    ResponseFailedEvent,
    ResponseIncompleteEvent,
    ResponseReasoningSummaryPartAddedEvent,
    ResponseReasoningSummaryTextDeltaEvent,
    ResponseRefusalDeltaEvent,
    ResponseTextDeltaEvent,
    ResponseUsage,
)
from openai.types.responses.response import IncompleteDetails
from openai.types.responses.response_usage import InputTokensDetails

from api.llm.providers import OpenAIResponsesProvider
from api.llm.types import (
    Effort,
    LLMMessage,
    ReasoningDelta,
    StreamEnd,
    StreamEvent,
    TextDelta,
    Usage,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeStream:
    def __init__(self, events: Sequence[object]) -> None:
        self._events = events

    async def __aenter__(self) -> FakeStream:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def __aiter__(self) -> AsyncIterator[object]:
        for event in self._events:
            yield event


class FakeResponses:
    def __init__(self, events: Sequence[object]) -> None:
        self.events = events
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> FakeStream:
        self.kwargs = kwargs
        return FakeStream(self.events)


class FakeClient:
    def __init__(self, events: Sequence[object]) -> None:
        self.responses = FakeResponses(events)


def make_provider(events: Sequence[object]) -> tuple[OpenAIResponsesProvider, FakeResponses]:
    provider = OpenAIResponsesProvider(api_key="test")
    client = FakeClient(events)
    cast(Any, provider)._client = client
    return provider, client.responses


async def collect(
    provider: OpenAIResponsesProvider,
    *,
    messages: Sequence[LLMMessage] = (LLMMessage("user", "hello"),),
    system: str | None = None,
    effort: Effort | None = None,
    cache_key: str | None = None,
) -> list[StreamEvent]:
    stream = provider.stream(
        model="gpt-test", messages=messages, system=system, effort=effort, cache_key=cache_key
    )
    return [event async for event in stream]


# What final() reports: 5 input tokens, 3 of them read from the cache.
USAGE = Usage(input_tokens=5, cached_input_tokens=3, output_tokens=7)


def text(delta: str) -> ResponseTextDeltaEvent:
    return ResponseTextDeltaEvent.model_construct(type="response.output_text.delta", delta=delta)


def summary_part(index: int) -> ResponseReasoningSummaryPartAddedEvent:
    return ResponseReasoningSummaryPartAddedEvent.model_construct(
        type="response.reasoning_summary_part.added", summary_index=index
    )


def summary(delta: str) -> ResponseReasoningSummaryTextDeltaEvent:
    return ResponseReasoningSummaryTextDeltaEvent.model_construct(
        type="response.reasoning_summary_text.delta", delta=delta
    )


def final(status: str, **fields: Any) -> Response:
    defaults: dict[str, Any] = {
        "model": "gpt-test-2026-10-01",
        "usage": ResponseUsage.model_construct(
            input_tokens=5,
            input_tokens_details=InputTokensDetails.model_construct(cached_tokens=3),
            output_tokens=7,
        ),
        "incomplete_details": None,
        "error": None,
    }
    return Response.model_construct(status=status, **{**defaults, **fields})


def completed(response: Response | None = None) -> ResponseCompletedEvent:
    return ResponseCompletedEvent.model_construct(
        type="response.completed", response=response or final("completed")
    )


async def test_streams_reasoning_summary_then_text() -> None:
    provider, responses = make_provider(
        [
            summary_part(0),
            summary("Think"),
            summary("ing"),
            summary_part(1),
            summary("More"),
            text("Hi"),
            text("!"),
            completed(),
        ]
    )

    events = await collect(
        provider,
        messages=[
            LLMMessage("user", "hello"),
            LLMMessage("assistant", "hey"),
            LLMMessage("user", "again"),
        ],
        system="Be brief",
        effort="high",
        cache_key="conversation-1",
    )

    assert events == [
        ReasoningDelta("Think"),
        ReasoningDelta("ing"),
        ReasoningDelta("\n\n"),
        ReasoningDelta("More"),
        TextDelta("Hi"),
        TextDelta("!"),
        StreamEnd("end_turn", "gpt-test-2026-10-01", USAGE),
    ]
    assert responses.kwargs == {
        "model": "gpt-test",
        "input": [
            {"type": "message", "role": "user", "content": "hello"},
            {"type": "message", "role": "assistant", "content": "hey"},
            {"type": "message", "role": "user", "content": "again"},
        ],
        "instructions": "Be brief",
        "reasoning": {"summary": "auto", "effort": "high"},
        "prompt_cache_key": "conversation-1",
        "store": False,
        "stream": True,
    }


async def test_omits_instructions_effort_and_cache_key_when_unset() -> None:
    provider, responses = make_provider([text("ok"), completed()])

    await collect(provider)

    assert responses.kwargs["instructions"] is omit
    assert responses.kwargs["reasoning"] == {"summary": "auto"}
    assert responses.kwargs["prompt_cache_key"] is omit


async def test_incomplete_at_output_limit_is_max_tokens() -> None:
    response = final(
        "incomplete",
        incomplete_details=IncompleteDetails.model_construct(reason="max_output_tokens"),
    )
    provider, _ = make_provider(
        [
            text("partial"),
            ResponseIncompleteEvent.model_construct(type="response.incomplete", response=response),
        ]
    )

    events = await collect(provider)

    assert events[-1] == StreamEnd("max_tokens", "gpt-test-2026-10-01", USAGE)


async def test_refusal_is_streamed_as_text() -> None:
    refusal = ResponseRefusalDeltaEvent.model_construct(
        type="response.refusal.delta", delta="I can't help with that."
    )
    provider, _ = make_provider([refusal, completed()])

    events = await collect(provider)

    assert events[0] == TextDelta("I can't help with that.")
    assert isinstance(events[-1], StreamEnd)
    assert events[-1].stop_reason == "refusal"


async def test_failed_response_raises() -> None:
    response = final("failed", error=ResponseError.model_construct(message="boom"))
    provider, _ = make_provider(
        [ResponseFailedEvent.model_construct(type="response.failed", response=response)]
    )

    with pytest.raises(RuntimeError, match="boom"):
        await collect(provider)


async def test_error_event_raises() -> None:
    provider, _ = make_provider(
        [ResponseErrorEvent.model_construct(type="error", message="overloaded")]
    )

    with pytest.raises(RuntimeError, match="overloaded"):
        await collect(provider)

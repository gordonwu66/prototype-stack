from collections.abc import AsyncIterator, Sequence

from anthropic import AsyncAnthropic, omit
from anthropic.types.beta import BetaMessageParam
from openai import AsyncOpenAI
from openai import omit as openai_omit
from openai.types.chat import ChatCompletionMessageParam
from openai.types.responses import (
    EasyInputMessageParam,
    Response,
    ResponseCompletedEvent,
    ResponseErrorEvent,
    ResponseFailedEvent,
    ResponseIncompleteEvent,
    ResponseReasoningSummaryPartAddedEvent,
    ResponseReasoningSummaryTextDeltaEvent,
    ResponseRefusalDeltaEvent,
    ResponseTextDeltaEvent,
)
from openai.types.shared_params import Reasoning

from api.llm.types import (
    Effort,
    LLMMessage,
    ReasoningDelta,
    StopReason,
    StreamEnd,
    StreamEvent,
    TextDelta,
    Usage,
)

_ANTHROPIC_STOP: dict[str, StopReason] = {
    "max_tokens": "max_tokens",
    "model_context_window_exceeded": "max_tokens",
    "refusal": "refusal",
}

_OPENAI_STOP: dict[str, StopReason] = {
    "length": "max_tokens",
    "content_filter": "refusal",
}

# Responses API: why a response ended with status "incomplete".
_RESPONSES_INCOMPLETE: dict[str, StopReason] = {
    "max_output_tokens": "max_tokens",
    "content_filter": "refusal",
}


def _anthropic_message(m: LLMMessage) -> BetaMessageParam:
    if m.role == "user":
        return {"role": "user", "content": m.content}
    return {"role": "assistant", "content": m.content}


def _openai_message(m: LLMMessage) -> ChatCompletionMessageParam:
    if m.role == "user":
        return {"role": "user", "content": m.content}
    return {"role": "assistant", "content": m.content}


def _responses_message(m: LLMMessage) -> EasyInputMessageParam:
    return {"type": "message", "role": m.role, "content": m.content}


class AnthropicProvider:
    # Models that accept server-side refusal fallback (Haiku has none).
    _FALLBACK_MODELS = frozenset({"claude-opus-5-5", "claude-sonnet-5-5"})

    def __init__(self, api_key: str | None) -> None:
        self._client = AsyncAnthropic(api_key=api_key)

    async def stream(
        self,
        *,
        model: str,
        messages: Sequence[LLMMessage],
        system: str | None,
        effort: Effort | None,
        cache_key: str | None,
    ) -> AsyncIterator[StreamEvent]:
        fallback = model in self._FALLBACK_MODELS
        async with self._client.beta.messages.stream(
            model=model,
            # The models' full output cap: thinking counts against it, and max effort can
            # think long enough to truncate the answer under a lower ceiling.
            max_tokens=128000,
            system=system or omit,
            messages=[_anthropic_message(m) for m in messages],
            # Caches the prompt through its last message. History only grows at the end,
            # so the next turn reads all of it back. Claude has no key to route on.
            cache_control={"type": "ephemeral"},
            # Current Claude models always think; "summarized" streams readable reasoning
            # instead of empty thinking blocks (which look like a stall in the UI).
            thinking={"type": "adaptive", "display": "summarized"},
            output_config={"effort": effort} if effort else omit,
            # On a safety-classifier refusal, the API retries on a recommended model in the
            # same stream; text already streamed stays valid.
            fallbacks="default" if fallback else omit,
            betas=["server-side-fallback-2026-07-01"] if fallback else omit,
        ) as stream:
            async for event in stream:
                if event.type == "text":
                    yield TextDelta(event.text)
                elif event.type == "thinking":
                    yield ReasoningDelta(event.thinking)
            final = await stream.get_final_message()

        usage = final.usage
        cached = usage.cache_read_input_tokens or 0
        yield StreamEnd(
            stop_reason=_ANTHROPIC_STOP.get(final.stop_reason or "", "end_turn"),
            model=final.model,
            usage=Usage(
                # Claude's input_tokens leaves out cache reads and writes; count them back in.
                input_tokens=usage.input_tokens + cached + (usage.cache_creation_input_tokens or 0),
                cached_input_tokens=cached,
                output_tokens=usage.output_tokens,
            ),
        )


class OpenAIResponsesProvider:
    """OpenAI's Responses API, used statelessly: the backend owns the history."""

    def __init__(self, *, api_key: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key)

    async def stream(
        self,
        *,
        model: str,
        messages: Sequence[LLMMessage],
        system: str | None,
        effort: Effort | None,
        cache_key: str | None,
    ) -> AsyncIterator[StreamEvent]:
        # Reasoning summaries stream as readable reasoning, like Claude's summarized thinking.
        reasoning: Reasoning = {"summary": "auto"}
        if effort:
            reasoning["effort"] = effort

        final: Response | None = None
        refused = False
        reasoned = False
        stream = await self._client.responses.create(
            model=model,
            input=[_responses_message(m) for m in messages],
            instructions=system or openai_omit,
            reasoning=reasoning,
            # Caching is automatic; the key routes a conversation's turns to the same cache.
            prompt_cache_key=cache_key or openai_omit,
            # Nothing is kept on OpenAI's side; every turn resends the history.
            store=False,
            stream=True,
        )
        async with stream:
            async for event in stream:
                match event:
                    case ResponseTextDeltaEvent(delta=delta):
                        yield TextDelta(delta)
                    case ResponseReasoningSummaryPartAddedEvent() if reasoned:
                        # A reasoning summary arrives as several parts; keep them apart.
                        yield ReasoningDelta("\n\n")
                    case ResponseReasoningSummaryTextDeltaEvent(delta=delta):
                        reasoned = True
                        yield ReasoningDelta(delta)
                    case ResponseRefusalDeltaEvent(delta=delta):
                        refused = True
                        yield TextDelta(delta)
                    case (
                        ResponseCompletedEvent(response=response)
                        | ResponseIncompleteEvent(response=response)
                        | ResponseFailedEvent(response=response)
                    ):
                        final = response
                    case ResponseErrorEvent(message=message):
                        raise RuntimeError(message)
                    case _:
                        pass

        if final is None:
            raise RuntimeError("Response stream ended without a final response")
        if final.status == "failed":
            raise RuntimeError(final.error.message if final.error else "Response failed")

        stop_reason: StopReason = "refusal" if refused else "end_turn"
        if final.status == "incomplete" and final.incomplete_details:
            stop_reason = _RESPONSES_INCOMPLETE.get(
                final.incomplete_details.reason or "", stop_reason
            )
        usage = final.usage
        yield StreamEnd(
            stop_reason=stop_reason,
            model=final.model,
            usage=Usage(
                input_tokens=usage.input_tokens,
                cached_input_tokens=usage.input_tokens_details.cached_tokens,
                output_tokens=usage.output_tokens,
            )
            if usage
            else None,
        )


class OpenAICompatibleProvider:
    """Any server speaking the Chat Completions API (vLLM, Ollama, Fireworks, Groq, ...)."""

    def __init__(self, *, api_key: str, base_url: str | None = None) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def stream(
        self,
        *,
        model: str,
        messages: Sequence[LLMMessage],
        system: str | None,
        effort: Effort | None,
        cache_key: str | None,
    ) -> AsyncIterator[StreamEvent]:
        params: list[ChatCompletionMessageParam] = []
        if system:
            params.append({"role": "system", "content": system})
        params.extend(_openai_message(m) for m in messages)

        stop_reason: StopReason = "end_turn"
        served_model = model
        usage: Usage | None = None
        stream = await self._client.chat.completions.create(
            model=model,
            messages=params,
            stream=True,
            stream_options={"include_usage": True},
            reasoning_effort=effort or openai_omit,
            # No prompt_cache_key: it's OpenAI's own field, which other servers may reject.
            # Their prefix caching (vLLM, Ollama) needs no key.
        )
        async with stream:
            async for chunk in stream:
                served_model = chunk.model or served_model
                if chunk.usage:
                    details = chunk.usage.prompt_tokens_details
                    usage = Usage(
                        input_tokens=chunk.usage.prompt_tokens,
                        cached_input_tokens=(details.cached_tokens if details else None) or 0,
                        output_tokens=chunk.usage.completion_tokens,
                    )
                for choice in chunk.choices:
                    delta = choice.delta
                    # Not in the OpenAI spec: open-weight servers stream reasoning as
                    # `reasoning` (Ollama, OpenRouter, newer vLLM) or `reasoning_content`.
                    reasoning = getattr(delta, "reasoning", None) or getattr(
                        delta, "reasoning_content", None
                    )
                    if isinstance(reasoning, str) and reasoning:
                        yield ReasoningDelta(reasoning)
                    if delta.content:
                        yield TextDelta(delta.content)
                    if delta.refusal:
                        stop_reason = "refusal"
                        yield TextDelta(delta.refusal)
                    if choice.finish_reason:
                        stop_reason = _OPENAI_STOP.get(choice.finish_reason, stop_reason)

        yield StreamEnd(stop_reason=stop_reason, model=served_model, usage=usage)

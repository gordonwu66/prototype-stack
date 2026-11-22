# Research sprint: Fireworks AI open-weight models as backend LLMs

Status: research only, nothing implemented. Researched 2026-11-06 against Fireworks' docs, changelog, rate card and Model Library. Fireworks changes its serverless models often, so re-check model IDs and prices before using them.

**Goal:** decide whether the gateway can serve Fireworks' top featured open-weight models directly. That covers today's streamed chat and the agent harness we plan next: tool and function calling, reasoning replay, structured output, and vision. We already do this through the `openai` and `anthropic` SDKs.

## Verdict

**Feasible, low risk.** I'm recommending it.

- **Chat works now with no code changes.** Fireworks serves the OpenAI Chat Completions API at `https://api.fireworks.ai/inference/v1`, and `OpenAICompatibleProvider` already reads Fireworks' `reasoning_content` stream field. Setting `OPENWEIGHT_BASE_URL` / `OPENWEIGHT_MODELS` is enough for a smoke test.
- **The agent harness fits too.** Tool calling uses OpenAI's format and streams argument deltas. It supports `tool_choice` (`auto|none|required|any|<named>`), `parallel_tool_calls`, and `response_format: json_schema`. Interleaved reasoning works when `reasoning_content` is replayed. Fireworks-specific code is a small adapter. The large piece is the provider-neutral content-block model, and the harness needs that for any provider anyway.
- **Use Chat Completions.** It is Fireworks' native API, and every Fireworks extension (`reasoning_history`, `prompt_cache_key`, `service_tier`, perf metrics) is a first-class field on it. The Anthropic-compatible `/v1/messages` endpoint is a translation layer with known gaps. The Responses API keeps server-side state for up to 30 days by default.
- **Three changes are needed before chat is production-ready:** a dedicated `fireworks` provider, always sending an explicit reasoning effort, and setting `prompt_cache_key`.
  - Effort matters because Kimi K3 thinks at **Max** when effort is omitted, and today the `openweight` provider always omits it.
  - The cache key matters because agent loops resend a growing context, and cached input costs about 2% of the normal input price on the default model.
- **Main risks:**
  - Tool-call quality varies between open models.
  - Models are retired often (at least 2 weeks' notice).
  - Some newer models' reasoning-effort behavior isn't documented.

  A 2–3 day validation spike (below) settles all three before we implement anything.

## Where we are today

- `apps/api/src/api/llm/` has `Gateway`, which routes `<provider>/<model>` to `AnthropicProvider` (Messages API, beta stream), `OpenAIResponsesProvider` (OpenAI, Responses API) or `OpenAICompatibleProvider` (open-weight servers, Chat Completions). Providers emit provider-neutral `TextDelta | ReasoningDelta | StreamEnd`.
- The `openweight` provider is a generic OpenAI-compatible endpoint (Ollama/vLLM/OpenRouter, and Fireworks per `config.py`). It registers with `supports_effort=False`, so no `reasoning_effort` is sent.
- History is plain text (`LLMMessage(role, content)`), so a session can switch models. Reasoning isn't replayed and there are no tools yet.
- `docs/SYSTEM_DESIGN.md` already plans `chat_messages.content` as a jsonb array of `[text, tool_use, tool_result, thinking]` blocks with a `tool` role. The Phase 2 spec below targets that shape.
- The UI groups models by `ModelSpec.provider` and shows `ModelSpec.model` as the label. A Fireworks model would currently show as `accounts/fireworks/models/...`.

## Fireworks platform summary

| Topic | What matters for us |
| - | - |
| Endpoints | Chat Completions `POST /inference/v1/chat/completions` (native). Anthropic Messages `POST /inference/v1/messages` (compat; SDK base URL is `.../inference` without `/v1`). Responses `POST /inference/v1/responses` (stateful). |
| Auth | `Authorization: Bearer $FIREWORKS_API_KEY`. |
| Model IDs | Resource names: `accounts/fireworks/models/<id>`. Fast and Ultra-fast variants are separate router IDs: `accounts/fireworks/routers/<id>-fast` and `...-ultrafast`. |
| Serverless modes | Standard (default); Priority (`service_tier: "priority"`, about 20–50% more, less load-shedding); Fast (router ID, 100+ tok/s target); Ultra-fast Preview (router ID, 6–8x speed, DeepSeek V4.1 Flash 1017 only). |
| Billing | Per token: input, cached input (discounted; varies by model), output. Batch API is 50% off. `usage` is the source of truth. On Chat Completions it comes on the final chunk, the one with `finish_reason`. |
| Prompt caching | Automatic, exact-prefix, replica-local. Route with `prompt_cache_key` (preferred), `user`, or the `x-session-affinity` header. Separate caches per account on serverless. |
| Rate limits | Adaptive, **per account and per model**, in tokens per minute. Limits start low and rise 25% at most every 15 minutes while usage is above 50%, and reset after 72 hours idle. Ceilings depend on model size (table under Operations). Errors are `429` with `Retry-After`, and `503` when load is shed even under the limit. |
| Lifecycle | Serverless models can be retired with **at least 2 weeks' notice**. Recent retirements: DeepSeek V4 Pro, GLM 5.2 and Kimi K2.6/K2.7 Code (2026-09-25); GPT OSS 120B and Nemotron 3 Ultra/3.5 Lightning (scheduled for 2026-11-07). Dedicated deployments aren't affected. |
| Privacy | Zero data retention by default on Chat Completions and Messages; only metadata is logged. The Responses API stores conversations for up to 30 days unless `store=false`. US-only serverless costs about 50% more (`us.api.fireworks.ai`). |
| SDK | No Fireworks SDK needed. The `openai` SDK works with `base_url`. The optional `fireworks-ai` SDK only adds typed extras such as `reasoning_content`. |

## Featured models

Featured serverless models from the Model Library on 2026-11-06, ordered by Fireworks' featured priority. All have function calling. Prices are USD per 1M tokens (Standard): input / cached input / output. "RL tier" is the rate-limit tier.

| Model | API `model` | Maker | Total params | Context | Vision | Price | RL tier |
| - | - | - | - | - | - | - | - |
| Kimi K3.1 Pro *(new 2026-11-02)* | `accounts/fireworks/models/kimi-k3p1-pro` | Moonshot | 2.78T | 1M | ✓ | 2.00 / 0.20 / 10.00 | Large |
| DeepSeek V4.1 Flash 1017 | `accounts/fireworks/models/deepseek-v4p1-flash-1017` | DeepSeek | 755B | 1M | ✓ | 0.30 / 0.006 / 1.20 | Small |
| DeepSeek V4.1 Flash | `accounts/fireworks/models/deepseek-v4p1-flash` | DeepSeek | 552B | 1M | ✓ | 0.30 / 0.006 / 1.20 | Small |
| Ember-1 | `accounts/fireworks/models/ember-1` | Fireworks | 2.78T | 1M | ✓ | 3.00 / 0.30 / 15.00 | Large |
| MiniMax M3.1 Flash | `accounts/fireworks/models/minimax-m3p1-flash` | MiniMax | 428B | 1M | ✓ | 0.15 / ? / 0.60 | Small* |
| GLM 5.3 Flash | `accounts/fireworks/models/glm-5p3-flash` | Z.ai | 320B | 1M | ✓ | 0.15 / 0.03 / 0.50 | Small |
| GLM 5.3 | `accounts/fireworks/models/glm-5p3` | Z.ai | 743B | 1M | ✗ | 1.40 / 0.26 / 4.40 | Small |
| Muse Spark Open *(US-only)* | `accounts/fireworks/models/muse-spark-open` | Meta | 816B | 1M | ✓ | 1.25 / 0.15 / 4.25 | Medium |

\* Not yet on the rate card or the tier table. The tier is inferred from its parameter count.

- **Also serverless but not featured:** Kimi K3 (3.00 / 0.30 / 15.00) and Qwen 3.8 Max (2.00 / 0.25 / 6.00).
- **Featured but dedicated-only (not serverless):** MiMo-V2.6-Pro-RL and Qwen3.8 Flash Next.
- **Fireworks' own picks:** its "AI agents with tool use" and "replace Claude Opus/Sonnet" recommendations both list Kimi K3.1 Pro, DeepSeek V4.1 Flash 1017, GLM 5.3 and MiniMax M3.

### Recommended starting lineup

| Role | Model | Why |
| - | - | - |
| Default and agent workhorse | DeepSeek V4.1 Flash 1017 | Top of every Fireworks agent recommendation. Cheapest capable model. Cached input is $0.006, which matters because each agent step resends the whole context. Small-tier (highest) rate limits. Has an Ultra-fast router. |
| Quality ceiling | Kimi K3.1 Pro | Strongest featured model for long-horizon agentic work, with vision. But it's 4 days old and in the Large tier (lowest rate limits). Fallback: GLM 5.3 or Kimi K3. |
| Second opinion | GLM 5.3 | Strong at coding and agents, mid-priced, and has a Fast router (`glm-5p3-fast`). Text-only. |
| Cheap and fast (titles, classification, sub-agents) | GLM 5.3 Flash or MiniMax M3.1 Flash | $0.15 input, vision, tools. |

Leave Ember-1 (most expensive), Muse Spark Open (only useful if we need US residency) and Qwen 3.8 Max (defaults to xhigh reasoning with a 131K-token thinking budget when effort is omitted) out of the defaults.

## Which Fireworks API to use

| | Chat Completions ✅ | Anthropic Messages (compat) | Responses |
| - | - | - | - |
| Our SDK path | `openai`, existing `OpenAICompatibleProvider` | `anthropic`, existing `AnthropicProvider` with `base_url` | `openai` |
| Fidelity | Native API | Translated to Chat Completions inside Fireworks | Native, stateful |
| Tools | OpenAI function tools, streamed `tool_calls` deltas, `tool_choice`, `parallel_tool_calls` | `tool_use`/`tool_result` blocks; client-side tool search and `defer_loading` | Function tools plus server-run MCP, `web_search`, `python` |
| Reasoning | `reasoning_content` (stream and replay), `reasoning_effort` (`none` through `max`), `reasoning_history` | `thinking` blocks; `output_config.effort`; `budget_tokens` converted to effort bands; `context_management` (clear thinking) | `reasoning` items, summary always on |
| Gaps | Non-standard fields go through `extra_body` / `getattr` | No `count_tokens` or batches; no server tools; no `cache_control`; forced `tool_choice` not allowed with thinking; some errors use Fireworks' format instead of Anthropic's | `store=true` by default (30-day retention); stored responses can be evicted after about 1h; no background mode with streaming |
| Verdict | **Primary.** The same adapter also covers local open-weight servers (OpenAI itself now uses the Responses API). | Compare in the spike. Revisit only if it matches Chat Completions on tool calls. | Not for the harness core. Our backend owns conversation state. |

## Spec, Phase 1: chat (smallest useful change)

**Config** (`config.py`, `.env.example`). Keep `openweight` for local Ollama/vLLM. Fireworks gets its own provider so both can run side by side:

```python
fireworks_api_key: SecretStr | None = None
fireworks_base_url: str = "https://api.fireworks.ai/inference/v1"  # US-only: https://us.api.fireworks.ai/inference/v1
fireworks_models: list[str] = [
    "accounts/fireworks/models/deepseek-v4p1-flash-1017",
    "accounts/fireworks/models/kimi-k3p1-pro",
    "accounts/fireworks/models/glm-5p3",
    "accounts/fireworks/models/glm-5p3-flash",
]
```

**Gateway:**
- Register `fireworks` with `OpenAICompatibleProvider(api_key=..., base_url=...)` and `supports_effort=True`.
- Public ID is `fireworks/<last path segment>`, e.g. `fireworks/deepseek-v4p1-flash-1017`. The wire `model` stays the full resource name.
- Add `ModelSpec.label` for the UI and show it instead of `model`.

**Provider call changes.** These apply to `OpenAICompatibleProvider` behind per-provider options. OpenAI's Responses API takes `prompt_cache_key` too, so `OpenAIResponsesProvider` can use the same session key.

| Param | Value | Why |
| - | - | - |
| `reasoning_effort` | Always sent. The UI's "default" maps to a provider default (`"medium"`). | Defaults when omitted vary: Kimi K3 thinks at **Max**, DeepSeek V4.1 at High, Qwen 3.8 Max at xhigh. `medium` becomes `high` on Kimi K3 and DeepSeek V4.1. |
| `prompt_cache_key` | `str(session_id)` (pass `session_key` into `Provider.stream`) | The cache is replica-local, so the key routes a session to the same replica. |
| `max_tokens` | Explicit cap, e.g. 32k | By default Fireworks lowers `max_tokens` to fit the context window. Combined with a 1M context and high effort, that's a cost risk. |
| `extra_body` | `{"perf_metrics_in_response": True}` (optional) | Streaming responses carry no perf headers, so this puts TTFT and tok/s in the body. |

**No change needed:**
- Reasoning arrives as `delta.reasoning_content`, which the existing `getattr` fallback already reads.
- Usage arrives on the `finish_reason` chunk, which the existing loop handles.
- `finish_reason: "length"` already maps to `max_tokens`.

**Later:** extend `Effort` with `none` (fast replies with no thinking) and `max`. Fireworks accepts `low|medium|high|xhigh|max|none`, but each model maps them differently.

## Spec, Phase 2: agent harness on Fireworks

### Provider-neutral types (`llm/types.py`)

These map 1:1 onto the planned `chat_messages.content` jsonb.

```python
TextBlock(text)
ImageBlock(media_type, data | url)
ReasoningBlock(text, source: str, signature: str | None)  # source = "<provider>/<model>"; signature is Claude-only
ToolUseBlock(id, name, input: dict, provider_id: str | None)  # provider_id = the ID the issuing model used
ToolResultBlock(tool_use_id, content: str | list[TextBlock | ImageBlock], is_error: bool = False)
Message(role: "user" | "assistant" | "tool", blocks: list[Block])
ToolSpec(name, description, input_schema: dict)  # name must match ^[a-zA-Z0-9_-]{1,64}$ (Fireworks/OpenAI limit, also valid for Anthropic)

# New stream events, alongside TextDelta / ReasoningDelta / StreamEnd
ToolCallStart(index, id, name)
ToolCallDelta(index, arguments_fragment)
ToolCallEnd(index, input: dict | None, error: str | None)
StopReason += "tool_use"
Usage += cached_input_tokens
```

`Provider.stream(model, messages, *, system, tools, tool_choice, effort, session_key, response_format)`

### Fireworks adapter mapping (Chat Completions)

| Canonical | Request | Notes |
| - | - | - |
| `system` | `{"role": "system", ...}` first | Keep the system prompt and tool list byte-stable: no timestamps, tools in a fixed order. Both are part of the cached prefix. |
| user `TextBlock` / `ImageBlock` | `content` parts `text` / `image_url` (URL or base64 data URL) | Gate images on `ModelSpec.supports_images` (GLM 5.3 has no vision). |
| assistant `TextBlock` | `content` | |
| assistant `ToolUseBlock` | `tool_calls[{id, type: "function", function: {name, arguments: json}}]` | |
| assistant `ReasoningBlock` | `reasoning_content` on the same assistant message | **Required** for interleaved thinking within a turn. Only when `source` is the target model. |
| `ToolResultBlock` | one `{"role": "tool", "tool_call_id", "content"}` per result, in call order | Send `is_error` as content text such as `"ERROR: ..."`; Chat Completions has no error flag. |
| `ToolSpec` | `tools[{type: "function", function: {name, description, parameters}}]` | Schemas support `$defs`/`$ref`, recursion and a root `$id`, but no external `$ref`. Pydantic `model_json_schema()` output works. |
| `tool_choice` | `auto` / `none` / `required` / `{type: "function", function: {name}}` | |
| (parallel) | `parallel_tool_calls: true` | Per-model support; verify in the spike. |
| `response_format` | `{"type": "json_schema", ...}` | Objects with `properties` act as `unevaluatedProperties: false`. `pattern` is best-effort. Put the schema in the prompt as well. |

**Streaming tool calls.** For each `delta.tool_calls[i]`, keyed by `index`:
- The first fragment carries `id` and `function.name`; emit `ToolCallStart` for it.
- Later fragments append `function.arguments`; emit `ToolCallDelta` for each.
- On `finish_reason == "tool_calls"`, parse each argument buffer, emit `ToolCallEnd`, and end with stop reason `tool_use`.
- If the JSON doesn't parse, don't crash the turn. Send back an error `ToolResultBlock` so the model can retry. Fireworks' docs explicitly warn that arguments can be malformed.

**Reasoning replay rules:**
1. **Within a turn** (assistant → tool → assistant, and so on), always replay prior `reasoning_content`. Without it, interleaved-thinking models lose their chain of reasoning.
2. **Across user turns,** leave `reasoning_history` unset (the model's default). Kimi models default to `preserved` and DeepSeek V4 to `interleaved`. Only override it if the spike shows a quality gain.
3. **Never replay a `ReasoningBlock` to a different model than its `source`.** Drop it instead. Claude thinking blocks need Claude signatures, and Fireworks reasoning is plain text in a model-specific chat template. This keeps model switching between turns working.

**Tool call IDs:**
- Fireworks passes through each model's own ID format: Kimi uses `functions.calculator:0`, MiniMax uses `chatcmpl-tool-…`.
- Anthropic rejects tool IDs outside `[a-zA-Z0-9_-]`.
- So store a sanitized canonical `id` and keep the original as `provider_id`. Replay `provider_id` to the model that issued it (it's rendered into that model's template), and the canonical ID to every other model.

**Things Fireworks doesn't provide, so the harness owns them:**
- **Server tools.** There are none on Chat Completions (web search, code execution, fetch), so those become our client tools.
- **Token counting.** There's no token-counting endpoint, so use `usage` for accounting. For context management, set `context_length_exceeded_behavior: "error"` (via `extra_body`) so an overflow shows up as a compaction trigger instead of a silently shrunk `max_tokens`.
- **Sampling defaults.** Fireworks suggests temperature 0.0–0.3 for tool calls, but reasoning models often have vendor-recommended values. Keep per-model sampling defaults in config and let the spike pick them.

## Operations

- **Rate limit ceilings** (spend tier 3 and above; lower tiers get less):

  | Tier | Total prompt TPM | Uncached prompt TPM | Generated TPM |
  | - | - | - | - |
  | Small | 216M | 54M | 2.16M |
  | Medium | 43.2M | 10.8M | 432k |
  | Large | 21.6M | 5.4M | 216k |

  Limits start low for a new account. That's fine for a prototype; for a launch, ask Fireworks to raise them or buy Reserved Throughput.
- **Retries.** The `openai` SDK's built-in retries honor `Retry-After` on 429. Also retry 503s with exponential backoff and jitter. If 503s become common, use Priority tier for user-facing traffic.
- **Model retirement.** Model IDs live only in env/config, never in code. Turn a 404 "Model not found" into a clear user-facing error. Optionally check the configured models against Fireworks' List Models API at startup.
- **Cost controls.** Set a monthly budget cap on the Fireworks account. Always send explicit `max_tokens` and effort. Track `cached_input_tokens` in `Usage`.
- **Privacy.** Use Chat Completions only, which keeps zero data retention. Avoid the Responses API, or use it with `store=false`.

## Risks

| Risk | Mitigation |
| - | - |
| Tool-call quality varies (bad arguments, missed parallel calls, no-call drift) | Run the conformance suite in the spike; defensive parsing plus a repair loop; default to the best-scoring model. |
| Frequent retirements (two batches in the last 6 weeks) | Config-driven model list; startup validation; documented fallback per role. |
| Effort mapping is undocumented for the newest models (K3.1 Pro, GLM 5.3, MiniMax M3.1 Flash) | Measure in the spike; always send explicit effort. |
| Non-standard fields (`reasoning_content`, `reasoning_history`) aren't in the `openai` SDK's types | `getattr` / `extra_body` / `cast`; unit tests on recorded stream fixtures. |
| Kimi K3.1 Pro is new and in the Large tier | Don't make it the default; GLM 5.3 or Kimi K3 as fallback. |

## Validation spike (before any implementation), about 2–3 days

1. **Chat smoke test (0.5 day).** Use the existing `openweight` provider via env (no code change) on the 4 lineup models. Record TTFT, tok/s, whether reasoning appears, usage, and cached tokens on the second turn. Confirm where streaming usage reports cached tokens.
2. **Tool-call conformance (1–1.5 days).** A scratch script running about 10 scenarios against each model:
   - single call
   - parallel calls
   - should-not-call
   - forced `required` / named `tool_choice`
   - nested `$defs` schema
   - a 3+ step chain with interleaved reasoning
   - an error result
   - a large result
   - streamed-argument assembly

   Run it over Chat Completions, and for the top 2 models also over the Anthropic-compatible endpoint. Score valid JSON, schema adherence, correct tool choice, and parallel support.
3. **Reasoning controls (0.5 day).** Measure each model's default and per-level thinking. Inspect the rendered prompt with `raw_output: true` to confirm `reasoning_history` behavior.
4. **Cross-provider replay (0.5 day).** Run a session with tool history across Claude → Fireworks → Claude. Check ID sanitizing and reasoning dropping.

**Exit criteria:**
- The default model gets ≥95% valid, schema-correct tool calls on the suite.
- Parallel calls work on at least one lineup model.
- Streamed arguments assemble correctly.
- Cached-token reporting is confirmed.
- No blocking gap turns up.

If all pass, do Phase 1 (about half a day), then build Phase 2 alongside the provider-neutral harness work.

## Open questions

- Should a Fireworks model be the default for new chats, or stay opt-in next to Claude and GPT?
- Do we need US-only data residency? It adds about 50% on most models.
- Use Priority tier for interactive traffic from the start, or only once 503s appear?
- Where should the spike scripts live: committed as opt-in live tests (`pytest -m live`) or kept in scratch?

## Sources

- [Which model should I use?](https://docs.fireworks.ai/guides/recommended-models): agent and migration recommendations
- [Model Library](https://fireworks.ai/models): featured models, context, params, vision and tools flags
- [Serverless pricing](https://docs.fireworks.ai/serverless/pricing) · [Serverless overview](https://docs.fireworks.ai/serverless/overview) · [Serverless modes](https://docs.fireworks.ai/serverless/serverless-modes) · [Rate limits](https://docs.fireworks.ai/serverless/rate-limits)
- [Tool calling](https://docs.fireworks.ai/guides/function-calling) · [Reasoning](https://docs.fireworks.ai/guides/reasoning) · [Structured outputs](https://docs.fireworks.ai/structured-responses/structured-response-formatting) · [Prompt caching](https://docs.fireworks.ai/guides/prompt-caching)
- [Chat Completions API reference](https://docs.fireworks.ai/api-reference/post-chatcompletions): `reasoning_effort` per model, `reasoning_history`, `prompt_cache_key`, `parallel_tool_calls`
- [OpenAI compatibility](https://docs.fireworks.ai/tools-sdks/openai-compatibility) · [Anthropic compatibility](https://docs.fireworks.ai/tools-sdks/anthropic-compatibility) · [Responses API](https://docs.fireworks.ai/guides/response-api)
- [Zero data retention](https://docs.fireworks.ai/guides/security_compliance/data_handling) · [Changelog](https://docs.fireworks.ai/updates/changelog): retirements, new models, rate-limit changes

# Harness core — spec

Status: design only, nothing implemented. Written 2026-11-09.

**Goal:** turn the chat prototype into an agent harness: a model-neutral tool loop, a tool registry with built-in tools, a per-session sandbox, and an eval runner. Every later direction (B2B wedges, routing, distillation, sub-agents, integrations) builds on these four pieces.

Builds on [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) (protocol, entities) and [FIREWORKS_RESEARCH.md](FIREWORKS_RESEARCH.md) Phase 2 (provider-neutral block types, Fireworks adapter mapping). Those types are not repeated here; this doc only lists changes to them. Product directions that sit on top of it are in [wedges/](wedges/README.md).

## Decisions

- **The loop is transport-agnostic.** `agent/loop.py` yields events; Socket.IO and the eval runner are two consumers of the same loop. `chat/socket.py` keeps only transport.
- **History is blocks, not text.** `ChatMessage.content` becomes `list[Block]`; the separate `reasoning` string goes away. This is the `chat_messages.content` jsonb already planned.
- **All tools are ours.** No provider server tools (Anthropic/OpenAI web search, code execution) in the core, so every model gets the same tool set and results are comparable. Fireworks has none anyway.
- **Tools that touch files or run code only run in a sandbox.** Nothing executes in the API process.
- **No new tables for tracing.** One LLM call produces one assistant message, so per-call usage, cost, model, timing and stop reason live on `chat_messages`; `turn_id` groups a turn. Tool timing lives on the result block.
- **Harness behaviour is one frozen config object** (`HarnessConfig`), hashed into every eval result. This is what makes ablations possible.

## Module layout

```
apps/api/src/api/
  llm/        types.py (blocks, events)  providers.py (adapters)  gateway.py
  agent/      loop.py  config.py (HarnessConfig)  context.py (request assembly, replay rules, truncation)
  tools/      base.py (Tool, ToolContext, registry)  builtin/{web,todo,files,bash}.py
  sandbox/    base.py (Sandbox protocol)  docker.py
  chat/       socket.py (transport)  store.py  schemas.py
apps/api/evals/   suites/  graders.py  runner.py
```

## Types: changes to the Fireworks Phase 2 list

| Change | Why |
| - | - |
| `ReasoningBlock.signature` → `replay: dict \| None` (opaque) | Claude needs its thinking signature replayed inside a tool loop; OpenAI's stateless Responses API needs the encrypted reasoning item. Same idea, different payload. Confirm both in Phase 1. |
| `ReasoningBlock.source` is the **served** model | Anthropic's refusal fallback can serve a different model than requested. |
| `ToolResultBlock` += `duration_ms`, `truncated: bool` | Tracing and context accounting without extra tables. |
| `StopReason` += `tool_use`, `max_steps`, `awaiting_approval` | Loop outcomes the UI and evals must tell apart. |
| `ChatMessage.role` += `tool`; `turn_id` added | A tool message holds one step's results. Adapters fold it into a user message (Anthropic), `function_call_output` items (OpenAI Responses) or `role: tool` messages (Chat Completions). |
| `Usage` += `cache_write_input_tokens` | `AnthropicProvider` folds cache writes into `input_tokens` today, which counts them but can't price them. Like `cached_input_tokens`, it is a subset of `input_tokens`; providers with no write charge report 0. |
| `ModelSpec` += `prices` (USD per 1M: input, cached input, cache write, output), `context_window`, `supports_images`, `supports_parallel_tools` | Cost and eligibility per model. Comes from config, so the model lists in `config.py` become structured entries. |
| `ChatMessage` += `cost_usd` | Set at `StreamEnd` from `Usage` × the **served** model's prices. `None` when the price is unknown, never 0. Turn cost is the sum over `turn_id`. |

These last three are what routing needs ([wedges/MODEL_ROUTING.md](wedges/MODEL_ROUTING.md)), and evals report cost from them.

## Agent loop

```
run_turn(session, config) -> AsyncIterator[LoopEvent]
  repeat:
    request  = context.build(history, config)       # system + tools byte-stable, replay rules applied
    message  = stream one assistant message          # yields block starts and deltas
    if message.stop_reason != "tool_use": stop
    results  = run tool calls                        # see below
    append tool message; step += 1
    if step == config.max_steps: stop with "max_steps"
```

- **Tool execution.** Calls marked `parallel_safe` run concurrently with `asyncio.gather`; the rest run in call order. Each has a timeout from its tool definition.
- **Errors go back to the model, not the user.** Unknown tool, arguments that fail JSON parsing or Pydantic validation, timeout and tool exceptions all become `ToolResultBlock(is_error=True)` so the model can retry.
- **History stays valid.** Every `ToolUseBlock` gets a result before the turn ends. On cancel or crash, unanswered calls get a synthetic `"cancelled"` result; otherwise Anthropic rejects the next request.
- **Result size.** Results over `config.max_result_chars` (30k default) are cut, flagged `truncated`, and the full output is written to the sandbox workspace when there is one.
- **Context overflow** in v1 ends the turn with `max_tokens`. Compaction is Phase 5.
- **Limits per turn:** `max_steps` (default 50), wall-clock timeout, and a token or cost budget summed from `Usage` and `cost_usd`.

## Tools

```python
class Tool(Protocol):
    name: str                    # ^[a-zA-Z0-9_-]{1,64}$
    description: str
    Input: type[BaseModel]       # input_schema = Input.model_json_schema()
    read_only: bool
    parallel_safe: bool
    timeout_s: float
    async def run(self, ctx: ToolContext, input: BaseModel) -> ToolResult: ...

ToolContext(session_id, user_id, sandbox: Sandbox | None, emit_progress)
```

| Tool | Phase | Needs sandbox | Read-only | Notes |
| - | - | - | - | - |
| `todo_write` | 2 | no | yes | State-only; renders as the task list the requirements call for. |
| `web_fetch` | 2 | no | yes | HTML to markdown, size cap, blocks private IP ranges. |
| `web_search` | 2 | no | yes | Needs a search API; see open questions. |
| `read_file`, `glob`, `grep` | 3 | yes | yes | |
| `write_file`, `edit_file` | 3 | yes | no | |
| `bash` | 3 | yes | no | Streams stdout as progress. |

The registry sorts tools by name so the cached prefix is stable. Later tool sources (MCP servers, per-tenant integrations, `spawn_agent`) register through the same protocol.

## Sandbox

```python
class Sandbox(Protocol):
    async def exec(self, cmd: str, *, timeout_s: float) -> ExecResult   # exit_code, stdout, stderr
    async def read(self, path: str) -> bytes
    async def write(self, path: str, data: bytes) -> None
    async def close(self) -> None
```

- **v1: `DockerSandbox`.** One container per session, created on first use, removed after an idle timeout. Workspace is a named volume mounted at `/workspace`. CPU, memory and PID limits; non-root user; network off by default.
- **Hosted option is deferred.** The protocol is small enough to back with E2B, Modal, Daytona or Fargate tasks when the API is deployed.

## Permissions

| Mode | Behaviour |
| - | - |
| `read_only` | Only `read_only` tools are offered to the model. |
| `ask` | Non-read-only calls pause the turn until a client approves or denies. |
| `auto` (default) | Everything runs; safe because v1 write tools only reach the sandbox. |

Integration tools with outside side effects (Phase 5+) default to `ask` regardless of mode. A denial becomes an error result so the model can change course.

## Socket protocol changes

The existing rule stays: `chat:message` inserts or replaces a whole message, `chat:delta` appends a fragment, and `seq` makes resume idempotent.

- `chat:delta` gains `index` (which block) and two kinds: `tool_input` (argument JSON fragments) and `tool_output` (progress from a running tool).
- Structural changes resend the whole message through `chat:message`: a block starting, a tool call's arguments completing, a tool result arriving. These are rare compared with text deltas.
- New client event `tool:approve {session_id, tool_use_id, decision: "allow" | "deny"}`.
- `ChatSession` gains `status: "idle" | "running" | "awaiting_approval"`, sent through the existing `session:upserted`.
- `chat:send` is unchanged. Permission mode and tool set come from the session's config, not from each send.

Frontend: `lib/chat.ts` mirrors the block types; `use-chat.ts` applies deltas by `index`; new components for a tool call card, the task list and an approval prompt.

## Evals

`apps/api/evals/`, built on Pydantic Evals as [SYSTEM.md](SYSTEM.md) already chose. Live runs are opt-in (`pytest -m live` or `python -m evals run`), never in the default test run.

| Suite | What it measures | Size |
| - | - | - |
| Adapter fixtures | Recorded provider streams replayed through each adapter; no network. Runs in normal `pytest`. | Per provider |
| Tool-call conformance | The 10 scenarios from the Fireworks spike, across every configured model. | 10 × models |
| Agent tasks | Small sandbox tasks graded by code: fix a failing test, multi-file edit, CSV wrangling, research against a local fixture site. | 10–20 |

- **Graders:** code checks on the final workspace or transcript first; an LLM judge only where code can't decide.
- **Metrics per run:** pass, steps, input/cached/output tokens, cost, wall time, tool error rate.
- **Results:** JSONL keyed by `(suite, case, model, HarnessConfig hash, git sha)`.
- **Ablations:** change one `HarnessConfig` field (system prompt, tool descriptions, parallel tools, effort, `max_steps`) and compare pass rate and cost on the same model.

## Phases

Estimates are rough guesses for one person.

| Phase | Scope | Exit criteria | Est. |
| - | - | - | - |
| 1. Blocks and adapters | Block types; tool calling and reasoning replay on all three providers; store and schemas on blocks; model price table and cost per message. | Adapter fixture tests pass; a scripted two-step tool exchange works live on Claude, GPT and one Fireworks model; `cost_usd` for one live call per provider matches usage × rate card worked by hand. | 3–4 d |
| 2. Loop and first tools | `agent/loop.py`, registry, `todo_write`, `web_fetch`, socket changes, tool cards in the UI. | A chat fetches a URL and answers from it; cancel mid-tool leaves valid history; resume mid-turn renders correctly. | 3–4 d |
| 3. Sandbox | `DockerSandbox`, file and bash tools, permission modes, approval flow. | The agent clones a small repo, edits it and runs its tests inside the container; `ask` mode blocks a write until approved. | 3–4 d |
| 4. Evals | Runner, `HarnessConfig`, conformance and agent-task suites. | One command prints a model × suite table; one ablation shows a measurable delta. | 3 d |
| 5. Later | Compaction, sub-agents, MCP and integration vault, durable runs across restarts, model routing and gateway failover ([wedges/MODEL_ROUTING.md](wedges/MODEL_ROUTING.md)), trajectory export. | Separate specs. | |

Postgres is independent of phases 1–2 (the in-memory `ChatStore` is enough) and should land before phase 3, so sandboxes and eval results survive a restart.

## Out of scope for the core

Auth and multi-tenancy, MCP, sub-agents, long-term memory, runs that survive an API restart, more than one API process, and provider server tools.

## Risks

| Risk | Mitigation |
| - | - |
| Reasoning replay differs per provider and breaks tool loops silently | Phase 1 fixture tests plus the cross-provider replay check from the Fireworks spike. |
| `web_fetch` brings untrusted text into context (prompt injection) | v1 has no private data and no outside write actions; revisit before integrations, and keep the sandbox network off. |
| Approval state is an in-memory future, lost on restart | Acceptable for the prototype; durable runs are Phase 5. |
| Docker on the API host doesn't carry to ECS Fargate | The `Sandbox` protocol isolates it; choose the hosted backend before deploying. |

## Open questions

- Which search API backs `web_search` (Brave, Tavily, Exa), or skip search until there is a need?
- Should `auto` stay the default once integration tools exist?
- Hosted sandbox: managed (E2B, Modal, Daytona) or our own Fargate tasks?
- Do eval results stay as JSONL in the repo, or go to Postgres or Langfuse datasets?

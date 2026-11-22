# Model and cost routing — feature and wedge

Status: hypothesis, nothing built. Written 2026-11-09. Prices come from [FIREWORKS_RESEARCH.md](../FIREWORKS_RESEARCH.md) (2026-11-06); re-check before quoting them.

## Verdict

- **As a feature: build it.** A routing policy inside the harness is cheap, every other wedge needs it, and it is one of the best learning projects on the list.
- **As a standalone wedge: weak on its own, worth one cheap test.** Per-request routers and gateways are a crowded market and labs ship their own auto modes. What is less served is routing that understands an agent loop and proves quality held. Test that with a savings audit before building a product.

## What routing covers

| Level | Decision | When it is made | Examples |
| - | - | - | - |
| 1. Gateway | Which provider or endpoint serves this model | Per request | Failover on 429/503 or a retired model; cheapest host for the same open-weight model; US-only endpoint; Priority tier for interactive traffic; budget caps |
| 2. Turn | Which model and effort start this turn | Once per user message | A cheap classifier or heuristics judge difficulty; simple questions go to a Flash model |
| 3. Step | Which model runs each role inside the loop | At role boundaries | Frontier model plans, cheap model executes tool-heavy steps; sub-agents and titles on Flash; escalate after failures; cheap draft with frontier review |
| 4. Learned | A model predicts pass probability per candidate | Offline training, online use | Trained on eval results keyed by task features and `HarnessConfig` |
| Policy (cuts across all) | Which models are allowed at all | Per tenant or session | Data-sensitivity and residency rules |

Level 1 is what gateways already sell. Levels 2–4 need the loop and the evals, which is where we differ.

## Constraints that shape routing in an agent loop

- **Switching models throws away the prompt cache.** Caches are per provider and per model. The first step after a switch reads the whole context uncached.
- **Reasoning does not transfer.** Reasoning blocks are dropped when the target model differs from the source ([FIREWORKS_RESEARCH.md](../FIREWORKS_RESEARCH.md), replay rule 3). A switch in the middle of a tool chain loses the chain of thought.
- **Tool-call quality varies between models.** A router needs per-model results from the conformance suite, not just prices.
- **Effort is a second dial.** Lowering effort on the same model may be cheaper than switching. Whether changing effort keeps the cache is not confirmed for any provider; measure it.

These point to one rule: **route at boundaries (turn start, sub-agent spawn), not on every step**, and try effort before model.

### What a switch costs

Input cost of one step at a 100k-token context, plus 1k output tokens:

| | Kimi K3.1 Pro | DeepSeek V4.1 Flash 1017 |
| - | - | - |
| Cached read of 100k | $0.020 | $0.0006 |
| Uncached read of 100k (first step after a switch) | $0.20 | $0.03 |
| 1k output tokens | $0.010 | $0.0012 |

- Switching **down** to DeepSeek costs $0.03 once and saves about $0.019 per step on input, so it pays back within 2 steps.
- Switching **up** to Kimi costs $0.20 once, the same as 10 cached Kimi steps. Escalation should be rare and deliberate.

## As a feature

```python
RoutingPolicy(
    roles: dict[Role, list[str]],          # ordered candidates per role: planner, worker, subagent, utility
    stickiness: Literal["session", "turn", "role"],
    escalate_on: set[Signal],              # tool_error_streak, malformed_args, verifier_fail, max_steps
    max_cost_per_turn_usd: float | None,
    allowed_providers: set[str] | None,    # data-policy and residency constraint
)
```

It lives in `HarnessConfig`, so it is hashed into every eval result and two policies can be compared on the same suite.

**What the harness needs first.** The first three rows are now part of phase 1 in [HARNESS_CORE.md](../HARNESS_CORE.md); failover stays with routing in phase 5.

| Change | Where | Why |
| - | - | - |
| Prices (input, cached, cache write, output), context window and capability flags per model | `ModelSpec`, from config | Cost and eligibility can't be computed without them. |
| `Usage.cache_write_input_tokens` | `llm/types.py`, `AnthropicProvider` | Cache writes are folded into `input_tokens` today, which counts them but can't price them separately. |
| Cost per assistant message and per turn | `chat_messages`, loop | The number routing optimises and the UI shows. |
| Failover to the next candidate | `Gateway` | Retry before the first token; after partial output, restart the step. |
| Cross-provider replay | Harness phase 1 | Already specified: ID sanitising and reasoning dropping. |

### Experiment ladder

Each rung is measured on the agent-task suite as cost per passed task and pass rate against a single-frontier-model baseline.

| Rung | Policy | What it teaches |
| - | - | - |
| R0 | Static role map, no switching within a session | Baseline cost per model |
| R1 | Failover chain | Reliability under 429/503 |
| R2 | Effort routing on one model | How much effort alone saves, and its cache effect |
| R3 | Difficulty classifier at turn start | Whether cheap triage is accurate enough |
| R4 | Escalate on failure signals | Which signals predict a failing run early |
| R5 | Sub-agents on cheap models | Savings from isolating context per role |
| R6 | Learned router from eval data | Whether prediction beats the hand-written rules |

Also track cache hit ratio, switches per turn, escalation rate and p50/p95 latency.

## As a wedge

| Packaging | What the customer does | Build cost | Assessment |
| - | - | - | - |
| A. Routed endpoint | Points their OpenAI- or Anthropic-compatible client at us | Medium | Head-on with existing gateways. We don't own their loop, so the agent-aware part is hard to deliver. |
| B. Savings audit | Sends traces or a task set; gets a report of cost per passed task on cheaper configurations | Low | Best first test. Reuses the eval runner and sells evidence, which is the hard part. |
| C. Routed harness | Runs agents on our harness with routing included | High | The full product. Only worth it if B shows demand, and it merges with the other wedges. |

**Why it is weak alone:** frontier prices keep falling, labs add their own auto modes, failover is a commodity, and teams with a bill large enough to care usually have engineers who can do this. The durable part is the evidence that quality held, so lead with that.

## Validation experiment: savings audit

- **Who:** 10 teams running agents in production who complain about the bill. Likely seed to Series B AI-native startups.
- **Offer:** send 30–50 representative traces or a task set. We replay them on 3–4 cheaper configurations, grade the outcomes, and return which task types are safe to downgrade and what it saves.
- **Needs:** harness phase 1 and the replay part of phase 4. The first two audits can be partly manual.
- **Strong signals:** they share real traces, act on the report, or ask for it to keep running.
- **Kill if:** fewer than 2 of 10 will share traces; or savings at equal pass rate come in under about 30%; or they implement the findings themselves in an afternoon, which makes it a consulting service and not a product.

## Competition

- **Routers and gateways:** OpenRouter, Not Diamond, Martian, Portkey, LiteLLM, Cloudflare and Vercel AI Gateway.
- **Cloud platforms:** Bedrock's prompt routing, Azure's model router.
- **Open source:** RouteLLM.
- **Labs:** automatic model selection in their own products.

As far as I know these route single requests. None owns the agent loop or grades task outcomes.

## Risks

| Risk | Mitigation |
| - | - |
| Savings claims without quality proof are not believed | Always report pass rate next to cost, on the customer's own tasks. |
| Customers won't share traces | Offer to run inside their environment, or on a synthetic task set they write. |
| Routing adds failure modes (mid-turn switches, lost reasoning) | Boundary-only switching; the cross-provider replay tests in phase 1. |
| Price changes erase the gap | Prices are config; rerun the suite when they move. |

## Open questions

- Does changing effort keep the prompt cache on Anthropic, OpenAI and Fireworks?
- Is a routed turn exposed to the user (which model answered) or hidden?
- Does the audit accept traces from other harnesses, and in what format?

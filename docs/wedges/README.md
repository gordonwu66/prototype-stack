# B2B wedges

Status: hypotheses only, no customer conversations yet. Written 2026-11-09. Competitor names are from memory and were not re-researched; check them before outreach.

Each doc is one candidate wedge for B2B outreach and market validation. They all sit on the harness in [HARNESS_CORE.md](../HARNESS_CORE.md); "needs" below refers to its phases.

## The wedges

| Doc | Pitch | Buyer | Needs | Crowded | Verdict |
| - | - | - | - | - | - |
| [MODEL_ROUTING.md](MODEL_ROUTING.md) | The same task pass rate for a fraction of the agent bill, with evidence. | Engineering lead with a growing LLM bill | Phases 1, 4 | Gateways: very. Agent-aware routing: less. | Build as a feature now. Test the wedge with a savings audit. |
| [PRIVATE_WORKSPACE.md](PRIVATE_WORKSPACE.md) | An agent workspace your compliance team can approve. | IT or ops lead in a regulated mid-size firm | Phase 2 | Medium | Test first. |
| [EMBEDDED_AGENT.md](EMBEDDED_AGENT.md) | An agent inside your product, built from your API spec. | CTO or product lead at a B2B SaaS without an AI team | Phase 2 | Medium to high | Test first. |
| [VERTICAL_WORKFLOW.md](VERTICAL_WORKFLOW.md) | One back-office workflow done by an agent, with a human approving. | Operations lead in one industry | Phases 2–3 | Depends on the vertical | Test once a vertical with reachable buyers is picked. |
| [INTEGRATION_VAULT.md](INTEGRATION_VAULT.md) | Credentials, permissions and audit for agent tool calls. | Team building its own agents | Phase 3 and later | High | Don't test alone. Ask about it in the other calls. |

**Parked:** a general persona builder with isolated docs. It is the most crowded option and only makes sense inside one of the wedges above.

## Routing runs through all of them

Routing is listed as a wedge, but it is also the feature every other wedge leans on:

- **Private workspace:** route by data policy, so sensitive sessions stay on zero-retention open-weight models.
- **Embedded agent:** our margin on a per-seat or per-conversation price is the gap between what the customer pays and what the routed model costs.
- **Vertical workflow:** background jobs are not latency-sensitive, so they can run on the cheapest model that passes the evals.

So the routing feature gets built whichever wedge wins. Only the standalone wedge needs its own validation.

## Shared validation method

For each wedge:

1. **Build one artifact** that shows the product, not slides. Each doc names it.
2. **List 15 buyers** you can reach this week, and aim for 10 conversations.
3. **Count costly signals only.** A strong signal is the buyer giving something up: real data, an API key, an engineer's time, a paid pilot or a signed letter of intent. "Interesting, keep me posted" counts as a no.
4. **Decide after 10 calls.** Each doc has a kill criterion. The thresholds are my guesses; set your own before the first call and don't move them afterwards.

## Suggested order

1. Finish harness phases 1–2. Every artifact needs a working tool loop.
2. Run **private workspace** and **embedded agent** in parallel. Both demos are small additions to phase 2, and they reach different buyers.
3. Run the **routing savings audit** once phase 4 evals exist. It reuses the eval runner almost unchanged.
4. Pick up **vertical workflow** if calls in step 2 keep pointing at the same workflow.

## What would change this order

- You already have warm access to buyers in one industry: start with the vertical workflow.
- You have access to teams with large agent bills: move the savings audit to the front, since it is the cheapest to run.
- Buyers in step 2 keep asking who holds the credentials: the integration vault moves from a feature to a candidate.

# Private agent workspace for regulated mid-market

Status: hypothesis, nothing built. Written 2026-11-09.

## Pitch

An agent workspace your compliance team can approve: models with zero data retention, a choice of where data is processed, an audit log of every tool call, and admin control over which tools and models staff can use.

## Buyer and pain

- **Buyer:** IT, operations or compliance lead at a 50–500 person firm in legal, healthcare administration, financial services or similar.
- **Pain:** staff want ChatGPT or Claude; policy bans or restricts them; the approved alternative is weak. The firm is too small for a negotiated enterprise contract with a lab and has no team to build its own.

## What the stack already gives

- Open-weight models through Fireworks with zero data retention by default on Chat Completions, and a US-only endpoint at about 50% more ([FIREWORKS_RESEARCH.md](../FIREWORKS_RESEARCH.md)).
- We own conversation state in our own Postgres; nothing is stored at the provider (`store: false` on OpenAI).
- Org-scoped tenancy is already planned through Clerk Organizations ([SYSTEM.md](../SYSTEM.md)).
- Every tool call is already a stored block, so an audit log is a query, not a new system.

## Smallest demo

On top of harness phase 2:

- An org-level model allowlist restricted to zero-retention models.
- Document upload into a session (the `agent_docs` entity in [SYSTEM_DESIGN.md](../SYSTEM_DESIGN.md)).
- An audit view: who asked what, which model answered, which tools ran.
- A per-org switch that turns web tools off.

## Routing angle

Policy routing from [MODEL_ROUTING.md](MODEL_ROUTING.md): `allowed_providers` per org, and optionally a rule that sessions with uploaded documents never leave the zero-retention set.

## Validation experiment

- **Who:** 10 IT or compliance leads in one regulated industry. Pick one industry so the calls are comparable.
- **Artifact:** the demo above, plus a one-page data-flow diagram showing where each byte goes.
- **Questions to settle:** what is banned today and why; who signs off; which certifications are required before a pilot; whether cloud-hosted is acceptable or it must run in their account.
- **Strong signals:** they bring compliance into a second call, send a security questionnaire, or agree to a paid pilot.
- **Kill if:** most say Bedrock, Azure OpenAI or an existing enterprise plan already solves it; or SOC 2 or a HIPAA agreement is a hard gate before any pilot.

## Competition

- **Lab enterprise plans:** ChatGPT Enterprise, Claude Enterprise, Microsoft Copilot.
- **Frontier models inside a cloud account:** Bedrock, Azure OpenAI, Vertex.
- **Self-hosted chat UIs:** Open WebUI, LibreChat, Onyx.
- **Vertical players:** Harvey and similar in legal.

"Private" alone is not unique. The angle is the combination: agent tools with audit, mid-market price, and deployable in the customer's own cloud account.

## Risks

| Risk | Mitigation |
| - | - |
| Compliance certifications cost months and money we don't have | Offer deployment into the customer's account so their controls apply; find out in calls whether that is enough. |
| Open-weight quality disappoints users who have seen frontier models | Eval suite per model; allow frontier models through the customer's own Bedrock or Azure keys. |
| Long sales cycles | Sell to firms small enough that one person decides. |

## Open questions

- Which industry first?
- Hosted by us, or deployed in the customer's cloud account from day one?
- Is bring-your-own-key for frontier models part of the first version?

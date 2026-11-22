# Embedded agent for SaaS products

Status: hypothesis, nothing built. Written 2026-11-09.

## Pitch

Give us your OpenAPI spec and we give you an agent inside your product: it acts through your API as the signed-in user, asks before it changes anything, and you never build a tool loop.

## Buyer and pain

- **Buyer:** CTO or head of product at a 20–200 person B2B SaaS with a documented API and no AI team.
- **Pain:** customers and the board ask for an AI assistant. Building the loop, tool auth, streaming UI, approvals and evals is months of work outside their core product.

## What the stack already gives

- A tool registry where a new tool source only has to produce `ToolSpec`s ([HARNESS_CORE.md](../HARNESS_CORE.md)).
- Permission modes and an approval flow: `ask` mode maps directly onto "confirm before any write".
- A streaming protocol with resume that a widget can speak unchanged.
- Model-neutral cost, so we can price per seat or per conversation and keep the routing margin ([MODEL_ROUTING.md](MODEL_ROUTING.md)).

## Smallest demo

On top of harness phase 2, about 2–3 days:

- **OpenAPI to tools:** one tool per operation, `GET` marked read-only, everything else requiring approval. An operation allowlist keeps the tool count small.
- **User token passthrough:** the host app hands the widget the end user's API token; tools call the customer's API with it. We store no customer credentials.
- **Widget:** an iframe or React component that speaks our Socket.IO protocol.

## Validation experiment

- **Who:** 10 SaaS companies with a public OpenAPI spec and a free trial or sandbox.
- **Artifact:** the demo built on *their* API before the call, sent as a short screen recording.
- **Strong signals:** an engineer joins a second call, they hand over a sandbox key, or they ask about pricing and data handling.
- **Kill if:** fewer than 3 of 10 take a second call; or the common answer is "we'll ship an MCP server and let users bring their own assistant".

## Competition

- **Build-it-yourself kits:** CopilotKit, assistant-ui, Vercel AI SDK.
- **Support-focused agents:** Intercom Fin, Decagon.
- **MCP itself:** the vendor ships an MCP server and the user's own Claude or ChatGPT becomes the interface. This is the biggest threat because it removes the need for an embedded UI.

## Risks

| Risk | Mitigation |
| - | - |
| Large specs flood the model with tools | Operation allowlist first; tool search and deferred loading later. |
| A wrong write damages a customer's customer | Approval on every non-`GET` call by default; per-operation policy. |
| Raw API operations make poor tools (bad descriptions, pagination, huge responses) | Result truncation from the harness; let the customer edit tool descriptions; measure with a per-customer eval set. |
| Each prospect demo is custom work | The converter makes it mostly automatic; cap effort at half a day per prospect. |

## Open questions

- Is the product the widget, or a headless API the customer wraps in their own UI?
- Per-seat, per-conversation or usage-based pricing?
- Do we also emit an MCP server from the same spec, turning the threat into a feature?

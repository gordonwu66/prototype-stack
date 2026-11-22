# Integration vault

Status: hypothesis, nothing built. Written 2026-11-09.

## Verdict

Don't pursue this as a standalone wedge yet. It is crowded, and holding customers' OAuth tokens demands security certification from day one. Build it as a feature when another wedge needs it, and use the other wedges' calls to learn whether it deserves more.

## Pitch

Credentials, permissions and audit for agent tool calls: each tenant's users connect their accounts once, tokens never reach the model, every tool call is checked against policy and logged.

## Buyer and pain

- **Buyer:** an engineering team building its own agents.
- **Pain:** per-user OAuth for each provider, token refresh, scope management, deciding which tools an agent may call for which user, and proving afterwards what it did.

## What it would be

- A managed MCP gateway: tools from many servers behind one endpoint.
- A per-tenant, per-user credential vault with refresh handled server-side.
- Tool-level policy: allow, ask or deny, by tenant, user and tool. This is the permission model in [HARNESS_CORE.md](../HARNESS_CORE.md) extended to outside tools.
- An audit log of every call with arguments and results.

## Where it shows up in the other wedges

| Wedge | What it needs from this |
| - | - |
| [PRIVATE_WORKSPACE.md](PRIVATE_WORKSPACE.md) | Admin control over which integrations staff can connect; audit. |
| [EMBEDDED_AGENT.md](EMBEDDED_AGENT.md) | Nothing at first (user token passthrough). Needed once the agent reaches third-party systems. |
| [VERTICAL_WORKFLOW.md](VERTICAL_WORKFLOW.md) | One or two integrations into the system of record, with service credentials. |

## Validation

No separate experiment. In every call for the other wedges, ask:

- Which systems would the agent need to reach?
- Who would be allowed to connect them, and who approves?
- Would you let a vendor hold those tokens, or must they stay in your account?

Promote this to its own wedge if the answers keep naming the same gap that existing vendors don't fill.

## Competition

Composio, Arcade, Pipedream Connect, Nango, Paragon and Merge, plus the connectors built into the labs' own products. The contest is catalogue breadth and trust, neither of which we have.

## Risks

| Risk | Mitigation |
| - | - |
| A token leak is a company-ending event | Don't hold third-party tokens until a wedge requires it; prefer passthrough or customer-hosted storage. |
| Catalogue breadth is an endless treadmill | Support MCP servers generically instead of writing connectors. |
| Tool results from outside systems carry prompt injection | Default outside tools with side effects to `ask`; revisit the harness risk table before shipping. |

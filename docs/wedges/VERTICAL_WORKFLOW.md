# One vertical background workflow

Status: hypothesis, no vertical chosen. Written 2026-11-09.

## Pitch

One recurring back-office workflow, done by an agent in the background, with a person approving the result. Sold on the outcome (items handled), not on the harness.

## Buyer and pain

- **Buyer:** the operations lead who owns the workflow and its headcount.
- **Pain:** a queue of repetitive document or email work that grows with the business, where mistakes are costly enough that full automation is not trusted.

## Choosing the vertical

This doc can't pick it; it depends on which buyers you can reach. Criteria:

- You can get 10 buyers on a call within two weeks.
- Input is documents, email or tickets; output is a draft, a structured record or an action in one system.
- A human approving each item is acceptable.
- The outcome is countable, so pricing per item is possible.
- The work is not time-critical, so it can run on the cheapest model that passes.

Candidates to pressure-test, not recommendations: security questionnaires and RFP answers, accounts-payable invoice exceptions, insurance claims intake, support ticket triage and drafting, logistics email operations. Several are already crowded.

## What the stack already gives

- Async runtime with background jobs is a stated requirement ([SYSTEM_DESIGN.md](../SYSTEM_DESIGN.md)); Procrastinate is the chosen queue ([SYSTEM.md](../SYSTEM.md)).
- The approval flow from [HARNESS_CORE.md](../HARNESS_CORE.md) becomes the review queue.
- Evals per workflow give the accuracy number buyers ask for first.

## Smallest demo

On top of harness phases 2–3:

- A scheduled or inbox-triggered run with no user in the chat.
- A review queue: each item shows the agent's draft, its sources and approve / edit / reject.
- One integration into the system of record, or a CSV export if that is too much for a demo.

The first customers can be served by hand behind the queue to learn the workflow before automating it.

## Routing angle

Background work tolerates latency, so the policy in [MODEL_ROUTING.md](MODEL_ROUTING.md) can default to the cheapest passing model, use batch pricing where offered, and escalate only items that fail a verifier.

## Validation experiment

- **Who:** 10 operations leads in the chosen vertical.
- **Artifact:** the review queue running on 20 of *their* real items, anonymised if needed.
- **Strong signals:** they hand over real items, name a price per item, or agree to a paid pilot on a slice of the queue.
- **Kill if:** they won't share sample items; or the accuracy they require is beyond what the eval set shows; or an incumbent tool already does it inside their system of record.

## Risks

| Risk | Mitigation |
| - | - |
| Picking a vertical with no access to buyers | Apply the first criterion strictly before building anything. |
| The harness becomes irrelevant to the sale | Accept it; this wedge validates a market, not the harness. |
| Integration into legacy systems dominates the work | Start with export and email; integrate after a paid pilot. |
| Runs must survive restarts | Durable runs are harness phase 5; fine for a demo, required before production. |

## Open questions

- Which industries do you have warm introductions in?
- Is per-item pricing acceptable to the buyer, or do they expect a seat licence?

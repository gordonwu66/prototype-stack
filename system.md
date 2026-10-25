# Prototype Stack — System Design

A lean, general-purpose stack for prototyping web apps and startup ideas (agent chat apps, SaaS) using modern system design principles without premature complexity.

## Committed decisions

- **FastAPI is the only backend.** It serves all API endpoints: basic CRUD, AI workflows, jobs, and integrations. There is no Fastify/Hono service and no business logic in Next.js route handlers.
- **Postgres on AWS RDS** is the only datastore. It also holds vectors (pgvector).
- **Alembic is the only migration tool.** Python owns the schema.
- **Next.js is UI only.** It renders pages and calls FastAPI. It does no database access and holds no business logic.
- **Clerk** for auth, **Vercel** for Next.js hosting. Nothing outside the VPC needs database access, so RDS stays private.

## Guiding principle

**One backend, one schema owner, one typed contract.** CRUD is trivial in FastAPI, so splitting it into a TS service would mean two runtimes, two models of the same tables, and two deploys for no benefit. Add infrastructure only when something forces it.

## Architecture

```
            Clerk (sign-in, sessions, JWKS)
               ▲                      ▲ JWKS (cached)
Browser ──► Next.js on Vercel ──server-side fetch + JWT──► FastAPI on ECS ──► RDS Postgres
   │        (UI only)                                      ▲   (private VPC)
   └──── TanStack Query / useChat (SSE) + JWT ─────────────┘
```

Data-flow rules:
- **Server components and server actions** call FastAPI server-side and forward the user's JWT.
- **Client components** call FastAPI directly through the generated client and TanStack Query.
- **Chat** (`useChat`) streams directly from FastAPI. Next.js never proxies long-lived streams.
- **FastAPI** verifies Clerk JWTs statelessly against Clerk's JWKS and has no session logic of its own.
- Tokens travel as `Authorization: Bearer`, never in cookies, because Vercel and the API are on different origins.

## Stack

### Repo & tooling
- **pnpm workspace** for the TS side. Turborepo is unnecessary with a single TS app.
- **uv** for Python
- **mise** pins Node and Python versions and runs cross-language tasks (`mise run dev`, `mise run codegen`)
- **Biome** for TS lint/format; **ruff + pyright** for Python
- **pytest** (API), **Vitest** (UI logic), and **Playwright** for a few e2e smoke tests

### Frontend
- **Next.js 16** (App Router), **Tailwind v4**, **shadcn/ui**
- **TanStack Query** with the generated API client (hey-api's TanStack Query plugin)
- **Vercel AI SDK UI** (`useChat`) for chat. FastAPI emits the AI SDK UI message stream protocol via Pydantic AI's Vercel AI adapter. Pin the AI SDK major version because the protocol changes between majors.
- **@clerk/nextjs**: `clerkMiddleware()` in `proxy.ts` (Next 16's renamed middleware) and prebuilt sign-in/user components
- **@t3-oss/env-nextjs** for typed env

### Backend
- **FastAPI** + **Pydantic v2**, one router per domain (`users`, `projects`, `chat`, …)
- **SQLAlchemy 2 (async) + asyncpg**, with a normal connection pool. FastAPI is a persistent service, so RDS Proxy is not needed.
- **Alembic** for migrations. Autogenerate, then review every migration before applying it.
- **pydantic-settings** for typed config

### Data
- **AWS RDS Postgres** (16+) with **pgvector**, in private subnets
- Local: docker-compose `pgvector/pgvector` image pinned to the same Postgres major version as RDS
- One database role per service with least privilege. Migrations run under a separate owner role.
- **ElastiCache (Valkey)** only when needed (resumable streams, rate limits, pub/sub)

### Auth (Clerk)
- **Getting a token:** server side, `await (await auth()).getToken()`; client side, `useAuth().getToken()`. Attach it to every API call through the generated client's request interceptor.
- **Verifying in FastAPI:** a single `current_user` dependency uses **PyJWT** + `PyJWKClient` with cached keys. It checks the signature, `exp`/`nbf`, `iss` (your Clerk Frontend API URL), and `azp` (an allowlist of your web origins).
- **Short-lived tokens:** Clerk session tokens last about 60s. The client SDK refreshes them automatically. SSE streams verify once at connection start, so long streams aren't affected.
- **User records:** `app.users` keyed by Clerk user ID (`sub`), upserted lazily on the first authenticated request. Clerk webhooks (`user.updated`, `user.deleted`) go to `POST /webhooks/clerk` on FastAPI and are verified with the **svix** library.
- **Multi-tenant (B2B):** use **Clerk Organizations**. The active org ID is in the session token; FastAPI scopes queries by it.
- **Extra claims** (e.g. email) go in Clerk's session-token customization, not JWT templates. Keep the token small.
- **Instances:** Clerk dev instance for local and Vercel preview deploys; production instance on your real domain (Clerk prod requires it).

### API contracts
- FastAPI's OpenAPI spec → **hey-api** → `packages/api-client` (typed client + TanStack Query hooks)
- Regenerate with `mise run codegen`; CI fails if the generated client is stale

### Background jobs
- **Procrastinate** (Postgres-backed, runs on RDS) to avoid new infrastructure
- Next.js enqueues jobs by calling a FastAPI endpoint, never by writing to the queue directly
- Graduate to **Temporal / Inngest** only when durable multi-step workflows are needed

### AI-specific
- **Pydantic AI** or the provider SDK directly
- Persist messages and tool calls in Postgres
- **Langfuse Cloud** or **Pydantic Logfire** for LLM traces. Self-hosted Langfuse needs ClickHouse, Redis, and S3, which is not lean.
- **Pydantic Evals** (or Langfuse datasets) for evals

### Ops & hosting
- **FastAPI on ECS Fargate** in the same VPC as RDS, behind an ALB. Raise the ALB idle timeout (e.g. 300s+) and send SSE heartbeats so streams aren't cut.
- **Next.js on Vercel.** `app.example.com` → Vercel, `api.example.com` → ALB. Preview deploys use the staging API + Clerk dev instance.
- **CORS on FastAPI:** the production origin plus a regex for your Vercel preview URLs; allow the `Authorization` header
- Secrets in **AWS Secrets Manager / SSM**; infra as code (**SST v3** or **Terraform**)
- **Sentry** from day one in both apps; **OpenTelemetry** later

## Repository structure

```
apps/
  web/              Next.js (UI only)
  api/              FastAPI (pyproject, uv) — CRUD + AI + jobs
    alembic/        migrations (sole schema owner)
packages/
  api-client/       generated from FastAPI OpenAPI (hey-api)
  config/           tsconfig, biome presets
infra/
  docker-compose.yml   postgres+pgvector (+ valkey)
  ...                  IaC for VPC, RDS, ECS, ALB
pnpm-workspace.yaml
mise.toml              tool versions + tasks (dev, codegen, migrate)
.env.example
```

## Deliberately skipped

A second backend (Fastify/Hono), a TS ORM or any TS database access, business logic in Next.js route handlers, self-hosted auth, GraphQL, Kafka, Kubernetes, Turborepo, a shared `ui` package (until a second frontend exists), and heavy abstraction frameworks (LangChain-style).

## Accepted trade-offs

- **Clerk lock-in:** user identities live in Clerk. Mitigation: keep only the Clerk ID as a foreign key in `app.users`, and keep app data in Postgres.
- **Cross-origin setup:** separate web and API origins mean CORS and bearer tokens. In return, Next.js never needs a database connection, and RDS never needs a public endpoint.

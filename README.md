# prototype-stack

Next.js frontend (`apps/web`) and FastAPI backend (`apps/api`) in one repo. See [docs/SYSTEM.md](docs/SYSTEM.md) for the stack design.

## Prerequisites

- Node + pnpm
- [uv](https://docs.astral.sh/uv/) (installs Python 3.14 if needed)
- Docker, only for running the API tests against Postgres

## Setup

```bash
pnpm install
cd apps/api && uv sync
cp .env.example .env   # then add at least one LLM provider
```

Chat history lives in Postgres when `DB_HOST` is set, and in memory otherwise. Document search (`/collections`, `/documents`, `POST /search`; design in [docs/HYBRID_SEARCH.md](docs/HYBRID_SEARCH.md)) needs Postgres, and uses OpenAI embeddings when `OPENAI_API_KEY` is valid, or BM25 alone otherwise. To connect the dev RDS instance, follow [infra/rds/README.md](infra/rds/README.md), then run:

```bash
pnpm db:migrate
```

## Development

```bash
pnpm dev:web   # Next.js on http://localhost:3000
pnpm dev:api   # FastAPI on http://localhost:8000 (docs at /docs)
```

| Command | What it does |
| - | - |
| `pnpm db:migrate` | Applies migrations to the database in `apps/api/.env`, as `DB_MIGRATION_USER`. |
| `pnpm db:revision "<message>"` | Autogenerates a migration from `apps/api/src/api/db/models.py`. Review it before applying. |
| `pnpm db:cert` | Downloads the RDS CA bundle used to verify TLS. |
| `pnpm test:api` | API tests on the in-memory store. |
| `pnpm db:test:up` then `pnpm test:api:db` | The same tests against a throwaway Postgres in Docker. |

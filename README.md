# prototype-stack

Next.js frontend (`apps/web`) and FastAPI backend (`apps/api`) in one repo. See [system.md](system.md) for the stack design.

## Prerequisites

- Node + pnpm
- [uv](https://docs.astral.sh/uv/) (installs Python 3.14 if needed)

## Setup

```bash
pnpm install
cd apps/api && uv sync
```

## Development

```bash
pnpm dev:web   # Next.js on http://localhost:3000
pnpm dev:api   # FastAPI on http://localhost:8000 (docs at /docs)
```

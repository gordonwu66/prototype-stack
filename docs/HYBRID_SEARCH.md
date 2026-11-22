# Hybrid search — spec

Status: phases 0 and 1 built 2026-11-20 (tables, documents CRUD, ingest, embedder, hybrid search; see [Phases](#phases) for what's left). Written 2026-11-20. RDS facts were checked that day against the AWS extension list for RDS PostgreSQL 18.6. Upgrade-path facts were checked against the ParadeDB docs, the pg_textsearch README (v1.5.1) and the pgvector README (v0.8.7). Reranker prices come from third-party roundups that disagree with each other; check the vendors' pages before quoting them.

**Goal:** one search system over our documents, served two ways: a REST endpoint for the web app and a set of read-only tools for the agent harness. Retrieval is BM25 and pgvector on the same table, both result lists merged with Reciprocal Rank Fusion (RRF), and an optional reranker over the top 50. Everything lives in the existing dev RDS Postgres instance, next to the chat tables, and the search indexes change in the same transaction as the data they index.

Builds on [SYSTEM.md](SYSTEM.md) (Postgres, Alembic, roles), [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) (entities, API) and [HARNESS_CORE.md](HARNESS_CORE.md) (tool protocol, evals). [Changes to existing docs](#changes-to-existing-docs) lists what this spec changes in each of them.

## Decisions

- **One database.** The dev RDS instance holds the chat tables (replacing the in-memory `ChatStore`) and the search tables. There is no second datastore and no sync pipeline.
- **One function, two consumers.** `search.service.search()` does all retrieval. `POST /search` and the `search_docs` tool are thin wrappers around it, in the same way the agent loop has two consumers (Socket.IO and the eval runner).
- **One table, two indexes.** `chunks` holds the text, a generated `tsvector` and the embedding. A GIN index covers the `tsvector` and a pgvector HNSW index covers the embedding.
- **BM25 is computed in SQL.** RDS has no BM25 extension (see [below](#database-the-dev-rds-instance)). The GIN index finds candidate chunks, and a term-statistics view supplies IDF and average length for the standard BM25 formula. If we later leave RDS, an index-native BM25 extension replaces one CTE ([Appendix](#appendix-upgrading-to-an-index-native-bm25)).
- **Fusion happens in SQL.** One statement runs both legs, ranks each one and fuses them with RRF. Only ranks are fused, never raw scores, so the two legs never need calibrating against each other.
- **The reranker is optional and runs in the API.** It is a model call over the top 50 fused results, behind a small `Reranker` protocol, with a timeout that falls back to RRF order. Whether it is on by default is decided by the retrieval eval, not assumed.
- **Chunks are immutable.** When a document changes, its chunks are replaced. An embedding therefore always matches its row's text, so stale embeddings can't happen.
- **A NULL embedding is the queue.** New chunks commit with `embedding = NULL` and are searchable by BM25 immediately. An in-process embedder fills in vectors. The semantic leg skips NULLs, so a half-embedded document is still findable.
- **Ownership is global for now.** There are no users or orgs yet, so every collection, document and session is visible to everyone. Filters narrow results; they are not access control. [Ownership later](#ownership-later) describes the change when auth lands.
- **Search settings are one frozen object** (`SearchConfig`). It is hashed into `HarnessConfig`, so retrieval ablations work like any other harness ablation.

## Database: the dev RDS instance

All tables go in one database on the existing dev RDS instance. This is what RDS PostgreSQL 18.6 offers for search, from the AWS extension list:

| Need | On RDS | Used for |
| - | - | - |
| pgvector | 0.8.2 listed; the dev instance (18.3) runs 0.8.1. Both have `halfvec` and iterative index scans. | Semantic leg |
| A BM25 extension (`pg_search`, `pg_textsearch`, `vchord_bm25`) | None | — |
| Full-text search (`tsvector`, GIN, `ts_stat`) | Built in | Lexical leg, with BM25 scoring computed in SQL |
| `pg_trgm` 1.6, `pg_bigm` | Yes | Not in v1. Candidates for typo tolerance or CJK text later. |

**What computing BM25 in SQL gives up.** The ranking formula is the one Lucene uses (`k1 = 1.2`, `b = 0.75`). What's missing compared with an index-native engine is top-k pruning: every chunk that matches any query term gets scored. That's fine at dev scale. Phase 1 measures the lexical leg's p95 latency, and that number is the trigger for the [upgrade path](#appendix-upgrading-to-an-index-native-bm25).

**Setup:**
- **Engine:** the dev instance runs RDS PostgreSQL 18.3; `uuidv7()` needs 18. If the instance is on 17, generate ids in Python (`uuid.uuid7()`, which `ChatMessage` already uses) and drop the `DEFAULT uuidv7()` clauses.
- **Connection** (built; see [infra/rds/README.md](../infra/rds/README.md)): the `DB_*` settings in `apps/api/.env`. TLS is verified against the RDS CA bundle (`DB_SSLMODE=verify-full`, `pnpm db:cert`). RDS IAM authentication is available as an option (`DB_IAM_AUTH`). If the instance is not publicly accessible, reach it through SSM port forwarding via a host in the VPC. Don't open the security group to the internet.
- **Roles** follow SYSTEM.md: one owner and one runtime role per service.
  - `app_owner` owns the schema and runs Alembic.
  - `app` is what the API connects as. It has DML on all tables. It refreshes the statistics views through `refresh_search_stats()`, a `SECURITY DEFINER` function owned by `app_owner`, so it needs no grant on the views and the migration names no roles.
  - `CREATE EXTENSION vector` needs `rds_superuser`. Run it once as the master user.
- **Migrations** run by hand (`pnpm db:migrate`), never on API startup. Startup checks that the schema is at head and stops if it isn't.
- **Pool:** SQLAlchemy async engine with a small pool (5). Small instance classes have low `max_connections`.
- **Tests never touch the shared dev instance.** pytest and CI use docker-compose with a `pgvector/pgvector` image pinned to pgvector 0.8.1 on Postgres 18, the same versions as the dev instance.

## Chat tables

These mirror today's `ChatSession` and `ChatMessage` field for field, so swapping `ChatStore` for a Postgres-backed store is mechanical. HARNESS_CORE phase 1 later migrates `content` and `reasoning` into a `content jsonb` block array. There is no `user_id` until auth lands.

```sql
CREATE TABLE chat_sessions (
  id          uuid PRIMARY KEY,                 -- generated by the client
  title       text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON chat_sessions (created_at DESC);

CREATE TABLE chat_messages (
  id            uuid PRIMARY KEY,               -- uuid7 from the API, so it sorts by time
  session_id    uuid NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
  role          text NOT NULL CHECK (role IN ('user', 'assistant')),
  content       text NOT NULL DEFAULT '',
  reasoning     text NOT NULL DEFAULT '',
  reasoning_ms  int,
  model         text,
  stop_reason   text,                           -- NULL while streaming
  error         text,
  usage         jsonb,
  seq           int NOT NULL DEFAULT 0,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON chat_messages (session_id, created_at);
```

- **Writes:** the user message is inserted on `chat:send`. The assistant placeholder is inserted when the reply starts, and the whole message is written once the reply ends, before the final `chat:message`. Deltas are never written per token. The in-flight message lives in memory with its task, and `session:join` merges it into the snapshot read from the database.
- **Restart:** on startup, assistant rows with a NULL `stop_reason` are reply placeholders whose stream died with the process. They get `stop_reason = "error"` and `error = "interrupted"`, so the UI never waits on them.
- **Still one API process.** Socket.IO rooms and in-flight tasks are in memory. Postgres makes history durable; more than one process still needs Socket.IO's Redis manager.

## Search data model

As built: [models.py](../apps/api/src/api/db/models.py) and migration [0002](../apps/api/alembic/versions/0002_search_tables.py). These add a partial index on pending chunks (`chunks_pending_idx`) and the `refresh_search_stats()` function to the design below.

`collections` replaces the planned `agent_docs` entity. It is a named group of documents with no owner yet. Search covers every collection unless the request narrows it.

```sql
CREATE EXTENSION IF NOT EXISTS vector;          -- once, as the master user

CREATE TABLE collections (
  id          uuid PRIMARY KEY DEFAULT uuidv7(),
  name        text NOT NULL UNIQUE,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE documents (
  id             uuid PRIMARY KEY DEFAULT uuidv7(),
  collection_id  uuid NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
  title          text NOT NULL,
  source         text NOT NULL CHECK (source IN ('upload', 'url', 'note')),
  uri            text,
  mime_type      text,
  content        text NOT NULL,            -- extracted markdown/plain text; the original file is not stored in v1
  content_hash   bytea NOT NULL,           -- sha256 of content; skip re-chunking when it is unchanged
  metadata       jsonb NOT NULL DEFAULT '{}',
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON documents (collection_id, created_at DESC);

CREATE TABLE chunks (
  id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  document_id      uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  collection_id    uuid NOT NULL,           -- copied from the document, so both legs can filter on it
  ord              int NOT NULL,            -- position in the document
  heading          text NOT NULL,           -- breadcrumb: "Title › Section › Subsection"
  content          text NOT NULL,
  token_count      int NOT NULL,            -- estimated tokens of heading + content; BM25's document length
  content_hash     bytea NOT NULL,          -- sha256(heading || content): embedding reuse key
  tsv              tsvector GENERATED ALWAYS AS (to_tsvector('english', heading || ' ' || content)) STORED,
  embedding        halfvec(1024),           -- NULL until the embedder fills it
  embedding_model  text
);
CREATE INDEX chunks_tsv_idx ON chunks USING gin (tsv);
CREATE INDEX chunks_embedding_idx ON chunks USING hnsw (embedding halfvec_cosine_ops);
CREATE INDEX ON chunks (collection_id);        -- lets the planner pick an exact scan for a small collection
CREATE INDEX ON chunks (document_id, ord);

-- BM25 statistics: document frequency per lexeme, plus corpus size and average length.
-- Schema-qualify the inner query: on Postgres 17+, materialized views are created and refreshed
-- with a restricted search_path, so an unqualified `chunks` fails with "relation does not exist".
CREATE MATERIALIZED VIEW lexeme_df AS
  SELECT word AS lexeme, ndoc AS df FROM ts_stat('SELECT tsv FROM public.chunks');
CREATE UNIQUE INDEX ON lexeme_df (lexeme);

CREATE MATERIALIZED VIEW corpus_stats AS
  SELECT 1 AS id, count(*)::float8 AS n, coalesce(avg(token_count), 1)::float8 AS avgdl FROM chunks;
CREATE UNIQUE INDEX ON corpus_stats (id);      -- required for REFRESH … CONCURRENTLY

-- OR-query from free text. Postgres does the quoting; user text is never concatenated into tsquery syntax.
CREATE FUNCTION or_tsquery(q text) RETURNS tsquery
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT replace(plainto_tsquery('english', q)::text, ' & ', ' | ')::tsquery
$$;
```

- **`tsv` is a generated column,** so it can never drift from `content`. The GIN index updates in the same transaction.
- **`halfvec(1024)`** stores 2 KB per vector, half the size of `vector`. HNSW indexes `halfvec` up to 4,000 dimensions. 1024 is a dimension most current embedding models can produce, either natively or by Matryoshka truncation.
- **Alembic:** write the extension, the HNSW index, the statistics views and `or_tsquery` by hand with `op.execute`, and keep them out of autogenerate with an `include_object` hook. Use `pgvector.sqlalchemy.HALFVEC` for the column type.
- **Sizing (rough):** about 4 KB of row plus vector per chunk, plus index overhead. Dev scale is far below what a small instance holds. Keep the HNSW index in memory.

## Write path: staying in sync

```
POST /collections/{id}/documents ── extract ── chunk ──► one transaction
                                                           ├─ upsert documents row
                                                           ├─ delete old chunks, insert new ones
                                                           │    (copy embedding where content_hash matches, else NULL)
                                                           └─ commit: tsv, GIN and HNSW update with the rows
                                     after commit ──► wake the embedder
                                                           ├─ embed NULL rows in batches ──► UPDATE … WHERE embedding IS NULL
                                                           └─ refresh BM25 statistics (debounced, at most every 30 s)
```

- **Extract.** Built: `.md` and `.txt` uploads, and JSON bodies. Not yet: HTML (needs the HTML-to-markdown converter `web_fetch` will bring) and text-layer PDFs. OCR is out of scope.
- **Chunk.** Split on headings first, then paragraphs, then sentences. Target about 400 tokens, with a hard maximum of 800 and about 50 tokens of overlap. Code blocks and tables stay whole when they fit under the maximum. v1 approximates tokens as characters ÷ 4.
- **What each stage sees.** The embedder and the reranker get `heading + "\n\n" + content`. BM25 sees the same text through `tsv`.
- **Replace, don't update.** On a document update, read the old chunks' `content_hash → embedding` map, delete them all, and insert the new chunks, copying embeddings whose hash matches. Editing one section re-embeds only that section's chunks. Chunk ids change, so citations use `(document_id, ord)`.
- **The embedder** is an asyncio task started in the FastAPI lifespan. It does three things:
  - **Wake-up:** an `asyncio.Event` set after each ingest commit, plus a 60 s timer as the safety net. The timer catches rows left NULL by a crash or a provider outage.
  - **Batch:** it reads up to 128 rows with `SELECT … WHERE embedding IS NULL ORDER BY id LIMIT 128` (served by the partial index `chunks_pending_idx`), calls the provider once, and writes the vectors back with `UPDATE … WHERE embedding IS NULL`. No transaction or lock is held during the API call, so a document edit never waits on the provider; a chunk replaced meanwhile is gone and its update matches nothing.
  - **Statistics:** it calls `refresh_search_stats()` (`REFRESH MATERIALIZED VIEW CONCURRENTLY` on both views) after ingests, at most every 30 s. Embedding and the refresh fail independently, so a provider outage never leaves BM25 weights stale. Failures back off exponentially, up to 5 minutes.

  Procrastinate (SYSTEM.md's job queue) replaces this loop once there is a worker service. Because the queue is just NULL rows, the swap doesn't change the data.
- **Delete** cascades from the collection to its documents and chunks, and every index updates in the same transaction.
- **Status for the UI.** `GET /documents/{id}` returns `status: "indexing" | "ready"` and `chunks_pending`, which is the count of NULL embeddings.
- **Statistics lag.** Between refreshes, a brand-new term has no `df` row and is scored as `df = 1`, which overweights it slightly for up to 30 s. Matching is never stale; only the weights are.
- **Changing the embedding model** means adding a new column (`embedding_v2 halfvec(d)`), backfilling it, running `CREATE INDEX CONCURRENTLY`, switching `SearchConfig`, and then dropping the old column. Never mix two models in one column.

## Read path

```
POST /search ──┐                                  ┌─ 1. embed query (skipped in lexical mode)
               ├──► search(query, filters, opts) ►├─ 2. one SQL statement: BM25 top 100 + HNSW top 100 → RRF → top 50
search_docs ───┘                                  └─ 3. optional rerank: 50 → top N (timeout → RRF order)
```

### The hybrid query

As built: [query.py](../apps/api/src/api/search/query.py). It is the statement below, plus an IDF clamp, with collection and document filters added only when a request sets them.

Run it in one transaction that starts with `SELECT set_config('hnsw.ef_search', '100', true), set_config('hnsw.iterative_scan', 'relaxed_order', true)`. `SET LOCAL` can't take bind parameters, and `set_config(..., true)` is its transaction-scoped equivalent. The collection predicate (marked `[filtered]`) is added only when the request narrows by collection, and the same goes for `document_ids`.

```sql
WITH query_terms AS (
  SELECT t.lexeme,
         ln(1 + (cs.n - coalesce(d.df, 1) + 0.5) / (coalesce(d.df, 1) + 0.5)) AS idf
  FROM unnest(tsvector_to_array(to_tsvector('english', :q))) AS t(lexeme)
  CROSS JOIN corpus_stats cs
  LEFT JOIN lexeme_df d USING (lexeme)
),
lexical AS (
  SELECT c.id,
         sum(q.idf * cardinality(u.positions) * (:k1 + 1)
             / (cardinality(u.positions) + :k1 * (1 - :b + :b * c.token_count / cs.avgdl))) AS score
  FROM chunks c
  CROSS JOIN corpus_stats cs
  CROSS JOIN LATERAL unnest(c.tsv) AS u(lexeme, positions, weights)
  JOIN query_terms q ON q.lexeme = u.lexeme
  WHERE c.tsv @@ or_tsquery(:q)
    -- [filtered] AND c.collection_id = ANY(:collections)
  GROUP BY c.id
  ORDER BY score DESC, c.id
  LIMIT :leg_limit                                    -- 100
),
lexical_ranked AS (
  SELECT id, row_number() OVER (ORDER BY score DESC, id) AS rank FROM lexical
),
semantic AS MATERIALIZED (
  SELECT id, embedding <=> :qvec AS distance
  FROM chunks
  WHERE embedding IS NOT NULL
    -- [filtered] AND collection_id = ANY(:collections)
  ORDER BY distance
  LIMIT :leg_limit
),
semantic_ranked AS (
  SELECT id, row_number() OVER (ORDER BY distance + 0) AS rank FROM semantic
),
fused AS (
  SELECT id,
         coalesce(:w_lex / (:k + l.rank), 0.0)
       + coalesce(:w_sem / (:k + s.rank), 0.0) AS rrf,   -- k = 60, weights 1.0
         l.rank AS lexical_rank,
         s.rank AS semantic_rank
  FROM lexical_ranked l
  FULL OUTER JOIN semantic_ranked s USING (id)
)
SELECT f.id, f.rrf, f.lexical_rank, f.semantic_rank,
       c.document_id, c.ord, c.heading, c.content, d.title
FROM fused f
JOIN chunks c USING (id)
JOIN documents d ON d.id = c.document_id
ORDER BY f.rrf DESC, f.id
LIMIT :fused_limit;                                   -- 50
```

Why the query is shaped this way:
- **BM25:** `score = Σ idf · tf·(k1+1) / (tf + k1·(1 − b + b·dl/avgdl))`.
  - `tf` is the term's position count in the chunk's `tsv`.
  - `dl` is `token_count`, and `avgdl` is its corpus average.
  - `idf = ln(1 + (N − df + 0.5)/(df + 0.5))`, with `N` clamped to at least `df`, so statistics that lag a new ingest can never make IDF negative.
  - Stop words never reach `tsv` or the query, so they cost nothing.
- **The GIN `@@` match** limits scoring to chunks that contain at least one query term. If p95 latency is too high, the first fix is to build the candidate tsquery only from terms above an IDF floor, while still scoring every term. Very common terms add little score but many candidates.
- **`or_tsquery`** turns free text into an OR of stemmed lexemes. Quotes, colons and other operator characters from users or models can't break the query or inject tsquery operators. An all-stop-word query matches nothing in this leg and falls through to the semantic leg.
- **`hnsw.ef_search` must be at least `leg_limit`.** Without iterative scans, HNSW returns at most `ef_search` rows, and the default of 40 would quietly cap the semantic leg at 40.
- **Iterative scans** (pgvector 0.8+) keep scanning when a collection filter discards candidates. `relaxed_order` can return rows slightly out of order. The `MATERIALIZED` CTE followed by a re-sort is pgvector's documented fix, and the `+ 0` is needed on Postgres 17+.
- **`FULL OUTER JOIN`** keeps rows found by only one leg and returns both ranks. Every hit carries `lexical_rank` and `semantic_rank`, which makes debugging and evals simple.
- **Modes.** `lexical` and `semantic` mode drop the other leg's CTEs. The service assembles the statement from fragments, and the shape stays the same.
- **Snippets** aren't in v1. The UI highlights query terms on the client. `ts_headline` is available later if needed.

### Reranking

```python
class Reranker(Protocol):
    async def rerank(self, query: str, docs: Sequence[str], *, top_n: int) -> list[tuple[int, float]]
```

- **Input:** the top `fused_limit` (50) fused hits, each as `"{title} › {heading}\n\n{content}"`. Output: the top N, ordered by `rerank_score`.
- **Adapters:** one hosted API and one self-hosted endpoint. Hosted options include Cohere Rerank (billed per search), Voyage rerank (billed per token) and Qwen3-Reranker on Fireworks. Self-hosted means Qwen3-Reranker (Apache-2.0) or bge-reranker behind Hugging Face TEI's `/rerank`. The vendors' request shapes are close (`query`, `documents`, `top_n`/`top_k`), so each adapter is about 30 lines.
- **Cost shape:** 50 candidates × ~450 tokens is about 22k tokens per search. Per-token pricing grows with chunk size and candidate count; per-search pricing doesn't. An agent may search 3–10 times per turn, so per-search cost matters more than it does for a search box.
- **Failure:** on a timeout (`rerank_timeout_s`, 2 s) or an error, return the RRF order with `reranked: false`. Search never fails because the reranker did.
- **Threshold:** `min_rerank_score` (off by default) can drop weak hits from tool results to cut noise in the context window. Tune it with the eval.

### Embeddings

```python
class EmbeddingProvider(Protocol):
    async def embed(self, texts: Sequence[str], *, kind: Literal["query", "document"]) -> list[list[float]]
```

- **One OpenAI-compatible adapter** (`openai` SDK, `embeddings.create(..., dimensions=1024)`) covers OpenAI, Fireworks, Ollama and TEI. That mirrors how `OpenAICompatibleProvider` covers open-weight chat. The OpenAI key already in `apps/api/.env` is enough for development.
- **`kind` exists** because several models (Qwen3-Embedding, Voyage, Cohere) embed queries and documents differently, with an instruction prefix or an `input_type`. OpenAI ignores it.
- **Which model** is decided by the Phase 1 eval. Run at least one hosted model and one open-weight model at 1024 dimensions.

### Config

```python
@dataclass(frozen=True)
class SearchConfig:
    embedding_model: str                  # "<provider>/<model>", like chat model ids
    embedding_dims: int = 1024
    leg_limit: int = 100                  # candidates per leg
    bm25_k1: float = 1.2
    bm25_b: float = 0.75
    rrf_k: int = 60
    lexical_weight: float = 1.0
    semantic_weight: float = 1.0
    fused_limit: int = 50                 # also the reranker's candidate count
    rerank_model: str | None = None       # None = reranking off
    rerank_timeout_s: float = 2.0
    min_rerank_score: float | None = None
    hnsw_ef_search: int = 100             # must be >= leg_limit
```

## REST API

Routes live in `search/routes.py`. There is no auth yet, and every route sees every collection.

| Method | Path | Body / query | Notes |
| - | - | - | - |
| GET | `/collections` | | |
| POST | `/collections` | `{name}` | |
| DELETE | `/collections/{id}` | | Cascades to documents and chunks. |
| GET | `/collections/{id}/documents` | | Newest first, with `status`. |
| GET | `/collections/{id}` | | With `document_count`. |
| POST | `/collections/{id}/documents` | `{title, content, source?, uri?, metadata?}` | `201`, returns the document with `status: "indexing"`. |
| POST | `/collections/{id}/documents/upload` | multipart `file` (`.md`, `.txt`), optional `title` | `201`. The title defaults to the file name. |
| GET | `/documents/{id}` | `?include=content` | `status`, `chunks_pending`. |
| PUT | `/documents/{id}` | `{title?, content?, uri?, metadata?}` | Re-chunks only if the title or content changed; unchanged chunks keep their embeddings. |
| DELETE | `/documents/{id}` | | |
| POST | `/search` | `SearchRequest` | Returns `SearchResponse`. |

```python
class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    collection_ids: list[UUID] | None = None     # None = every collection
    document_ids: list[UUID] | None = None
    mode: Literal["hybrid", "lexical", "semantic"] = "hybrid"
    limit: int = Field(default=10, ge=1, le=50)

class Hit(BaseModel):
    chunk_id: int
    document_id: UUID
    collection_id: UUID
    ord: int
    title: str
    heading: str
    content: str
    score: float                  # the RRF score
    lexical_rank: int | None      # 1-based; None if that leg missed it
    semantic_rank: int | None

class SearchResponse(BaseModel):
    results: list[Hit]
    mode: Literal["hybrid", "lexical", "semantic"]   # what actually ran
    timings_ms: dict[str, float]  # embed, sql
```

As built (`apps/api/src/api/search/schemas.py`). Phase 2 adds `rerank` to the request, and `rerank_score` and `reranked` to the response.

**Search never fails because embeddings did.** Without an embedding provider, or when the query embedding call fails, `hybrid` runs BM25 alone and reports `mode: "lexical"`. `semantic` returns 400 when no provider is configured and 503 when the provider errors.

The generated client (hey-api) picks these up through OpenAPI as usual. Next.js does no search work itself.

## Agent tools

These live in `tools/builtin/search.py` and implement the `Tool` protocol from [HARNESS_CORE.md](HARNESS_CORE.md#tools). All three are `read_only` and `parallel_safe`, with a 10 s timeout.

| Tool | Input | Returns |
| - | - | - |
| `search_docs` | `query`, `collection?` (name), `limit` (default 8, max 20) | Numbered hits: `[n] Title › Heading (doc <id>, chunk <ord>)` followed by the chunk text. |
| `read_document` | `document_id`, `start` (chunk ord, default 0), `count` (default 5, max 20) | Chunks in order, plus `total_chunks`, so the model can page through or read around a hit. |
| `list_documents` | `collection?` | Collections, plus the titles, ids and status of their documents. |

- **Scope** is every collection for now. `ToolContext.collections` is `None` (meaning all), and the tool honours it. That gives ownership a place to plug in later without changing the tools.
- **No query rewriting, HyDE or multi-query expansion in v1.** The model is already the query rewriter. The tool description tells it to search more than once, with keywords (names, error codes, ids) as well as paraphrases. Measure before adding more.
- **Context budget:** 8 hits × ~400 tokens is about 3–4k tokens per call, well under `max_result_chars`.
- **Cost:** query embedding and rerank cost go on the tool result block (`cost_usd`), so turn cost includes retrieval.
- **Later:** `save_note` (a write tool that adds a `note` document to a collection). It follows the normal permission modes.

## Ownership later

When Clerk auth lands:
1. Add `owner_id text NOT NULL` to `collections` and `chat_sessions`.
2. The API resolves allowed collection ids from `current_user`; the harness resolves them from the session into `ToolContext.collections`. Requests and models can narrow that list but never widen it.
3. Make the collection predicate in both legs unconditional, so filtering happens before ranking. A post-filter would leak through rank positions.
4. Add an isolation test to normal `pytest`: two owners with overlapping content, asserting that no query in any mode returns the other owner's chunks.
5. Note that BM25 statistics stay global across owners. This is acceptable at small scale; per-owner statistics come with per-tenant partitioning.

## Module layout

```
apps/api/src/api/
  db/        engine.py (async engine, TLS, session dependency)  models.py
  chat/      store.py → PostgresChatStore (same interface, async)
  search/    schemas.py  service.py (search())  sql.py (hybrid query fragments)
             ingest.py (extract, chunk, write)  embedder.py (lifespan task: embed + refresh stats)  routes.py
  llm/       embeddings.py (EmbeddingProvider)  rerank.py (Reranker)
  tools/builtin/search.py
apps/api/alembic/versions/  0001_chat_tables.py (built)  0002_search.py
apps/api/evals/suites/retrieval/
infra/docker-compose.yml   pgvector/pgvector at pgvector 0.8.1 + Postgres 18 (tests and CI only)
```

New settings (the `DB_*` ones already exist): `EMBEDDING_MODEL`, `EMBEDDING_BASE_URL`, `EMBEDDING_API_KEY`, `RERANK_PROVIDER`, `RERANK_MODEL`, `RERANK_BASE_URL`, `RERANK_API_KEY`. New dependencies: `pgvector`, plus a PDF text extractor. SQLAlchemy, asyncpg and Alembic are already in.

## Evals

Retrieval evals are what turn "the reranker is a big quality boost" into a measured number. They plug into the HARNESS_CORE Phase 4 runner and are keyed by the `SearchConfig` hash. They run against the local Docker database loaded with a fixed corpus, never against dev RDS.

| Suite | What it measures | Size |
| - | - | - |
| Retrieval | A fixed corpus with labelled `(query, relevant chunks)` pairs. Most queries are LLM-generated per chunk and spot-checked by hand. About 30 are hand-written, split between keyword-heavy (names, codes, ids: BM25's strength) and paraphrased (vectors' strength). | 150–200 queries |
| Agent QA | Questions answered from an uploaded corpus, graded on answer correctness and on whether the cited document is right. | 10–20 tasks |

- **Metrics:** recall@50 after fusion (the ceiling on what the reranker can do), nDCG@10 and MRR@10 on the final list, p50/p95 latency per stage, and cost per 1k searches.
- **Matrix:** lexical only, semantic only, RRF, and RRF + rerank. The lexical leg is run two ways: SQL BM25 and Postgres's own `ts_rank_cd` (a one-line swap). That checks the BM25 work actually pays off.
- **Ablations:** `rrf_k`, `leg_limit`, leg weights, chunk size, and 25/50/100 rerank candidates.
- **Agent QA** compares the search tools on vs off, and rerank on vs off, on the same model.

## Phases

Estimates are rough guesses for one person. Phases 0–2 need only Postgres, not the harness. Phase 3 needs HARNESS_CORE phase 2 (loop and registry). Phase 0 also covers the "connect Postgres" TODO in SYSTEM_DESIGN.md and HARNESS_CORE's note that Postgres should land before its phase 3.

| Phase | Scope | Exit criteria | Est. |
| - | - | - | - |
| 0. Database | **Done 2026-11-20:** roles and the `vector` extension (`infra/rds/bootstrap.sql`), TLS connection, async SQLAlchemy, Alembic, chat tables and `PostgresChatStore`, local Docker database for tests. **Left:** the search tables migration. | Migrations apply to a clean local database and to dev RDS. Sessions and messages survive an API restart, and an interrupted reply is marked as such. A committed chunk is matched by `or_tsquery` in the next statement. `EXPLAIN` shows the GIN and HNSW indexes used. | 2–3 d |
| 1. Ingest and hybrid search | **Built 2026-11-20:** chunk, write path, `EmbeddingProvider` (`text-embedding-3-large` at 1024 dims by default), embedder and statistics refresh, the hybrid query, collections/documents routes, `POST /search`, tests against Postgres. **Left:** HTML and PDF extraction, the retrieval eval and its baselines, and lexical-leg p95 at 10k/100k chunks. Original scope: extract, chunk, write path, `EmbeddingProvider`, embedder and statistics refresh, the hybrid query, collections/documents routes, `POST /search`. | An uploaded markdown doc is lexically searchable at once and semantically searchable within seconds. Editing one section re-embeds only that section. Delete removes it from both legs. Baseline retrieval numbers exist for both lexical variants, semantic and RRF, with two embedding models. Lexical-leg p95 is recorded at 10k and 100k chunks. | 3–4 d |
| 2. Reranker | `Reranker` protocol, one hosted and one self-hosted adapter, timeout fallback. | The eval shows the nDCG@10 and p95 latency change from reranking. Whether reranking is on by default is decided from those numbers. | 1–2 d |
| 3. Agent tools | `search_docs`, `read_document`, `list_documents`, `ToolContext.collections`, retrieval cost on tool results, tool cards. | The agent answers from an uploaded doc and cites it correctly. Agent QA with tools on vs off. | 2 d |
| 4. Web UI | Collections and documents pages, upload, indexing status, a search box over `/search`. | Upload → see it indexing → search it, end to end in the browser. | 2 d |
| 5. Later | [Ownership](#ownership-later), chat history as a source, OCR, `save_note`, Procrastinate in place of the in-process embedder, a query-embedding cache, LLM-written chunk context, an [index-native BM25](#appendix-upgrading-to-an-index-native-bm25) once off RDS. | Separate specs. | |

## Risks

| Risk | Mitigation |
| - | - |
| SQL BM25 scores every matching chunk, so latency grows with corpus size and common terms | Measure p95 in Phase 1. Prune low-IDF terms from candidate selection. The upgrade path is one CTE. |
| BM25 statistics lag ingest by up to 30 s | Matching is never stale, only term weights, and new terms are scored as rare. Refresh is debounced after every ingest. |
| The dev RDS instance is shared state: a migration or a bad ingest affects everyone using it | Tests and evals never run against it. Migrations are run by hand. RDS automated backups are on. |
| Uploaded documents and fetched pages are untrusted text in the same session as an outbound channel (`web_fetch`), which is the setup for exfiltration through prompt injection | Retrieved text is treated as untrusted, the same as fetched pages. Before any private data is uploaded, `web_fetch` defaults to `ask` in sessions that have searched documents. |
| HNSW plus a selective collection filter returns too few rows | Iterative scans, `ef_search >= leg_limit`, and a B-tree on `collection_id` so small collections get exact scans. Phase 0 checks the plans. |
| Reranker latency or cost per agent turn grows with repeated searches | Timeout fallback. Cost recorded per tool call. Candidate count is ablated in evals. |

## Open questions

1. ~~Is the dev RDS instance on Postgres 18?~~ Yes: 18.3 with pgvector 0.8.1.
2. Which embedding model and which reranker? Phase 1 and 2 evals decide.
3. Should chat history be searchable in v1 (a `chat` source), or only uploaded documents?
4. Do we keep original uploaded files (S3), or only the extracted text?
5. What lexical-leg p95, or what corpus size, is the trigger to leave RDS for an index-native BM25?

## Changes to existing docs

These aren't applied yet.

- **SYSTEM.md:**
  - Data: lexical search is BM25 computed in SQL over Postgres full-text search, since RDS has no BM25 extension.
  - The local docker-compose image is for tests only, pinned to the dev instance's pgvector (0.8.1) and Postgres major version.
  - Background jobs: the embedder runs in-process until there is a worker service.
- **SYSTEM_DESIGN.md:**
  - Chat entities match today's schemas: uuid message ids, and no `user_id` until auth.
  - `agent_docs/files` becomes `collections` / `documents` / `chunks`.
  - The API section gains the routes above.
  - The "connect Postgres" TODO points to Phase 0.
- **HARNESS_CORE.md:** the tools table gains `search_docs`, `read_document` and `list_documents`. `ToolContext` gains `collections`. `ToolResultBlock` gains `cost_usd`.

## Appendix: upgrading to an index-native BM25

These apply only if the database moves off RDS: self-managed, ParadeDB BYOC, or Tiger Cloud. Neon retired `pg_search` on 2026-09-21. Only the `query_terms` and `lexical` CTEs change, and the statistics views and `or_tsquery` go away. Everything from `lexical_ranked` onward stays the same.

**ParadeDB `pg_search`** (AGPL-3.0). Filters on indexed columns run inside the index scan, and top-k is pruned. A table can have only one ParadeDB index.

```sql
CREATE INDEX chunks_search_idx ON chunks USING paradedb (
  id, (heading::pdb.unicode_words('stemmer=english')), (content::pdb.unicode_words('stemmer=english')), collection_id
);

lexical AS (
  SELECT id, pdb.score(id) AS score
  FROM chunks
  WHERE (heading ||| :q OR content ||| :q)   -- match query: tokenized, OR-ed, no parser syntax
  ORDER BY score DESC
  LIMIT :leg_limit
)
```

**`pg_textsearch`** (PostgreSQL licence, Postgres 17–19). Lower scores rank first. BM25 combined with a filter is not yet a single index scan.

```sql
CREATE INDEX chunks_bm25_idx ON chunks USING bm25 (content) WITH (text_config = 'english');

lexical AS (
  SELECT id, -(content <@> to_bm25query(:q, 'chunks_bm25_idx')) AS score
  FROM chunks
  ORDER BY content <@> to_bm25query(:q, 'chunks_bm25_idx')
  LIMIT :leg_limit
)
```

`pg_search`, `pg_textsearch` and `vchord_bm25` all register a `bm25` access method, so never install two of them in the same database.

## Sources

- [AWS: extensions supported on RDS for PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/PostgreSQLReleaseNotes/postgresql-extensions.html) (pgvector 0.8.2 on 18.6; no BM25 extension)
- [pgvector README](https://github.com/pgvector/pgvector) (HNSW limits, iterative scans)
- [ParadeDB: Hybrid search in PostgreSQL, the missing manual](https://www.paradedb.com/blog/hybrid-search-in-postgresql-the-missing-manual), [create index](https://www.paradedb.com/docs/documentation/indexing/create-index), [filtering](https://www.paradedb.com/docs/documentation/filtering)
- [pg_textsearch README](https://github.com/timescale/pg_textsearch) (v1.5.1)
- [Neon: pg_search vs pg_textsearch vs Lakebase Search](https://neon.com/faqs/pg-search-vs-pg-textsearch-vs-lakebase-search-bm25) (2026-11-13)
- Reranker roundups that disagree on models and prices: [futureagi.com](https://futureagi.com/blog/best-rerankers-for-rag-2026/), [beri.net](https://www.beri.net/article/cohere-vs-voyage-vs-bge-reranker-per-search-vs-per-token-cost-2026)

"""Hybrid retrieval: BM25 and vector search on the chunks table, fused with RRF in one query.

BM25 is computed in SQL because RDS has no BM25 extension: the GIN index finds chunks with
any query term, and lexeme_df / corpus_stats supply IDF and average length. Only ranks are
fused, never raw scores, so the two legs never need calibrating against each other.
"""

import logging
import time
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.llm.embeddings import EmbeddingProvider
from api.search.config import SearchConfig
from api.search.embedder import vector_literal
from api.search.schemas import Hit, SearchRequest, SearchResponse

Mode = Literal["hybrid", "lexical", "semantic"]

logger = logging.getLogger(__name__)


class SemanticSearchUnavailable(Exception):
    """Semantic mode was asked for but can't run. `retryable` when the provider failed."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


async def search(
    db: async_sessionmaker[AsyncSession],
    provider: EmbeddingProvider | None,
    request: SearchRequest,
    config: SearchConfig,
) -> SearchResponse:
    mode: Mode = request.mode
    if mode != "lexical" and provider is None:
        if mode == "semantic":
            raise SemanticSearchUnavailable("No embedding provider is configured", retryable=False)
        mode = "lexical"

    timings: dict[str, float] = {}
    params: dict[str, Any] = {"q": request.query, "limit": request.limit}
    if request.collection_ids is not None:
        params["collections"] = request.collection_ids
    if request.document_ids is not None:
        params["documents"] = request.document_ids
    if mode != "lexical":
        assert provider is not None
        started = time.perf_counter()
        try:
            [vector] = await provider.embed([request.query], kind="query")
        except Exception as exc:
            if mode == "semantic":
                raise SemanticSearchUnavailable(
                    f"The embedding provider failed: {exc}", retryable=True
                ) from exc
            # Search never fails because embeddings did: BM25 alone still answers.
            logger.warning("Query embedding failed; answering with BM25 only", exc_info=True)
            mode = "lexical"
        else:
            timings["embed"] = _ms(started)
            params["qvec"] = vector_literal(vector)

    started = time.perf_counter()
    async with db.begin() as session:
        if mode != "lexical":
            # SET LOCAL can't take bind parameters; set_config(..., true) is the same thing.
            await session.execute(
                text(
                    "SELECT set_config('hnsw.ef_search', :ef, true), "
                    "set_config('hnsw.iterative_scan', 'relaxed_order', true)"
                ),
                {"ef": str(config.hnsw_ef_search)},
            )
        rows = (await session.execute(text(build_query(mode, request, config)), params)).mappings()
        hits = [Hit.model_validate(dict(row)) for row in rows]
    timings["sql"] = _ms(started)
    return SearchResponse(results=hits, mode=mode, timings_ms=timings)


def build_query(mode: Mode, request: SearchRequest, config: SearchConfig) -> str:
    """The statement for one search. Only config numbers are inlined; user input is bound."""
    filters = ""
    if request.collection_ids is not None:
        filters += "\n    AND c.collection_id = ANY(CAST(:collections AS uuid[]))"
    if request.document_ids is not None:
        filters += "\n    AND c.document_id = ANY(CAST(:documents AS uuid[]))"
    k1, b = float(config.bm25_k1), float(config.bm25_b)
    k, n = int(config.rrf_k), int(config.leg_limit)
    w_lex, w_sem = float(config.lexical_weight), float(config.semantic_weight)

    lexical = f"""
query_terms AS (
  SELECT t.lexeme, coalesce(l.df, 1)::float8 AS df
  FROM unnest(tsvector_to_array(to_tsvector('english', :q))) AS t(lexeme)
  LEFT JOIN lexeme_df l USING (lexeme)
),
idf AS (
  -- Between statistics refreshes a new term has no df row; it counts as df = 1 (rare), and
  -- N is clamped so a stale corpus count can never make IDF negative.
  SELECT q.lexeme, ln(1 + (greatest(cs.n, q.df) - q.df + 0.5) / (q.df + 0.5)) AS idf
  FROM query_terms q CROSS JOIN corpus_stats cs
),
lexical AS (
  SELECT c.id,
         sum(i.idf * cardinality(u.positions) * ({k1} + 1)
             / (cardinality(u.positions)
                + {k1} * (1 - {b} + {b} * c.token_count / cs.avgdl))) AS score
  FROM chunks c
  CROSS JOIN corpus_stats cs
  CROSS JOIN LATERAL unnest(c.tsv) AS u(lexeme, positions, weights)
  JOIN idf i ON i.lexeme = u.lexeme
  WHERE c.tsv @@ or_tsquery(:q){filters}
  GROUP BY c.id
  ORDER BY score DESC, c.id
  LIMIT {n}
),
lexical_ranked AS (
  SELECT id, row_number() OVER (ORDER BY score DESC, id) AS rank FROM lexical
)"""

    # MATERIALIZED + a re-sort: pgvector's fix for relaxed_order iterative scans, which can
    # return rows slightly out of order. `+ 0` is needed on Postgres 17+.
    semantic = f"""
semantic AS MATERIALIZED (
  SELECT c.id, c.embedding <=> CAST(CAST(:qvec AS text) AS halfvec) AS distance
  FROM chunks c
  WHERE c.embedding IS NOT NULL{filters}
  ORDER BY distance
  LIMIT {n}
),
semantic_ranked AS (
  SELECT id, row_number() OVER (ORDER BY distance + 0) AS rank FROM semantic
)"""

    if mode == "hybrid":
        ctes = [lexical, semantic]
        fused = f"""
fused AS (
  SELECT id,
         coalesce({w_lex}::float8 / ({k} + l.rank), 0)
       + coalesce({w_sem}::float8 / ({k} + s.rank), 0) AS rrf,
         l.rank AS lexical_rank,
         s.rank AS semantic_rank
  FROM lexical_ranked l
  FULL OUTER JOIN semantic_ranked s USING (id)
)"""
    elif mode == "lexical":
        ctes = [lexical]
        fused = f"""
fused AS (
  SELECT id, {w_lex}::float8 / ({k} + rank) AS rrf, rank AS lexical_rank,
         NULL::bigint AS semantic_rank
  FROM lexical_ranked
)"""
    else:
        ctes = [semantic]
        fused = f"""
fused AS (
  SELECT id, {w_sem}::float8 / ({k} + rank) AS rrf, NULL::bigint AS lexical_rank,
         rank AS semantic_rank
  FROM semantic_ranked
)"""

    return f"""WITH {",".join([*ctes, fused])}
SELECT f.id AS chunk_id, c.document_id, c.collection_id, c.ord, d.title, c.heading,
       c.content, f.rrf AS score, f.lexical_rank, f.semantic_rank
FROM fused f
JOIN chunks c ON c.id = f.id
JOIN documents d ON d.id = c.document_id
ORDER BY f.rrf DESC, f.id
LIMIT :limit"""


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)

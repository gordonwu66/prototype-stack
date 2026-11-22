"""Background work that keeps search current: fills NULL embeddings, refreshes BM25 stats.

A NULL embedding is the queue. Writes commit chunks without vectors and call notify();
a timer sweep catches anything a crash or provider outage left behind, so nothing is lost
between a commit and a wake-up. One loop per API process.
"""

import asyncio
import contextlib
import logging
import time

from sqlalchemy import text

from api.config import settings
from api.db.engine import Database, database
from api.db.models import EMBEDDING_DIMS
from api.llm.embeddings import EmbeddingProvider, embedding_provider
from api.search.chunking import embed_text
from api.search.config import DEFAULT_CONFIG, SearchConfig

logger = logging.getLogger(__name__)


def vector_literal(vector: list[float]) -> str:
    """pgvector's text format; cast to halfvec in SQL."""
    return "[" + ",".join(f"{x:.7g}" for x in vector) + "]"


class Embedder:
    def __init__(
        self, db: Database, provider: EmbeddingProvider | None, config: SearchConfig
    ) -> None:
        self.database = db
        self.provider = provider
        self.config = config
        self._wake = asyncio.Event()
        self._stats_dirty = True  # refresh once at startup
        self._last_refresh = float("-inf")
        self._task: asyncio.Task[None] | None = None

    def notify(self) -> None:
        """Call after committing a change that added or removed chunks."""
        self._stats_dirty = True
        self._wake.set()

    def start(self) -> None:
        if self.database.configured and self._task is None:
            self._wake = asyncio.Event()  # bound to the serving loop
            self._task = asyncio.create_task(self._run(), name="search-embedder")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def embed_pending(self) -> int:
        """Embeds every chunk that has no vector yet. Returns how many it embedded."""
        if self.provider is None:
            return 0
        done = 0
        while True:
            async with self.database.sessions() as session:
                rows = (
                    await session.execute(
                        text(
                            "SELECT id, heading, content FROM chunks "
                            "WHERE embedding IS NULL ORDER BY id LIMIT :n"
                        ),
                        {"n": self.config.embed_batch_size},
                    )
                ).all()
            if not rows:
                return done
            # No transaction is held during the API call. A chunk replaced meanwhile is
            # gone, so its update below matches nothing.
            vectors = await self.provider.embed(
                [embed_text(heading, content) for _, heading, content in rows], kind="document"
            )
            async with self.database.sessions.begin() as session:
                await session.execute(
                    text(
                        """
                        UPDATE chunks AS c
                        SET embedding = CAST(v.e AS halfvec), embedding_model = :model
                        FROM unnest(CAST(:ids AS bigint[]), CAST(:vectors AS text[])) AS v(id, e)
                        WHERE c.id = v.id AND c.embedding IS NULL
                        """
                    ),
                    {
                        "ids": [row.id for row in rows],
                        "vectors": [vector_literal(v) for v in vectors],
                        "model": self.provider.model,
                    },
                )
            done += len(rows)

    async def refresh_stats(self) -> None:
        """Recomputes BM25 document frequencies and average chunk length."""
        self._stats_dirty = False  # a notify() during the refresh marks it dirty again
        self._last_refresh = time.monotonic()
        async with self.database.sessions.begin() as session:
            await session.execute(text("SELECT refresh_search_stats()"))

    async def tick(self) -> bool:
        """One round of background work. Embedding and the statistics refresh run
        independently, so a provider outage never leaves BM25 weights stale. False on errors."""
        ok = True
        try:
            await self.embed_pending()
        except Exception:
            ok = False
            logger.exception(
                "Embedding chunks failed; they stay searchable by BM25 and are retried"
            )
        try:
            since = time.monotonic() - self._last_refresh
            if self._stats_dirty and since >= self.config.stats_refresh_s:
                await self.refresh_stats()
        except Exception:
            ok = False
            self._stats_dirty = True
            logger.exception("Refreshing BM25 statistics failed; retrying")
        return ok

    @property
    def stats_dirty(self) -> bool:
        return self._stats_dirty

    async def _run(self) -> None:
        failures = 0
        while True:
            timeout = self.config.sweep_interval_s
            if self._stats_dirty:
                due = self._last_refresh + self.config.stats_refresh_s - time.monotonic()
                timeout = max(0.0, min(timeout, due))
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout)
            self._wake.clear()
            failures = 0 if await self.tick() else failures + 1
            if failures:
                await asyncio.sleep(min(300.0, 5.0 * 2**failures))


embedder = Embedder(database, embedding_provider(settings, EMBEDDING_DIMS), DEFAULT_CONFIG)

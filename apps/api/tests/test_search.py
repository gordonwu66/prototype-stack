"""Search against real Postgres (`pnpm test:api:db`); skipped without one.

Each test works in its own collection and filters by it, so tests don't see each other's
documents. BM25 statistics are global, which none of the assertions depend on.
"""

import asyncio
import math
import re
import zlib
from collections.abc import AsyncIterator, Sequence
from dataclasses import replace
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text

from api.db.engine import database
from api.db.models import EMBEDDING_DIMS
from api.llm.embeddings import EmbeddingProvider, EmbedKind
from api.main import app
from api.search import documents as docs
from api.search.config import DEFAULT_CONFIG
from api.search.embedder import Embedder, embedder
from api.search.query import Mode, SemanticSearchUnavailable, build_query, search
from api.search.schemas import DocumentCreate, DocumentUpdate, Hit, SearchRequest

pytestmark = pytest.mark.anyio

SYNONYMS = {"automobile": "car", "vehicle": "car", "cars": "car"}


class FakeEmbeddings:
    """Bag-of-words vectors with a few synonyms, so "automobile" lands near "car"."""

    model = "fake/bag-of-words"

    def __init__(self) -> None:
        self.texts: list[str] = []

    async def embed(self, texts: Sequence[str], *, kind: EmbedKind) -> list[list[float]]:
        if kind == "document":
            self.texts.extend(texts)
        return [self._vector(t) for t in texts]

    def _vector(self, text: str) -> list[float]:
        v = [0.0] * EMBEDDING_DIMS
        for word in re.findall(r"[a-z]+", text.lower()):
            word = SYNONYMS.get(word) or word
            v[zlib.crc32(word.encode()) % EMBEDDING_DIMS] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]


class FailingEmbeddings:
    model = "fake/down"

    async def embed(self, texts: Sequence[str], *, kind: EmbedKind) -> list[list[float]]:
        raise RuntimeError("provider is down")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def db() -> AsyncIterator[docs.Sessions]:
    if not database.configured:
        pytest.skip("Postgres not configured; run `pnpm test:api:db`")
    await database.start()
    yield database.sessions
    await database.close()


@pytest.fixture
def fake() -> FakeEmbeddings:
    return FakeEmbeddings()


@pytest.fixture
def indexer(fake: FakeEmbeddings) -> Embedder:
    return Embedder(database, fake, DEFAULT_CONFIG)


async def new_collection(db: docs.Sessions) -> UUID:
    return (await docs.create_collection(db, f"test-{uuid4()}")).id


async def add(db: docs.Sessions, collection: UUID, title: str, content: str) -> UUID:
    document_id = await docs.create_document(
        db, collection, DocumentCreate(title=title, content=content), DEFAULT_CONFIG
    )
    assert document_id is not None
    return document_id


async def find(
    db: docs.Sessions, provider: EmbeddingProvider | None, query: str, collection: UUID, **kw
) -> list[Hit]:
    request = SearchRequest(query=query, collection_ids=[collection], **kw)
    return (await search(db, provider, request, DEFAULT_CONFIG)).results


async def test_new_document_is_found_by_bm25_before_it_is_embedded(
    db: docs.Sessions, fake: FakeEmbeddings
) -> None:
    c = await new_collection(db)
    doc = await add(db, c, "Setup", "Install postgres, then run the migrations.")

    document = await docs.get_document(db, doc, embedding=True)
    assert document is not None
    assert (document.status, document.chunk_count, document.chunks_pending) == ("indexing", 1, 1)
    [hit] = await find(db, fake, "postgres migrations", c)
    assert (hit.document_id, hit.lexical_rank, hit.semantic_rank) == (doc, 1, None)
    assert hit.heading == "Setup"


async def test_embedder_fills_vectors_and_semantic_search_finds_paraphrases(
    db: docs.Sessions, fake: FakeEmbeddings, indexer: Embedder
) -> None:
    c = await new_collection(db)
    car = await add(db, c, "Garage", "Rotate the car tires every season.")
    await add(db, c, "Kitchen", "Simmer the stock for an hour.")

    assert await indexer.embed_pending() >= 2
    document = await docs.get_document(db, car, embedding=True)
    assert document is not None and (document.status, document.chunks_pending) == ("ready", 0)

    semantic = await find(db, fake, "automobile", c, mode="semantic")
    assert semantic[0].document_id == car and semantic[0].semantic_rank == 1
    assert await find(db, fake, "automobile", c, mode="lexical") == []


async def test_hybrid_ranks_chunks_found_by_both_legs_first(
    db: docs.Sessions, fake: FakeEmbeddings, indexer: Embedder
) -> None:
    c = await new_collection(db)
    await add(db, c, "Ops", "Postgres replication and failover.")
    await add(db, c, "Fleet", "Automobile maintenance schedule.")
    both = await add(db, c, "Rentals", "A postgres database of every car rental.")
    await indexer.embed_pending()

    hits = await find(db, fake, "postgres car", c)
    assert hits[0].document_id == both
    assert (hits[0].lexical_rank, hits[0].semantic_rank) == (1, 1)
    assert hits[0].score == pytest.approx(2 / (DEFAULT_CONFIG.rrf_k + 1))
    # "Fleet" has no query term, so only the semantic leg (synonyms) finds it.
    fleet = next(h for h in hits if h.title == "Fleet")
    assert fleet.lexical_rank is None and fleet.semantic_rank is not None


async def test_background_loop_embeds_after_a_notify(
    db: docs.Sessions, fake: FakeEmbeddings
) -> None:
    worker = Embedder(database, fake, replace(DEFAULT_CONFIG, stats_refresh_s=0.0))
    c = await new_collection(db)
    doc = await add(db, c, "Loop", "Background capybara text.")
    worker.start()
    document = None
    try:
        worker.notify()
        for _ in range(100):
            document = await docs.get_document(db, doc, embedding=True)
            assert document is not None
            if document.chunks_pending == 0:
                break
            await asyncio.sleep(0.05)
        assert document is not None and document.chunks_pending == 0
    finally:
        await worker.stop()


async def test_editing_one_section_reembeds_only_that_section(
    db: docs.Sessions, fake: FakeEmbeddings, indexer: Embedder
) -> None:
    c = await new_collection(db)
    body = "# Alpha\n\nFirst part.\n\n# Beta\n\nSecond part.\n\n# Gamma\n\nThird part."
    doc = await add(db, c, "Guide", body)
    await indexer.embed_pending()
    fake.texts.clear()

    edited = body.replace("Second part.", "Second part, rewritten.")
    assert await docs.update_document(db, doc, DocumentUpdate(content=edited), DEFAULT_CONFIG)
    assert await indexer.embed_pending() == 1
    assert fake.texts == ["Guide › Beta\n\nSecond part, rewritten."]
    document = await docs.get_document(db, doc, embedding=True)
    assert document is not None and (document.chunk_count, document.chunks_pending) == (3, 0)

    # A metadata-only update doesn't touch chunks at all.
    assert await docs.update_document(db, doc, DocumentUpdate(uri="https://x"), DEFAULT_CONFIG)
    assert await indexer.embed_pending() == 0


async def test_deleting_a_document_removes_it_from_both_legs(
    db: docs.Sessions, fake: FakeEmbeddings, indexer: Embedder
) -> None:
    c = await new_collection(db)
    doc = await add(db, c, "Notes", "Quarterly zebra census results.")
    await indexer.embed_pending()
    [hit] = await find(db, fake, "zebra census", c)
    assert hit.lexical_rank == 1 and hit.semantic_rank == 1

    assert await docs.delete_document(db, doc)
    assert await find(db, fake, "zebra census", c) == []


async def test_filters_narrow_results(db: docs.Sessions, fake: FakeEmbeddings) -> None:
    a, b = await new_collection(db), await new_collection(db)
    doc_a = await add(db, a, "One", "Shared pelican text.")
    doc_a2 = await add(db, a, "Two", "Shared pelican text again.")
    await add(db, b, "Three", "Shared pelican text.")

    assert {h.document_id for h in await find(db, fake, "pelican", a)} == {doc_a, doc_a2}
    request = SearchRequest(query="pelican", collection_ids=[a, b], document_ids=[doc_a2])
    [hit] = (await search(db, fake, request, DEFAULT_CONFIG)).results
    assert hit.document_id == doc_a2


async def test_bm25_weights_rare_terms_above_common_ones(
    db: docs.Sessions, fake: FakeEmbeddings, indexer: Embedder
) -> None:
    c = await new_collection(db)
    for i in range(4):
        await add(db, c, f"Filler {i}", f"Database backups and database indexes, part {i}.")
    common = await add(db, c, "Common", "Database database database tuning.")
    rare = await add(db, c, "Rare", "Zebra stripes.")
    await indexer.refresh_stats()

    hits = await find(db, fake, "database zebra", c, mode="lexical")
    assert hits[0].document_id == rare
    assert hits[1].document_id == common


async def test_query_text_is_never_parsed_as_syntax(
    db: docs.Sessions, fake: FakeEmbeddings
) -> None:
    c = await new_collection(db)
    doc = await add(db, c, "Q", "The postgres database.")
    weird = """it's "postgres": OR & | ! <-> (database) \\ ' ;--"""
    assert [h.document_id for h in await find(db, fake, weird, c, mode="lexical")] == [doc]
    assert await find(db, fake, "the of and", c, mode="lexical") == []


async def test_semantic_search_needs_an_embedding_provider(db: docs.Sessions) -> None:
    c = await new_collection(db)
    await add(db, c, "Doc", "Some walrus text.")
    with pytest.raises(SemanticSearchUnavailable):
        await find(db, None, "walrus", c, mode="semantic")
    response = await search(
        db, None, SearchRequest(query="walrus", collection_ids=[c]), DEFAULT_CONFIG
    )
    assert response.mode == "lexical" and len(response.results) == 1


async def test_a_failing_provider_degrades_search_and_indexing_to_bm25(
    db: docs.Sessions,
) -> None:
    down = FailingEmbeddings()
    c = await new_collection(db)
    doc = await add(db, c, "Doc", "Some narwhal text.")

    request = SearchRequest(query="narwhal", collection_ids=[c])
    response = await search(db, down, request, DEFAULT_CONFIG)
    assert response.mode == "lexical" and [h.document_id for h in response.results] == [doc]
    with pytest.raises(SemanticSearchUnavailable) as raised:
        await find(db, down, "narwhal", c, mode="semantic")
    assert raised.value.retryable

    # The background round reports the failure, but the statistics still refresh.
    worker = Embedder(database, down, replace(DEFAULT_CONFIG, stats_refresh_s=0.0))
    assert await worker.tick() is False
    assert worker.stats_dirty is False


async def test_query_plans_can_use_the_search_indexes(db: docs.Sessions) -> None:
    """Each leg's query shape is index-compatible. On a test-sized table the planner would
    rather scan, so cheaper paths are switched off to see what it *can* use."""
    request = SearchRequest(query="postgres")
    params = {"q": "postgres", "qvec": "[" + ",".join(["0.1"] * EMBEDDING_DIMS) + "]", "limit": 10}

    async def plan(mode: Mode, *disabled: str) -> str:
        async with db.begin() as session:
            for setting in disabled:
                await session.execute(text(f"SET LOCAL {setting} = off"))
            sql = "EXPLAIN " + build_query(mode, request, DEFAULT_CONFIG)
            return "\n".join((await session.execute(text(sql), params)).scalars())

    # BM25 candidates come from the GIN index on tsv.
    assert "chunks_tsv_idx" in await plan("lexical", "enable_seqscan", "enable_indexscan")
    # The vector leg is an HNSW index scan (ORDER BY distance LIMIT n).
    assert "chunks_embedding_idx" in await plan("semantic", "enable_seqscan")


async def test_rest_round_trip(
    db: docs.Sessions, fake: FakeEmbeddings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(embedder, "provider", fake)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        name = f"rest-{uuid4()}"
        res = await http.post("/collections", json={"name": name})
        assert res.status_code == 201
        c = res.json()["id"]
        assert (await http.post("/collections", json={"name": name})).status_code == 409

        res = await http.post(
            f"/collections/{c}/documents",
            json={"title": "Runbook", "content": "# Restart\n\nRestart the ocelot service."},
        )
        assert res.status_code == 201 and res.json()["status"] == "indexing"
        doc = res.json()["id"]
        files = {"file": ("notes.md", b"Ocelot notes, uploaded.", "text/markdown")}
        res = await http.post(f"/collections/{c}/documents/upload", files=files)
        assert res.status_code == 201
        assert (res.json()["title"], res.json()["source"]) == ("notes", "upload")
        pdf = {"file": ("scan.pdf", b"%PDF", "application/pdf")}
        assert (await http.post(f"/collections/{c}/documents/upload", files=pdf)).status_code == 415

        listed = (await http.get(f"/collections/{c}/documents")).json()
        assert {d["title"] for d in listed} == {"Runbook", "notes"}
        assert (await http.get(f"/collections/{c}")).json()["document_count"] == 2

        await embedder.embed_pending()
        res = await http.get(f"/documents/{doc}", params={"include": "content"})
        assert res.json()["status"] == "ready" and "ocelot" in res.json()["content"]
        res = await http.put(f"/documents/{doc}", json={"title": "Runbook v2"})
        assert res.json()["title"] == "Runbook v2"
        # The title is in every chunk's breadcrumb, so a rename re-cuts and re-embeds.
        assert res.json()["status"] == "indexing"
        await embedder.embed_pending()

        res = await http.post("/search", json={"query": "restart ocelot", "collection_ids": [c]})
        assert res.status_code == 200
        body = res.json()
        assert body["mode"] == "hybrid" and set(body["timings_ms"]) == {"embed", "sql"}
        assert body["results"][0]["document_id"] == doc
        assert body["results"][0]["heading"] == "Runbook v2 › Restart"

        assert (await http.delete(f"/documents/{doc}")).status_code == 204
        assert (await http.get(f"/documents/{doc}")).status_code == 404
        assert (await http.delete(f"/collections/{c}")).status_code == 204
        assert (await http.get(f"/collections/{c}")).status_code == 404

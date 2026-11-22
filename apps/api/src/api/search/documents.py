"""Collections and documents, and the write path that keeps chunks in step with them.

Every write that changes chunks happens in the same transaction as the document change, so
the BM25 and HNSW indexes never disagree with the documents. Only embeddings lag: new chunks
commit with a NULL embedding and the embedder fills them in (api/search/embedder.py).
"""

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Integer, Select, delete, func, insert, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import defer

from api.db.models import ChunkRow, CollectionRow, DocumentRow
from api.search.chunking import chunk_document
from api.search.config import SearchConfig
from api.search.schemas import Collection, Document, DocumentCreate, DocumentUpdate

Sessions = async_sessionmaker[AsyncSession]


class CollectionExists(Exception):
    pass


# --- collections


async def list_collections(db: Sessions) -> list[Collection]:
    counts = (
        select(DocumentRow.collection_id, func.count().label("n"))
        .group_by(DocumentRow.collection_id)
        .subquery()
    )
    async with db() as session:
        rows = await session.execute(
            select(CollectionRow, func.coalesce(counts.c.n, 0))
            .outerjoin(counts, counts.c.collection_id == CollectionRow.id)
            .order_by(CollectionRow.name)
        )
        return [_collection(c, n) for c, n in rows.tuples()]


async def get_collection(db: Sessions, collection_id: UUID) -> Collection | None:
    async with db() as session:
        row = await session.get(CollectionRow, collection_id)
        if row is None:
            return None
        n = await session.scalar(
            select(func.count()).where(DocumentRow.collection_id == collection_id)
        )
        return _collection(row, n or 0)


async def create_collection(db: Sessions, name: str) -> Collection:
    try:
        async with db.begin() as session:
            row = CollectionRow(name=name)
            session.add(row)
    except IntegrityError as exc:
        raise CollectionExists(name) from exc
    return _collection(row, 0)


async def delete_collection(db: Sessions, collection_id: UUID) -> bool:
    async with db.begin() as session:
        deleted = await session.scalar(
            delete(CollectionRow)
            .where(CollectionRow.id == collection_id)
            .returning(CollectionRow.id)
        )
        return deleted is not None


# --- documents


async def list_documents(db: Sessions, collection_id: UUID, *, embedding: bool) -> list[Document]:
    async with db() as session:
        rows = await session.execute(
            _documents_query(include_content=False)
            .where(DocumentRow.collection_id == collection_id)
            .order_by(DocumentRow.created_at.desc())
        )
        return [_document(d, n, p, embedding=embedding) for d, n, p in rows.tuples()]


async def get_document(
    db: Sessions, document_id: UUID, *, embedding: bool, include_content: bool = False
) -> Document | None:
    async with db() as session:
        row = (
            await session.execute(
                _documents_query(include_content=include_content).where(
                    DocumentRow.id == document_id
                )
            )
        ).first()
        if row is None:
            return None
        d, n, p = row.tuple()
        return _document(d, n, p, embedding=embedding, include_content=include_content)


async def create_document(
    db: Sessions,
    collection_id: UUID,
    body: DocumentCreate,
    config: SearchConfig,
    *,
    source: str | None = None,
    mime_type: str | None = None,
) -> UUID | None:
    """Returns the new document's id, or None when the collection doesn't exist."""
    async with db.begin() as session:
        if await session.get(CollectionRow, collection_id) is None:
            return None
        doc = DocumentRow(
            collection_id=collection_id,
            title=body.title,
            source=source or body.source,
            uri=body.uri,
            mime_type=mime_type,
            content=body.content,
            content_hash=_document_hash(body.title, body.content),
            metadata_=body.metadata,
        )
        session.add(doc)
        await session.flush()
        await _replace_chunks(session, doc, config)
        return doc.id


async def update_document(
    db: Sessions, document_id: UUID, body: DocumentUpdate, config: SearchConfig
) -> bool:
    """Applies the changes; re-chunks only when the title or content changed."""
    async with db.begin() as session:
        doc = await session.scalar(
            select(DocumentRow).where(DocumentRow.id == document_id).with_for_update()
        )
        if doc is None:
            return False
        if body.title is not None:
            doc.title = body.title
        if body.content is not None:
            doc.content = body.content
        if "uri" in body.model_fields_set:
            doc.uri = body.uri
        if body.metadata is not None:
            doc.metadata_ = body.metadata
        doc.updated_at = datetime.now(UTC)
        new_hash = _document_hash(doc.title, doc.content)
        if new_hash != doc.content_hash:
            doc.content_hash = new_hash
            await _replace_chunks(session, doc, config)
        return True


async def delete_document(db: Sessions, document_id: UUID) -> bool:
    async with db.begin() as session:
        deleted = await session.scalar(
            delete(DocumentRow).where(DocumentRow.id == document_id).returning(DocumentRow.id)
        )
        return deleted is not None


async def _replace_chunks(session: AsyncSession, doc: DocumentRow, config: SearchConfig) -> None:
    """Swaps a document's chunks for freshly cut ones, keeping embeddings of unchanged chunks."""
    old_ids = list(
        (await session.scalars(select(ChunkRow.id).where(ChunkRow.document_id == doc.id))).all()
    )
    chunks = chunk_document(
        doc.title,
        doc.content,
        target_tokens=config.chunk_target_tokens,
        max_tokens=config.chunk_max_tokens,
        overlap_tokens=config.chunk_overlap_tokens,
    )
    new_ids: list[int] = []
    if chunks:
        new_ids = list(
            (
                await session.scalars(
                    insert(ChunkRow).returning(ChunkRow.id),
                    [
                        {
                            "document_id": doc.id,
                            "collection_id": doc.collection_id,
                            "ord": c.ord,
                            "heading": c.heading,
                            "content": c.content,
                            "token_count": c.token_count,
                            "content_hash": c.content_hash,
                        }
                        for c in chunks
                    ],
                )
            ).all()
        )
    if old_ids and new_ids:
        # Same text, same embedding: copied in SQL, so vectors never leave the database.
        await session.execute(
            text(
                """
                UPDATE chunks AS n
                SET embedding = o.embedding, embedding_model = o.embedding_model
                FROM chunks AS o
                WHERE n.id = ANY(CAST(:new_ids AS bigint[]))
                  AND o.id = ANY(CAST(:old_ids AS bigint[]))
                  AND o.content_hash = n.content_hash
                  AND o.embedding IS NOT NULL
                """
            ),
            {"new_ids": new_ids, "old_ids": old_ids},
        )
    if old_ids:
        await session.execute(delete(ChunkRow).where(ChunkRow.id.in_(old_ids)))


def _documents_query(*, include_content: bool) -> Select[DocumentRow, int, int]:
    counts = (
        select(
            ChunkRow.document_id,
            func.count().label("n"),
            func.count().filter(ChunkRow.embedding.is_(None)).label("pending"),
        )
        .group_by(ChunkRow.document_id)
        .subquery()
    )
    query = select(
        DocumentRow,
        func.coalesce(counts.c.n, 0).cast(Integer),
        func.coalesce(counts.c.pending, 0).cast(Integer),
    ).outerjoin(counts, counts.c.document_id == DocumentRow.id)
    return query if include_content else query.options(defer(DocumentRow.content))


def _document_hash(title: str, content: str) -> bytes:
    return hashlib.sha256(f"{title}\0{content}".encode()).digest()


def _collection(row: CollectionRow, document_count: int) -> Collection:
    return Collection(
        id=row.id, name=row.name, created_at=row.created_at, document_count=document_count
    )


def _document(
    row: DocumentRow, chunk_count: int, pending: int, *, embedding: bool, include_content=False
) -> Document:
    return Document(
        id=row.id,
        collection_id=row.collection_id,
        title=row.title,
        source=row.source,
        uri=row.uri,
        mime_type=row.mime_type,
        metadata=row.metadata_,
        created_at=row.created_at,
        updated_at=row.updated_at,
        chunk_count=chunk_count,
        chunks_pending=pending,
        # Without an embedding provider nothing is coming, so BM25 alone is "ready".
        status="indexing" if pending and embedding else "ready",
        content=row.content if include_content else None,
    )

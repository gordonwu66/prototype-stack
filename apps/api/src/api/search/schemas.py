from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

MAX_DOCUMENT_CHARS = 2_000_000


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class Collection(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    document_count: int = 0


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(max_length=MAX_DOCUMENT_CHARS)
    source: Literal["note", "url"] = "note"
    uri: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    content: str | None = Field(default=None, max_length=MAX_DOCUMENT_CHARS)
    uri: str | None = None
    metadata: dict[str, Any] | None = None


class Document(BaseModel):
    id: UUID
    collection_id: UUID
    title: str
    source: str
    uri: str | None
    mime_type: str | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    chunk_count: int
    # Chunks still waiting for an embedding; BM25 already finds them.
    chunks_pending: int
    status: Literal["indexing", "ready"]
    content: str | None = None  # only with ?include=content


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    collection_ids: list[UUID] | None = None  # None = every collection
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
    score: float  # the RRF score
    lexical_rank: int | None  # 1-based rank in the BM25 leg; None if that leg missed it
    semantic_rank: int | None


class SearchResponse(BaseModel):
    results: list[Hit]
    # The mode that actually ran: hybrid falls back to lexical without an embedding provider.
    mode: Literal["hybrid", "lexical", "semantic"]
    timings_ms: dict[str, float]

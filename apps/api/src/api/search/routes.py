from pathlib import PurePath
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile

from api.db.engine import database
from api.search import documents as docs
from api.search.embedder import embedder
from api.search.query import SemanticSearchUnavailable, search
from api.search.schemas import (
    MAX_DOCUMENT_CHARS,
    Collection,
    CollectionCreate,
    Document,
    DocumentCreate,
    DocumentUpdate,
    SearchRequest,
    SearchResponse,
)

router = APIRouter(tags=["search"])

TEXT_TYPES = {".md": "text/markdown", ".markdown": "text/markdown", ".txt": "text/plain"}


def _db() -> docs.Sessions:
    if not database.configured:
        raise HTTPException(503, "Search needs Postgres: set DB_HOST (see infra/rds/README.md)")
    return database.sessions


Db = Annotated[docs.Sessions, Depends(_db)]


def _embedding() -> bool:
    return embedder.provider is not None


async def _document_or_404(db: docs.Sessions, document_id: UUID, **kw: bool) -> Document:
    document = await docs.get_document(db, document_id, embedding=_embedding(), **kw)
    if document is None:
        raise HTTPException(404, "Document not found")
    return document


# --- collections


@router.get("/collections")
async def list_collections(db: Db) -> list[Collection]:
    return await docs.list_collections(db)


@router.post("/collections", status_code=201)
async def create_collection(db: Db, body: CollectionCreate) -> Collection:
    try:
        return await docs.create_collection(db, body.name)
    except docs.CollectionExists:
        raise HTTPException(409, f"A collection named {body.name!r} already exists") from None


@router.get("/collections/{collection_id}")
async def get_collection(db: Db, collection_id: UUID) -> Collection:
    collection = await docs.get_collection(db, collection_id)
    if collection is None:
        raise HTTPException(404, "Collection not found")
    return collection


@router.delete("/collections/{collection_id}", status_code=204)
async def delete_collection(db: Db, collection_id: UUID) -> None:
    if not await docs.delete_collection(db, collection_id):
        raise HTTPException(404, "Collection not found")
    embedder.notify()


# --- documents


@router.get("/collections/{collection_id}/documents")
async def list_documents(db: Db, collection_id: UUID) -> list[Document]:
    if await docs.get_collection(db, collection_id) is None:
        raise HTTPException(404, "Collection not found")
    return await docs.list_documents(db, collection_id, embedding=_embedding())


@router.post("/collections/{collection_id}/documents", status_code=201)
async def create_document(db: Db, collection_id: UUID, body: DocumentCreate) -> Document:
    document_id = await docs.create_document(db, collection_id, body, embedder.config)
    if document_id is None:
        raise HTTPException(404, "Collection not found")
    embedder.notify()
    return await _document_or_404(db, document_id)


@router.post("/collections/{collection_id}/documents/upload", status_code=201)
async def upload_document(
    db: Db, collection_id: UUID, file: UploadFile, title: Annotated[str | None, Form()] = None
) -> Document:
    name = PurePath(file.filename or "untitled.txt")
    mime_type = TEXT_TYPES.get(name.suffix.lower())
    if mime_type is None:
        raise HTTPException(415, "Only .md and .txt files are supported for now")
    data = await file.read(MAX_DOCUMENT_CHARS * 4 + 1)
    if len(data) > MAX_DOCUMENT_CHARS * 4:
        raise HTTPException(413, "File too large")
    try:
        content = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(415, "The file is not UTF-8 text") from None
    body = DocumentCreate(title=title or name.stem, content=content)
    document_id = await docs.create_document(
        db, collection_id, body, embedder.config, source="upload", mime_type=mime_type
    )
    if document_id is None:
        raise HTTPException(404, "Collection not found")
    embedder.notify()
    return await _document_or_404(db, document_id)


@router.get("/documents/{document_id}")
async def get_document(
    db: Db, document_id: UUID, include: Literal["content"] | None = None
) -> Document:
    return await _document_or_404(db, document_id, include_content=include == "content")


@router.put("/documents/{document_id}")
async def update_document(db: Db, document_id: UUID, body: DocumentUpdate) -> Document:
    if not await docs.update_document(db, document_id, body, embedder.config):
        raise HTTPException(404, "Document not found")
    embedder.notify()
    return await _document_or_404(db, document_id)


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(db: Db, document_id: UUID) -> None:
    if not await docs.delete_document(db, document_id):
        raise HTTPException(404, "Document not found")
    embedder.notify()


# --- search


@router.post("/search")
async def search_documents(db: Db, body: SearchRequest) -> SearchResponse:
    try:
        return await search(db, embedder.provider, body, embedder.config)
    except SemanticSearchUnavailable as exc:
        status = 503 if exc.retryable else 400
        raise HTTPException(status, f"{exc}; mode 'hybrid' falls back to BM25") from None

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.chat.routes import router as sessions_router
from api.chat.socket import sio
from api.chat.store import store
from api.config import settings
from api.db.engine import database
from api.llm.gateway import ModelSpec, gateway
from api.search.embedder import embedder
from api.search.routes import router as search_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # With a database configured, startup fails unless it is reachable and fully migrated.
    await database.start()
    try:
        await store.start()
        embedder.start()
        yield
    finally:
        await embedder.stop()
        await store.close()
        await database.close()


app = FastAPI(title="api", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(sessions_router)
app.include_router(search_router)
app.mount("/socket.io", socketio.ASGIApp(sio, socketio_path="socket.io"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/models")
def list_models() -> list[ModelSpec]:
    return gateway.models

from uuid import UUID

from fastapi import APIRouter, HTTPException

from api.chat.schemas import ChatSession, SessionUpdate
from api.chat.socket import cancel_generation, sio
from api.chat.store import store

# Sessions are created by the first chat:send, so there is no POST.
router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("")
async def list_sessions() -> list[ChatSession]:
    return await store.list_sessions()


@router.put("/{session_id}")
async def rename_session(session_id: UUID, body: SessionUpdate) -> ChatSession:
    session = await store.rename_session(session_id, body.title)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    await sio.emit("session:upserted", session.model_dump(mode="json"))
    return session


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: UUID) -> None:
    if not await store.delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    cancel_generation(session_id)
    await sio.emit("session:deleted", {"id": str(session_id)})

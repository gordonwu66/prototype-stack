"""Socket.IO chat protocol.

Client -> server (each answered with an ack: {"ok": true, ...} or {"ok": false, "error"}):
  session:join  {session_id}                       -> ack {session, messages}; watches this
                                                   session (and stops watching any other).
                                                   An unknown id is a draft: session is null.
  chat:send     {session_id, input, model, effort}  starts a streamed reply; creates the
                                                   session on its first message
  chat:cancel   {session_id}                       stops the in-flight reply

Server -> every client (sidebars):
  session:upserted  ChatSession                    insert or replace by id
  session:deleted   {id}

Server -> session room (every tab watching the session):
  chat:message  ChatMessage                        insert or replace by id; a reply is also
                                                   resent when its reasoning ends
  chat:delta    {session_id, id, seq, kind, text}  append text to message `id`'s content
                                                   (kind "text") or reasoning (kind "reasoning")
"""

import asyncio
import logging
import time
from typing import Any
from uuid import UUID

import socketio
from pydantic import ValidationError

from api.chat.schemas import CancelPayload, ChatMessage, JoinPayload, SendPayload
from api.chat.store import store
from api.config import settings
from api.llm.gateway import ModelSpec, gateway
from api.llm.types import Effort, LLMMessage, ReasoningDelta, StreamEnd, TextDelta

logger = logging.getLogger(__name__)

# CORS is left to FastAPI's CORSMiddleware, which also wraps this app; letting both set
# headers duplicates Access-Control-Allow-Origin. Auth will travel as a bearer token in the
# handshake, not a cookie, so websockets need no origin check.
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=[])
# One in-flight reply per session, keyed by session so any of its tabs can cancel it.
_generations: dict[UUID, asyncio.Task[None]] = {}
# Sessions whose chat:send is still saving its prompt, before the reply task exists.
_starting: set[UUID] = set()
# The in-flight reply per session. The store has it only as of its last save, so joins
# take its current content and seq from here.
_live: dict[UUID, ChatMessage] = {}

TITLE_LENGTH = 60


def _ok(**data: Any) -> dict[str, Any]:
    return {"ok": True, **data}


def _error(error: str) -> dict[str, Any]:
    return {"ok": False, "error": error}


def _title(text: str) -> str:
    line = " ".join(text.split())
    return line if len(line) <= TITLE_LENGTH else line[: TITLE_LENGTH - 1].rstrip() + "…"


def cancel_generation(session_id: UUID) -> None:
    if task := _generations.get(session_id):
        task.cancel()


async def session_join(sid: str, data: Any) -> dict[str, Any]:
    try:
        payload = JoinPayload.model_validate(data)
    except ValidationError as exc:
        return _error(str(exc))
    room = str(payload.session_id)
    for other in sio.rooms(sid):
        if other not in (sid, room):
            await sio.leave_room(sid, other)
    await sio.enter_room(sid, room)
    try:
        session = await store.get_session(payload.session_id)
        history = await store.history(payload.session_id)
    except Exception:
        logger.exception("Could not load session %s", payload.session_id)
        return _error("Could not load this chat")
    # Deltas streamed while the store was read arrive before this ack; the client replaces
    # its state with the snapshot, so the live reply must be dumped with no await after.
    if live := _live.get(payload.session_id):
        history = [live if m.id == live.id else m for m in history]
    return _ok(
        session=session.model_dump(mode="json") if session else None,
        messages=[m.model_dump(mode="json") for m in history],
    )


async def chat_send(sid: str, data: Any) -> dict[str, Any]:
    try:
        payload = SendPayload.model_validate(data)
    except ValidationError as exc:
        return _error(str(exc))
    spec = gateway.get(payload.model)
    if spec is None:
        return _error(f"Unknown model: {payload.model}")

    session_id = payload.session_id
    await sio.enter_room(sid, str(session_id))
    # No awaits from the busy check until the session is marked as starting.
    if session_id in _generations or session_id in _starting:
        return _error("A reply is already streaming in this session")
    _starting.add(session_id)
    try:
        session = await store.get_session(session_id)
        created = session is None
        if session is None:
            session = await store.create_session(session_id, _title(payload.input))
        prompt = ChatMessage(session_id=session_id, role="user", content=payload.input)
        await store.append(prompt)
        task = asyncio.create_task(_generate(prompt, spec, payload.effort))
        _generations[session_id] = task
        task.add_done_callback(lambda _: _generations.pop(session_id, None))
    except Exception:
        logger.exception("Could not save the message in session %s", session_id)
        return _error("Could not save your message")
    finally:
        _starting.discard(session_id)

    if created:
        await sio.emit("session:upserted", session.model_dump(mode="json"))
    return _ok()


async def chat_cancel(sid: str, data: Any) -> dict[str, Any]:
    try:
        payload = CancelPayload.model_validate(data)
    except ValidationError as exc:
        return _error(str(exc))
    cancel_generation(payload.session_id)
    return _ok()


sio.on("session:join", session_join)
sio.on("chat:send", chat_send)
sio.on("chat:cancel", chat_cancel)


async def _generate(prompt: ChatMessage, spec: ModelSpec, effort: Effort | None) -> None:
    session_id = prompt.session_id
    reply = ChatMessage(session_id=session_id, role="assistant", model=spec.id)
    _live[session_id] = reply
    try:
        await _stream_reply(prompt, reply, spec, effort)
        # Saved before the final emit, so once a client sees the reply end, the session takes
        # a new send and its history is complete. Cancelled and failed replies are kept too;
        # if the session was deleted meanwhile, there is no row left and this updates nothing.
        try:
            await store.save(reply)
        except Exception:
            logger.exception("Could not save reply %s", reply.id)
        await sio.emit("chat:message", reply.model_dump(mode="json"), room=str(session_id))
    finally:
        # Only now: a join before the save would otherwise snapshot the stale placeholder.
        _live.pop(session_id, None)


async def _stream_reply(
    prompt: ChatMessage, reply: ChatMessage, spec: ModelSpec, effort: Effort | None
) -> None:
    room = str(prompt.session_id)
    started = time.monotonic()
    try:
        # Provider-neutral text history, so a session can switch models between turns.
        history = [
            LLMMessage(m.role, m.content)
            for m in await store.history(prompt.session_id)
            if m.content
        ]
        await store.append(reply)
        await sio.emit("chat:message", prompt.model_dump(mode="json"), room=room)
        await sio.emit("chat:message", reply.model_dump(mode="json"), room=room)

        stream = gateway.stream(
            spec, history, system=settings.chat_system_prompt, effort=effort, cache_key=room
        )
        async for event in stream:
            match event:
                case TextDelta(text=text):
                    if reply.reasoning and reply.reasoning_ms is None:
                        # The answer starting ends the reasoning; resend the message so
                        # every tab shows the duration now rather than at the end.
                        reply.reasoning_ms = round((time.monotonic() - started) * 1000)
                        await sio.emit("chat:message", reply.model_dump(mode="json"), room=room)
                    reply.content += text
                    kind = "text"
                case ReasoningDelta(text=text):
                    reply.reasoning += text
                    kind = "reasoning"
                case StreamEnd(stop_reason=stop_reason, model=model, usage=usage):
                    reply.stop_reason = stop_reason
                    reply.model = f"{spec.provider}/{model}"
                    reply.usage = usage
                    continue
            reply.seq += 1
            delta = {
                "session_id": room,
                "id": reply.id,
                "seq": reply.seq,
                "kind": kind,
                "text": text,
            }
            await sio.emit("chat:delta", delta, room=room)
    except asyncio.CancelledError:
        reply.stop_reason = "cancelled"
    except Exception as exc:
        logger.exception("Reply failed (model=%s)", spec.id)
        reply.stop_reason = "error"
        reply.error = str(exc) or type(exc).__name__

    reply.stop_reason = reply.stop_reason or "end_turn"
    # Cancelled, failed, or reasoning-only: the model reasoned until the reply ended.
    if reply.reasoning and reply.reasoning_ms is None:
        reply.reasoning_ms = round((time.monotonic() - started) * 1000)

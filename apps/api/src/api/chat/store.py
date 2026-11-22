from typing import Protocol
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.chat.schemas import ChatMessage, ChatSession
from api.db.engine import Database, database
from api.db.models import ChatMessageRow, ChatSessionRow


class ChatStore(Protocol):
    async def start(self) -> None: ...
    async def close(self) -> None: ...
    async def list_sessions(self) -> list[ChatSession]: ...
    async def get_session(self, session_id: UUID) -> ChatSession | None: ...
    async def create_session(self, session_id: UUID, title: str) -> ChatSession: ...
    async def rename_session(self, session_id: UUID, title: str) -> ChatSession | None: ...
    async def delete_session(self, session_id: UUID) -> bool: ...
    async def history(self, session_id: UUID) -> list[ChatMessage]: ...
    async def append(self, message: ChatMessage) -> None: ...
    # Writes back a message appended earlier, e.g. a reply once it has finished streaming.
    async def save(self, message: ChatMessage) -> None: ...


class MemoryChatStore:
    """Process-local store, used when no database is configured. Lost on restart."""

    def __init__(self) -> None:
        self._sessions: dict[UUID, ChatSession] = {}
        self._messages: dict[UUID, list[ChatMessage]] = {}

    async def start(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def list_sessions(self) -> list[ChatSession]:
        return sorted(self._sessions.values(), key=lambda s: s.created_at, reverse=True)

    async def get_session(self, session_id: UUID) -> ChatSession | None:
        return self._sessions.get(session_id)

    async def create_session(self, session_id: UUID, title: str) -> ChatSession:
        session = ChatSession(id=session_id, title=title)
        self._sessions[session_id] = session
        self._messages[session_id] = []
        return session

    async def rename_session(self, session_id: UUID, title: str) -> ChatSession | None:
        if session := self._sessions.get(session_id):
            session.title = title
        return session

    async def delete_session(self, session_id: UUID) -> bool:
        self._messages.pop(session_id, None)
        return self._sessions.pop(session_id, None) is not None

    async def history(self, session_id: UUID) -> list[ChatMessage]:
        return list(self._messages.get(session_id, []))

    async def append(self, message: ChatMessage) -> None:
        if message.session_id not in self._sessions:
            raise LookupError(f"Session {message.session_id} does not exist")
        self._messages[message.session_id].append(message.model_copy())

    async def save(self, message: ChatMessage) -> None:
        messages = self._messages.get(message.session_id, [])
        for i, m in enumerate(messages):
            if m.id == message.id:
                messages[i] = message.model_copy()


def _session(row: ChatSessionRow) -> ChatSession:
    return ChatSession(id=row.id, title=row.title, created_at=row.created_at)


def _message(row: ChatMessageRow) -> ChatMessage:
    return ChatMessage.model_validate(
        {
            "id": str(row.id),
            "session_id": row.session_id,
            "role": row.role,
            "content": row.content,
            "reasoning": row.reasoning,
            "reasoning_ms": row.reasoning_ms,
            "model": row.model,
            "stop_reason": row.stop_reason,
            "error": row.error,
            "usage": row.usage,
            "seq": row.seq,
            "created_at": row.created_at,
        }
    )


def _mutable_fields(message: ChatMessage) -> dict:
    return {
        "content": message.content,
        "reasoning": message.reasoning,
        "reasoning_ms": message.reasoning_ms,
        "model": message.model,
        "stop_reason": message.stop_reason,
        "error": message.error,
        "usage": message.usage.model_dump() if message.usage else None,
        "seq": message.seq,
    }


class PostgresChatStore:
    """chat_sessions / chat_messages in Postgres. Assumes a single API process."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def start(self) -> None:
        # A reply still streaming when the last process stopped can never finish.
        async with self.db.begin() as db:
            await db.execute(
                update(ChatMessageRow)
                .where(ChatMessageRow.role == "assistant", ChatMessageRow.stop_reason.is_(None))
                .values(stop_reason="error", error="Interrupted by a server restart")
            )

    async def close(self) -> None:
        pass

    @property
    def db(self) -> async_sessionmaker[AsyncSession]:
        return self._database.sessions

    async def list_sessions(self) -> list[ChatSession]:
        async with self.db() as db:
            rows = await db.scalars(
                select(ChatSessionRow).order_by(ChatSessionRow.created_at.desc())
            )
            return [_session(r) for r in rows]

    async def get_session(self, session_id: UUID) -> ChatSession | None:
        async with self.db() as db:
            row = await db.get(ChatSessionRow, session_id)
            return _session(row) if row else None

    async def create_session(self, session_id: UUID, title: str) -> ChatSession:
        session = ChatSession(id=session_id, title=title)
        async with self.db.begin() as db:
            db.add(
                ChatSessionRow(id=session.id, title=session.title, created_at=session.created_at)
            )
        return session

    async def rename_session(self, session_id: UUID, title: str) -> ChatSession | None:
        async with self.db.begin() as db:
            row = await db.scalar(
                update(ChatSessionRow)
                .where(ChatSessionRow.id == session_id)
                .values(title=title)
                .returning(ChatSessionRow)
            )
            return _session(row) if row else None

    async def delete_session(self, session_id: UUID) -> bool:
        async with self.db.begin() as db:
            deleted = await db.scalar(
                delete(ChatSessionRow)
                .where(ChatSessionRow.id == session_id)
                .returning(ChatSessionRow.id)
            )
            return deleted is not None

    async def history(self, session_id: UUID) -> list[ChatMessage]:
        async with self.db() as db:
            rows = await db.scalars(
                select(ChatMessageRow)
                .where(ChatMessageRow.session_id == session_id)
                .order_by(ChatMessageRow.created_at, ChatMessageRow.id)
            )
            return [_message(r) for r in rows]

    async def append(self, message: ChatMessage) -> None:
        async with self.db.begin() as db:
            db.add(
                ChatMessageRow(
                    id=UUID(message.id),
                    session_id=message.session_id,
                    role=message.role,
                    created_at=message.created_at,
                    **_mutable_fields(message),
                )
            )

    async def save(self, message: ChatMessage) -> None:
        async with self.db.begin() as db:
            await db.execute(
                update(ChatMessageRow)
                .where(ChatMessageRow.id == UUID(message.id))
                .values(**_mutable_fields(message))
            )


store: ChatStore = PostgresChatStore(database) if database.configured else MemoryChatStore()

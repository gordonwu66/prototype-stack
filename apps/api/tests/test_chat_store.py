from collections.abc import AsyncIterator
from uuid import uuid4

import pytest

from api.chat.schemas import ChatMessage
from api.chat.store import ChatStore, MemoryChatStore, PostgresChatStore
from api.db.engine import database
from api.llm.types import Usage

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(params=["memory", "postgres"])
async def chat_store(request: pytest.FixtureRequest) -> AsyncIterator[ChatStore]:
    if request.param == "memory":
        yield MemoryChatStore()
        return
    if not database.configured:
        pytest.skip("Postgres not configured; run `pnpm test:api:db`")
    await database.start()
    store = PostgresChatStore(database)
    await store.start()
    yield store
    await store.close()
    await database.close()


async def test_session_round_trip(chat_store: ChatStore) -> None:
    session_id = uuid4()
    created = await chat_store.create_session(session_id, "First")
    assert await chat_store.get_session(session_id) == created
    assert (await chat_store.list_sessions())[0] == created

    renamed = await chat_store.rename_session(session_id, "Renamed")
    assert renamed is not None and renamed.title == "Renamed"
    assert await chat_store.rename_session(uuid4(), "x") is None

    assert await chat_store.delete_session(session_id)
    assert not await chat_store.delete_session(session_id)
    assert await chat_store.get_session(session_id) is None


async def test_messages_store_saved_state_in_order(chat_store: ChatStore) -> None:
    session_id = uuid4()
    await chat_store.create_session(session_id, "t")
    prompt = ChatMessage(session_id=session_id, role="user", content="Hi")
    reply = ChatMessage(session_id=session_id, role="assistant", model="fake/echo")
    await chat_store.append(prompt)
    await chat_store.append(reply)

    reply.content, reply.reasoning, reply.reasoning_ms, reply.seq = "Hello", "hmm", 12, 3
    reply.stop_reason = "end_turn"
    reply.usage = Usage(input_tokens=3, cached_input_tokens=1, output_tokens=2)
    # Until saved, the store keeps the reply as appended.
    assert (await chat_store.history(session_id))[1].content == ""
    await chat_store.save(reply)
    assert await chat_store.history(session_id) == [prompt, reply]


async def test_deleting_a_session_deletes_its_messages(chat_store: ChatStore) -> None:
    session_id = uuid4()
    await chat_store.create_session(session_id, "t")
    await chat_store.append(ChatMessage(session_id=session_id, role="user", content="Hi"))
    await chat_store.delete_session(session_id)
    assert await chat_store.history(session_id) == []
    with pytest.raises(Exception):  # noqa: B017 - LookupError in memory, IntegrityError in Postgres
        await chat_store.append(ChatMessage(session_id=session_id, role="user", content="Hi"))


async def test_restart_marks_unfinished_replies_interrupted(chat_store: ChatStore) -> None:
    if not isinstance(chat_store, PostgresChatStore):
        pytest.skip("Only the Postgres store outlives a restart")
    session_id = uuid4()
    await chat_store.create_session(session_id, "t")
    await chat_store.append(ChatMessage(session_id=session_id, role="assistant", content="par"))
    await chat_store.close()

    await chat_store.start()
    [reply] = await chat_store.history(session_id)
    assert (reply.stop_reason, reply.content) == ("error", "par")
    assert reply.error == "Interrupted by a server restart"

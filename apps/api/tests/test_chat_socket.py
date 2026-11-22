import asyncio
import socket
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any
from uuid import uuid4

import httpx
import pytest
import socketio
import uvicorn

from api.llm.gateway import gateway
from api.llm.types import (
    Effort,
    LLMMessage,
    ReasoningDelta,
    StreamEnd,
    StreamEvent,
    TextDelta,
    Usage,
)
from api.main import app

pytestmark = pytest.mark.anyio


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[list[LLMMessage]] = []
        self.cache_keys: list[str | None] = []

    async def stream(
        self,
        *,
        model: str,
        messages: Sequence[LLMMessage],
        system: str | None,
        effort: Effort | None,
        cache_key: str | None,
    ) -> AsyncIterator[StreamEvent]:
        self.calls.append(list(messages))
        self.cache_keys.append(cache_key)
        if model == "slow":
            await asyncio.sleep(30)
        if model == "pause":
            yield TextDelta("partial")
            await asyncio.sleep(30)
        yield ReasoningDelta("hmm")
        for word in ["Hello", " ", "world"]:
            yield TextDelta(word)
        yield StreamEnd("end_turn", model, Usage(input_tokens=3, output_tokens=2))


fake = FakeProvider()
gateway.register("fake", fake, ["echo", "slow", "pause"], supports_effort=True)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def base_url() -> AsyncIterator[str]:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
    serving = asyncio.create_task(server.serve(sockets=[sock]))
    while not server.started:
        await asyncio.sleep(0.01)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    await serving


@pytest.fixture
async def client(base_url: str) -> AsyncIterator[socketio.AsyncSimpleClient]:
    sio = socketio.AsyncSimpleClient()
    await sio.connect(base_url, transports=["websocket"])
    yield sio
    await sio.disconnect()


@pytest.fixture
async def http(base_url: str) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(base_url=base_url) as http:
        yield http


async def receive_until(
    client: socketio.AsyncSimpleClient, done: Callable[[str, Any], bool]
) -> list[list[Any]]:
    events = []
    while True:
        event = await client.receive(timeout=5)
        events.append(event)
        if done(event[0], event[1]):
            return events


def is_final_reply(name: str, payload: Any) -> bool:
    return name == "chat:message" and payload["role"] == "assistant" and payload["stop_reason"]


async def receive_reply(client: socketio.AsyncSimpleClient) -> list[list[Any]]:
    """Collect chat events until the assistant message arrives with a stop reason."""
    events = await receive_until(client, is_final_reply)
    return [e for e in events if e[0].startswith("chat:")]


async def test_streams_reply_and_keeps_history(client: socketio.AsyncSimpleClient) -> None:
    session_id = str(uuid4())
    assert await client.call("session:join", {"session_id": session_id}) == {
        "ok": True,
        "session": None,
        "messages": [],
    }

    ack = await client.call(
        "chat:send", {"session_id": session_id, "input": "Hi", "model": "fake/echo"}
    )
    assert ack == {"ok": True}
    events = await receive_reply(client)

    names = [e[0] for e in events]
    assert names == (
        ["chat:message", "chat:message", "chat:delta"]
        + ["chat:message"]  # resent as reasoning gives way to the answer
        + ["chat:delta"] * 3
        + ["chat:message"]
    )
    assert events[0][1]["content"] == "Hi"
    assert events[1][1]["reasoning_ms"] is None
    resent = events[3][1]
    assert (resent["reasoning"], resent["content"], resent["seq"]) == ("hmm", "", 1)
    assert isinstance(resent["reasoning_ms"], int)
    deltas = [e[1] for e in events if e[0] == "chat:delta"]
    assert [(d["seq"], d["kind"]) for d in deltas] == [
        (1, "reasoning"),
        (2, "text"),
        (3, "text"),
        (4, "text"),
    ]
    reply = events[-1][1]
    assert reply["content"] == "Hello world"
    assert reply["reasoning"] == "hmm"
    assert reply["reasoning_ms"] == resent["reasoning_ms"]
    assert reply["stop_reason"] == "end_turn"
    assert reply["model"] == "fake/echo"
    assert reply["usage"] == {"input_tokens": 3, "cached_input_tokens": 0, "output_tokens": 2}
    assert fake.cache_keys[-1] == session_id

    await client.call(
        "chat:send", {"session_id": session_id, "input": "Again", "model": "fake/echo"}
    )
    await receive_reply(client)
    assert [(m.role, m.content) for m in fake.calls[-1]] == [
        ("user", "Hi"),
        ("assistant", "Hello world"),
        ("user", "Again"),
    ]

    joined = await client.call("session:join", {"session_id": session_id})
    assert joined is not None
    assert [m["content"] for m in joined["messages"]] == [
        "Hi",
        "Hello world",
        "Again",
        "Hello world",
    ]


async def test_cancel_stops_reply(client: socketio.AsyncSimpleClient) -> None:
    session_id = str(uuid4())
    send = {"session_id": session_id, "input": "Hi", "model": "fake/slow"}
    assert await client.call("chat:send", send) == {"ok": True}

    busy = await client.call("chat:send", send)
    assert busy == {"ok": False, "error": "A reply is already streaming in this session"}

    assert await client.call("chat:cancel", {"session_id": session_id}) == {"ok": True}
    events = await receive_reply(client)
    assert events[-1][1]["stop_reason"] == "cancelled"


async def test_join_mid_stream_snapshots_the_live_reply(
    client: socketio.AsyncSimpleClient, base_url: str
) -> None:
    session_id = str(uuid4())
    send = {"session_id": session_id, "input": "Hi", "model": "fake/pause"}
    assert await client.call("chat:send", send) == {"ok": True}
    await receive_until(client, lambda name, _: name == "chat:delta")

    # A second tab joins while the reply is streaming; the store only has the placeholder.
    other = socketio.AsyncSimpleClient()
    await other.connect(base_url, transports=["websocket"])
    try:
        joined = await other.call("session:join", {"session_id": session_id})
        assert joined is not None
        reply = joined["messages"][-1]
        assert (reply["content"], reply["seq"], reply["stop_reason"]) == ("partial", 1, None)
    finally:
        await other.disconnect()

    await client.call("chat:cancel", {"session_id": session_id})
    events = await receive_reply(client)
    assert events[-1][1]["stop_reason"] == "cancelled"
    rejoined = await client.call("session:join", {"session_id": session_id})
    assert rejoined is not None
    saved = rejoined["messages"][-1]
    assert (saved["content"], saved["stop_reason"]) == ("partial", "cancelled")


async def test_rejects_unknown_model(client: socketio.AsyncSimpleClient) -> None:
    ack = await client.call(
        "chat:send", {"session_id": str(uuid4()), "input": "Hi", "model": "nope/nope"}
    )
    assert ack == {"ok": False, "error": "Unknown model: nope/nope"}


async def test_first_message_creates_session(
    client: socketio.AsyncSimpleClient, http: httpx.AsyncClient
) -> None:
    session_id = str(uuid4())
    prompt = "  Plan a   trip\nto Kyoto " + "in spring " * 10
    await client.call(
        "chat:send", {"session_id": session_id, "input": prompt, "model": "fake/echo"}
    )
    events = await receive_until(client, is_final_reply)

    created = [e[1] for e in events if e[0] == "session:upserted"]
    assert len(created) == 1
    title = created[0]["title"]
    assert title.startswith("Plan a trip to Kyoto in spring")
    assert len(title) == 60 and title.endswith("…")

    sessions = (await http.get("/sessions")).json()
    assert sessions[0] == created[0]

    await client.call(
        "chat:send", {"session_id": session_id, "input": "More", "model": "fake/echo"}
    )
    events = await receive_until(client, is_final_reply)
    assert not [e for e in events if e[0] == "session:upserted"]

    joined = await client.call("session:join", {"session_id": session_id})
    assert joined is not None
    assert joined["session"] == created[0]
    assert all(m["session_id"] == session_id for m in joined["messages"])


async def test_rename_and_delete_session(
    client: socketio.AsyncSimpleClient, http: httpx.AsyncClient
) -> None:
    session_id = str(uuid4())
    await client.call("chat:send", {"session_id": session_id, "input": "Hi", "model": "fake/slow"})
    await receive_until(client, lambda name, _: name == "session:upserted")

    res = await http.put(f"/sessions/{session_id}", json={"title": "Renamed"})
    assert res.status_code == 200
    assert res.json()["title"] == "Renamed"
    events = await receive_until(client, lambda name, _: name == "session:upserted")
    assert events[-1][1]["title"] == "Renamed"

    # Deleting cancels the in-flight reply.
    assert (await http.delete(f"/sessions/{session_id}")).status_code == 204
    seen: dict[str, Any] = {}

    def deleted_and_cancelled(name: str, payload: Any) -> bool:
        if name == "session:deleted" or is_final_reply(name, payload):
            seen[name] = payload
        return len(seen) == 2

    await receive_until(client, deleted_and_cancelled)
    assert seen["session:deleted"] == {"id": session_id}
    assert seen["chat:message"]["stop_reason"] == "cancelled"

    assert session_id not in [s["id"] for s in (await http.get("/sessions")).json()]
    joined = await client.call("session:join", {"session_id": session_id})
    assert joined == {"ok": True, "session": None, "messages": []}
    assert (await http.put(f"/sessions/{session_id}", json={"title": "x"})).status_code == 404
    assert (await http.delete(f"/sessions/{session_id}")).status_code == 404

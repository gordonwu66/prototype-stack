"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  type ChatDelta,
  type ChatMessage,
  type ChatSession,
  type Effort,
  listModels,
  listSessions,
  type ModelSpec,
} from "@/lib/chat";
import { useChatSocket } from "./socket-provider";

const ACK_TIMEOUT_MS = 10_000;
const CONNECTION_TOAST = "chat:connection";

function toastConnectionError() {
  // The fixed id collapses repeat sends into one toast, kept up until reconnect.
  toast.error("Can't reach the server", {
    id: CONNECTION_TOAST,
    description: "Reload the page or try again later.",
    duration: Number.POSITIVE_INFINITY,
  });
}

function upsert<T extends { id: string }>(items: T[], item: T): T[] {
  const i = items.findIndex((x) => x.id === item.id);
  return i === -1 ? [...items, item] : items.with(i, item);
}

function applyDelta(messages: ChatMessage[], delta: ChatDelta): ChatMessage[] {
  return messages.map((m) => {
    // Skip deltas already folded into the snapshot we joined with.
    if (m.id !== delta.id || delta.seq <= m.seq) return m;
    return delta.kind === "text"
      ? { ...m, seq: delta.seq, content: m.content + delta.text }
      : { ...m, seq: delta.seq, reasoning: m.reasoning + delta.text };
  });
}

/**
 * Messages for one session. `sessionId` null is a new chat: the first send picks
 * its id, and the server creates the session.
 */
export function useChat(sessionId: string | null) {
  const { socket, connected } = useChatSocket();
  const [session, setSession] = useState<ChatSession | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [error, setError] = useState<string | null>(null);
  // The session whose first join has answered; until then its transcript is unknown.
  const [joinedId, setJoinedId] = useState<string | null>(null);

  useEffect(() => {
    if (!socket || !sessionId) return;
    let active = true;

    // Rooms are per connection, so (re)join on every connect. The snapshot also
    // catches up on anything streamed while disconnected.
    const join = async () => {
      try {
        const res = await socket
          .timeout(ACK_TIMEOUT_MS)
          .emitWithAck("session:join", { session_id: sessionId });
        if (!active) return;
        if (res.ok) {
          setSession(res.session);
          setMessages(res.messages);
        } else {
          setError(res.error);
        }
        setJoinedId(sessionId);
      } catch {
        if (!active) return;
        setError("Timed out joining the chat session");
        setJoinedId(sessionId);
      }
    };
    const onSession = (s: ChatSession) => {
      if (s.id === sessionId) setSession(s);
    };
    const onMessage = (m: ChatMessage) => {
      if (m.session_id === sessionId) setMessages((ms) => upsert(ms, m));
    };
    const onDelta = (d: ChatDelta) => {
      if (d.session_id === sessionId) setMessages((ms) => applyDelta(ms, d));
    };

    socket.on("connect", join);
    socket.on("session:upserted", onSession);
    socket.on("chat:message", onMessage);
    socket.on("chat:delta", onDelta);
    if (socket.connected) join();
    return () => {
      active = false;
      socket.off("connect", join);
      socket.off("session:upserted", onSession);
      socket.off("chat:message", onMessage);
      socket.off("chat:delta", onDelta);
    };
  }, [socket, sessionId]);

  // Retire the connection toast once the socket is back, or when leaving the
  // chat (the Toaster outlives it, and the toast never times out).
  useEffect(() => {
    if (connected) toast.dismiss(CONNECTION_TOAST);
    return () => {
      toast.dismiss(CONNECTION_TOAST);
    };
  }, [connected]);

  /**
   * Resolves to the session id the message went to, or null if it was rejected.
   * Send failures are toasts; `error` is left for the session failing to load.
   */
  const send = useCallback(
    async (input: string, model: string, effort: Effort | null) => {
      // Socket.IO buffers emits while disconnected and flushes them on
      // reconnect, so a send that timed out here could still land later.
      if (!socket?.connected) {
        toastConnectionError();
        return null;
      }
      const id = sessionId ?? crypto.randomUUID();
      setError(null);
      try {
        const res = await socket
          .timeout(ACK_TIMEOUT_MS)
          .emitWithAck("chat:send", { session_id: id, input, model, effort });
        if (!res.ok) toast.error(res.error);
        return res.ok ? id : null;
      } catch {
        toast.error("The server did not respond");
        return null;
      }
    },
    [socket, sessionId],
  );

  const cancel = useCallback(() => {
    if (sessionId) socket?.emit("chat:cancel", { session_id: sessionId });
  }, [socket, sessionId]);

  const last = messages.at(-1);
  const streaming = last?.role === "assistant" && last.stop_reason === null;
  const loading = sessionId !== null && joinedId !== sessionId;

  return {
    session,
    messages,
    loading,
    streaming,
    error,
    send,
    cancel,
  };
}

/** All sessions, newest first, kept live by session:upserted / session:deleted. */
export function useSessions() {
  const { socket } = useChatSocket();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  // The first load has finished, successfully or not.
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!socket) return;
    // Refetch on every connect to pick up changes missed while disconnected.
    const load = () =>
      listSessions()
        .then((list) => {
          setSessions(list);
          setError(null);
        })
        .catch(() => setError("Could not load chats"))
        .finally(() => setLoaded(true));
    const onUpserted = (s: ChatSession) =>
      setSessions((ss) =>
        ss.some((x) => x.id === s.id) ? upsert(ss, s) : [s, ...ss],
      );
    const onDeleted = ({ id }: { id: string }) =>
      setSessions((ss) => ss.filter((s) => s.id !== id));

    socket.on("connect", load);
    socket.on("session:upserted", onUpserted);
    socket.on("session:deleted", onDeleted);
    if (socket.connected) load();
    return () => {
      socket.off("connect", load);
      socket.off("session:upserted", onUpserted);
      socket.off("session:deleted", onDeleted);
    };
  }, [socket]);

  return { sessions, loaded, error };
}

export function useModels() {
  const { socket } = useChatSocket();
  const [models, setModels] = useState<ModelSpec[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!socket) return;
    // Refetch on every connect so a page loaded before the server was up recovers.
    const load = () =>
      listModels()
        .then((list) => {
          setModels(list);
          setError(null);
        })
        .catch(() => setError("Could not load models"));

    socket.on("connect", load);
    if (socket.connected) load();
    return () => {
      socket.off("connect", load);
    };
  }, [socket]);

  return { models, error };
}

/** A string preference persisted in localStorage, read after mount. */
export function useStoredState<T extends string>(key: string, initial: T) {
  const [value, setValue] = useState<T>(initial);

  useEffect(() => {
    const stored = localStorage.getItem(key);
    if (stored !== null) setValue(stored as T);
  }, [key]);

  const update = useCallback(
    (next: T) => {
      localStorage.setItem(key, next);
      setValue(next);
    },
    [key],
  );

  return [value, update] as const;
}

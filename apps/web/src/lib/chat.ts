import { io, type Socket } from "socket.io-client";
import { API_URL, json, request } from "./api";

// Mirrors apps/api/src/api/chat/schemas.py and the protocol in api/chat/socket.py.

export type Effort = "low" | "medium" | "high" | "xhigh" | "max";

export type StopReason =
  | "end_turn"
  | "max_tokens"
  | "refusal"
  | "cancelled"
  | "error";

export interface ChatSession {
  id: string;
  title: string;
  created_at: string;
}

export interface ChatMessage {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  reasoning: string;
  /** null while reasoning is in progress, and on replies with none */
  reasoning_ms: number | null;
  model: string | null;
  /** null while an assistant message is still streaming */
  stop_reason: StopReason | null;
  error: string | null;
  /** input_tokens counts the cached ones too */
  usage: {
    input_tokens: number;
    cached_input_tokens: number;
    output_tokens: number;
  } | null;
  seq: number;
  created_at: string;
}

export interface ChatDelta {
  session_id: string;
  id: string;
  seq: number;
  kind: "text" | "reasoning";
  text: string;
}

export interface ModelSpec {
  id: string;
  provider: string;
  model: string;
  supports_effort: boolean;
}

type Ack<T = object> = ({ ok: true } & T) | { ok: false; error: string };

interface ServerToClientEvents {
  "session:upserted": (session: ChatSession) => void;
  "session:deleted": (payload: { id: string }) => void;
  "chat:message": (message: ChatMessage) => void;
  "chat:delta": (delta: ChatDelta) => void;
}

interface ClientToServerEvents {
  "session:join": (
    payload: { session_id: string },
    ack: (
      res: Ack<{ session: ChatSession | null; messages: ChatMessage[] }>,
    ) => void,
  ) => void;
  "chat:send": (
    payload: {
      session_id: string;
      input: string;
      model: string;
      effort: Effort | null;
    },
    ack: (res: Ack) => void,
  ) => void;
  "chat:cancel": (payload: { session_id: string }) => void;
}

export type ChatSocket = Socket<ServerToClientEvents, ClientToServerEvents>;

export function connectChatSocket(): ChatSocket {
  // WebSocket only: skipping the long-polling fallback means no sticky sessions
  // are needed behind a load balancer.
  return io(API_URL, { transports: ["websocket"] });
}

export const listModels = () => request<ModelSpec[]>("/models");

export const listSessions = () => request<ChatSession[]>("/sessions");

export const renameSession = (id: string, title: string) =>
  request<ChatSession>(`/sessions/${id}`, json("PUT", { title }));

export const deleteSession = (id: string) =>
  request<void>(`/sessions/${id}`, { method: "DELETE" });

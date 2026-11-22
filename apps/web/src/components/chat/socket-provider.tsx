"use client";

import { createContext, type ReactNode, use, useEffect, useState } from "react";
import { type ChatSocket, connectChatSocket } from "@/lib/chat";

const ChatSocketContext = createContext<{
  socket: ChatSocket | null;
  connected: boolean;
}>({ socket: null, connected: false });

/** One Socket.IO connection for the app, shared by the sidebar and the chat. */
export function ChatSocketProvider({ children }: { children: ReactNode }) {
  const [socket, setSocket] = useState<ChatSocket | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const socket = connectChatSocket();
    socket.on("connect", () => setConnected(true));
    socket.on("disconnect", () => setConnected(false));
    setSocket(socket);
    return () => {
      socket.disconnect();
    };
  }, []);

  return (
    <ChatSocketContext value={{ socket, connected }}>
      {children}
    </ChatSocketContext>
  );
}

export function useChatSocket() {
  return use(ChatSocketContext);
}

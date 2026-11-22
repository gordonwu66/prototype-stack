"use client";

import { ChevronRight, Loader } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { ChatMessage, Effort, StopReason } from "@/lib/chat";
import { cn } from "@/lib/utils";
import { ChatInput } from "./chat-input";
import { Markdown } from "./markdown";
import { ElapsedTimer, PixelLoader } from "./pixel-loader";
import { useChatSocket } from "./socket-provider";
import { useChat, useModels, useStoredState } from "./use-chat";
import { useSmoothedText } from "./use-smoothed-text";
import { useStickToBottom } from "./use-stick-to-bottom";

const EFFORTS: Effort[] = ["low", "medium", "high", "xhigh", "max"];
const EFFORT_LABELS: Record<Effort, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
  xhigh: "Extra high",
  max: "Max",
};
const DEFAULT_EFFORT: Effort = "medium";

const STOP_NOTICES: Partial<Record<StopReason, string>> = {
  max_tokens: "Stopped at the output limit.",
  refusal: "The model declined to answer.",
  cancelled: "Stopped.",
};

/** The reading column: messages, composer and empty state share one width. */
const column = "mx-auto w-full max-w-3xl px-4";

// Equal side padding so the hover background frames the label evenly.
const toolbarTrigger =
  "max-w-48 border-transparent bg-transparent px-2 text-xs text-muted-foreground shadow-none hover:bg-muted hover:text-foreground dark:bg-transparent dark:hover:bg-muted";

// Roomier menu rows than the select defaults. Items keep `pr-8` for the check mark.
const menuGroup = "p-1.5";
const menuLabel = "px-2.5 py-1.5";
const menuItem = "py-1.5 pl-2.5";

/** `sessionId` null renders a new chat; its first message creates the session. */
export function Chat({ sessionId }: { sessionId: string | null }) {
  const router = useRouter();
  const { socket } = useChatSocket();
  const { session, messages, loading, streaming, error, send, cancel } =
    useChat(sessionId);
  const { models, error: modelsError } = useModels();
  // Persisted so the choice survives switching chats and reloads.
  const [modelId, setModelId] = useStoredState<string>("chat:model", "");
  const [storedEffort, setEffort] = useStoredState<Effort>(
    "chat:effort",
    DEFAULT_EFFORT,
  );
  // Older builds stored "" for "default effort"; treat anything unknown as the default.
  const effort = EFFORTS.includes(storedEffort) ? storedEffort : DEFAULT_EFFORT;
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useStickToBottom();

  // Leave a chat that was deleted, here or in another tab.
  useEffect(() => {
    if (!socket || !sessionId) return;
    const onDeleted = ({ id }: { id: string }) => {
      if (id === sessionId) router.replace("/chat");
    };
    socket.on("session:deleted", onDeleted);
    return () => {
      socket.off("session:deleted", onDeleted);
    };
  }, [socket, sessionId, router]);

  const model = models.find((m) => m.id === modelId) ?? models[0];
  const providers = [...new Set(models.map((m) => m.provider))];

  async function submit() {
    const text = input.trim();
    if (!text || !model || streaming || sending) return;
    setSending(true);
    const sentTo = await send(
      text,
      model.id,
      model.supports_effort ? effort : null,
    );
    if (sentTo && !sessionId) {
      // This page unmounts on navigation; keep the draft on screen until it does.
      router.push(`/chat/${sentTo}`);
      return;
    }
    if (sentTo) setInput("");
    setSending(false);
  }

  const composer = (
    <ChatInput
      value={input}
      onValueChange={setInput}
      onSubmit={submit}
      onStop={cancel}
      streaming={streaming}
      canSend={!!input.trim() && !!model && !sending && !loading}
      disabled={loading}
    >
      <Select
        value={model?.id ?? ""}
        onValueChange={setModelId}
        disabled={models.length === 0}
      >
        <SelectTrigger size="sm" aria-label="Model" className={toolbarTrigger}>
          <SelectValue placeholder="No models" />
        </SelectTrigger>
        <SelectContent position="popper" side="top" align="start">
          {providers.map((provider) => (
            <SelectGroup key={provider} className={menuGroup}>
              <SelectLabel className={menuLabel}>{provider}</SelectLabel>
              {models
                .filter((m) => m.provider === provider)
                .map((m) => (
                  <SelectItem key={m.id} value={m.id} className={menuItem}>
                    {m.model}
                  </SelectItem>
                ))}
            </SelectGroup>
          ))}
        </SelectContent>
      </Select>
      {model?.supports_effort && (
        <Select value={effort} onValueChange={(v) => setEffort(v as Effort)}>
          <SelectTrigger
            size="sm"
            aria-label="Effort"
            className={toolbarTrigger}
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent position="popper" side="top" align="start">
            <SelectGroup className={menuGroup}>
              <SelectLabel className={menuLabel}>Effort level</SelectLabel>
              {EFFORTS.map((level) => (
                <SelectItem key={level} value={level} className={menuItem}>
                  {EFFORT_LABELS[level]} effort
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
      )}
    </ChatInput>
  );

  const errorText = error ?? modelsError;
  const errorLine = errorText && (
    <p className="pb-2 text-sm text-destructive">{errorText}</p>
  );

  return (
    // Full width so the header border spans the main area; content keeps to `column`.
    <div className="flex h-full w-full flex-col">
      {/* Fixed height so the bar doesn't jump while the title loads. */}
      <header className="flex h-12 shrink-0 items-center border-b px-4">
        <h1 className="truncate">
          {session?.title ?? (sessionId ? "" : "New chat")}
        </h1>
      </header>

      {loading ? (
        <div className="flex flex-1 items-center justify-center">
          <Loader
            aria-label="Loading chat"
            className="size-4 animate-spin text-muted-foreground"
          />
        </div>
      ) : messages.length === 0 ? (
        // Nothing to read yet: the composer sits in the middle of the page.
        <div
          className={cn(
            column,
            "flex flex-1 flex-col justify-center gap-4 pb-[12vh]",
          )}
        >
          <p className="text-center text-sm text-muted-foreground">
            {models.length === 0 && !modelsError
              ? "No models configured. Set a provider key in apps/api/.env."
              : "Send a message to start."}
          </p>
          <div>
            {errorLine}
            {composer}
          </div>
        </div>
      ) : (
        // The scroll area stays full width so the gutters scroll too and the
        // scrollbar sits at the window edge; only its content is narrowed.
        <ScrollArea viewportRef={scrollRef} className="min-h-0 flex-1">
          <div className={cn(column, "flex flex-col gap-6 py-6")}>
            {messages.map((m) =>
              m.role === "user" ? (
                <UserMessage key={m.id} message={m} />
              ) : (
                <AssistantMessage key={m.id} message={m} />
              ),
            )}
          </div>
        </ScrollArea>
      )}

      {(loading || messages.length > 0) && (
        <div className={cn(column, "pb-4")}>
          {errorLine}
          {composer}
        </div>
      )}
    </div>
  );
}

/** "Thought for 12s"; minutes once past one, since max effort can run that long. */
function thoughtFor(ms: number | null) {
  if (ms === null) return "Thought";
  const s = Math.max(1, Math.round(ms / 1000));
  return s < 60
    ? `Thought for ${s}s`
    : `Thought for ${Math.floor(s / 60)}m ${s % 60}s`;
}

function usageLine(usage: NonNullable<ChatMessage["usage"]>) {
  const cached = usage.cached_input_tokens
    ? ` (${usage.cached_input_tokens} cached)`
    : "";
  return `${usage.input_tokens} in${cached} · ${usage.output_tokens} out`;
}

function UserMessage({ message }: { message: ChatMessage }) {
  return (
    <div className="max-w-[80%] self-end whitespace-pre-wrap break-words rounded-2xl bg-muted px-4 py-2">
      {message.content}
    </div>
  );
}

function AssistantMessage({ message }: { message: ChatMessage }) {
  const pending = message.stop_reason === null;
  const content = useSmoothedText(message.content);
  const reasoning = useSmoothedText(message.reasoning);
  const notice = message.stop_reason && STOP_NOTICES[message.stop_reason];
  // The server stamps reasoning_ms as the answer starts, so this ends with it.
  const thinking = pending && message.reasoning_ms === null;

  return (
    <div className="group flex flex-col gap-2">
      {reasoning && (
        // Open while thinking; collapses once the answer starts.
        <details
          open={thinking}
          className="group/thinking text-sm text-muted-foreground"
        >
          <summary className="flex w-fit cursor-pointer select-none items-center gap-1 transition-colors hover:text-foreground [&::-webkit-details-marker]:hidden">
            <span className={cn(thinking && "text-shimmer")}>
              {thinking ? "Thinking" : thoughtFor(message.reasoning_ms)}
            </span>
            {/* Same anchor as the loader's timer, so the count carries on from it. */}
            {thinking && (
              <ElapsedTimer since={message.created_at} className="ml-1" />
            )}
            <ChevronRight
              aria-hidden
              className="size-3.5 transition-transform group-open/thinking:rotate-90"
            />
          </summary>
          <Markdown streaming={pending} className="mt-2">
            {reasoning}
          </Markdown>
        </details>
      )}
      {content ? (
        <Markdown streaming={pending} className="leading-7">
          {content}
        </Markdown>
      ) : (
        pending &&
        !reasoning && (
          <PixelLoader label="Thinking" since={message.created_at} />
        )
      )}
      {(notice || message.error) && (
        <p className="text-sm text-amber-600 dark:text-amber-500">
          {message.error ?? notice}
        </p>
      )}
      {/* Opacity, not display, so revealing the line doesn't shift the layout. */}
      <span className="text-xs text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100">
        {message.model}
        {message.usage && ` · ${usageLine(message.usage)}`}
      </span>
    </div>
  );
}

"use client";

import { Loader2, Send, Square } from "lucide-react";
import {
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
  useEffect,
  useRef,
  useState,
} from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

interface ChatInputProps {
  value: string;
  onValueChange: (value: string) => void;
  onSubmit: () => void;
  onStop: () => void;
  /** A reply is streaming: the send button becomes a stop button. */
  streaming: boolean;
  /** Whether the current draft can be sent (has text, a model, a connection...). */
  canSend: boolean;
  /** The session is still loading, so nothing can be typed yet. */
  disabled?: boolean;
  /** Controls for the left end of the toolbar, such as the model picker. */
  children?: ReactNode;
  className?: string;
}

/** Composer: a growing textarea over a toolbar of controls and a send/stop button. */
export function ChatInput({
  value,
  onValueChange,
  onSubmit,
  onStop,
  streaming,
  canSend,
  disabled = false,
  children,
  className,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  // Spinner on the stop button from the click until the reply settles.
  const [stopping, setStopping] = useState(false);
  if (stopping && !streaming) setStopping(false);

  // Focus whenever the composer becomes usable: on mount, and once a session loads.
  useEffect(() => {
    if (!disabled) textareaRef.current?.focus();
  }, [disabled]);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (canSend && !streaming) onSubmit();
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      e.currentTarget.form?.requestSubmit();
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className={cn(
        "rounded-xl border border-input bg-card shadow-xs",
        className,
      )}
    >
      <Textarea
        ref={textareaRef}
        aria-label="Message"
        placeholder="Send a message…"
        rows={2}
        value={value}
        disabled={disabled}
        onChange={(e) => onValueChange(e.target.value)}
        onKeyDown={handleKeyDown}
        className="max-h-[min(50vh,480px)] min-h-20 resize-none rounded-none border-0 bg-transparent p-4 shadow-none focus-visible:ring-0 disabled:bg-transparent dark:bg-transparent dark:disabled:bg-transparent"
      />
      {/* `pl-2` plus the triggers' `px-2` lines their labels up with the textarea's `p-4`. */}
      <div className="flex items-center justify-between gap-2 pr-4 pb-2 pl-2">
        <div className="flex min-w-0 items-center gap-1 overflow-x-auto">
          {children}
        </div>
        {streaming ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                size="icon"
                aria-label={stopping ? "Stopping" : "Stop"}
                disabled={stopping}
                onClick={() => {
                  setStopping(true);
                  onStop();
                }}
              >
                {stopping ? (
                  <Loader2 className="animate-spin" />
                ) : (
                  <Square className="size-3.5 fill-current" />
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              {stopping ? "Stopping…" : "Stop generating"}
            </TooltipContent>
          </Tooltip>
        ) : (
          <Tooltip>
            {/* A disabled button fires no pointer events, so the span carries the hover. */}
            <TooltipTrigger asChild>
              <span className="inline-flex">
                <Button
                  type="submit"
                  size="icon"
                  aria-label="Send"
                  disabled={!canSend}
                >
                  <Send />
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent>Send (Enter)</TooltipContent>
          </Tooltip>
        )}
      </div>
    </form>
  );
}

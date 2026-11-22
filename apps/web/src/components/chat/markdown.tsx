"use client";

import { code } from "@streamdown/code";
import { Streamdown } from "streamdown";
import { cn } from "@/lib/utils";

// Module-level so Streamdown's memoized blocks see a stable reference.
const plugins = { code };

/**
 * Markdown for model output. Streamdown closes unterminated syntax while text is
 * still arriving and re-renders only the block that changed; `streaming` also
 * holds back code-block controls until the reply settles.
 */
export function Markdown({
  children,
  streaming,
  className,
}: {
  children: string;
  streaming: boolean;
  className?: string;
}) {
  return (
    <Streamdown
      plugins={plugins}
      isAnimating={streaming}
      className={cn("min-w-0 break-words", className)}
    >
      {children}
    </Streamdown>
  );
}

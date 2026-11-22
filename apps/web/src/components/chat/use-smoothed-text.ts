"use client";

import { useEffect, useRef, useState } from "react";

const MIN_CHARS_PER_FRAME = 3; // ~180 chars/s at 60fps
const CATCHUP_FRAMES = 12; // drain whatever is buffered within ~200ms
const MAX_BACKLOG = 500; // past this, jump to the end rather than type it out

/**
 * Reveals appended text at a steady pace instead of in network-sized bursts. Text
 * present at mount shows at once, so history and a stream joined midway don't
 * replay. The tail that lands with the end of a stream still drains smoothly.
 */
export function useSmoothedText(text: string): string {
  const [shown, setShown] = useState(text);
  const target = useRef(text);
  const revealed = useRef(text.length);
  const frame = useRef<number | null>(null);

  useEffect(() => {
    target.current = text;
    revealed.current = Math.min(revealed.current, text.length);
    // Caught up, or the running loop will read the new target.
    if (frame.current !== null || revealed.current === text.length) return;

    const tick = () => {
      const full = target.current;
      const backlog = full.length - revealed.current;
      if (backlog <= 0) {
        frame.current = null;
        return;
      }
      let next =
        backlog > MAX_BACKLOG
          ? full.length
          : revealed.current +
            Math.max(MIN_CHARS_PER_FRAME, Math.ceil(backlog / CATCHUP_FRAMES));
      // Don't cut between the halves of a surrogate pair (emoji).
      if (next < full.length && isLowSurrogate(full.charCodeAt(next))) next++;
      revealed.current = next;
      setShown(full.slice(0, next));
      frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
  }, [text]);

  useEffect(
    () => () => {
      if (frame.current !== null) cancelAnimationFrame(frame.current);
      frame.current = null;
    },
    [],
  );

  // Text that was replaced rather than appended to shows as-is.
  return text.startsWith(shown) ? shown : text;
}

function isLowSurrogate(code: number) {
  return code >= 0xdc00 && code <= 0xdfff;
}

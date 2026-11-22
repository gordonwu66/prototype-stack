"use client";

import { useCallback } from "react";

/** Within this many px of the bottom still counts as "at the bottom". */
const BOTTOM_THRESHOLD_PX = 80;

/**
 * Callback ref for a scroll container whose first child is the message list. Keeps
 * the view at the bottom as content grows (deltas, smoothed text, reflow) while the
 * user is there, and stops following once they scroll up to read.
 */
export function useStickToBottom() {
  return useCallback((el: HTMLDivElement) => {
    let pinned = true;
    el.scrollTop = el.scrollHeight;

    const onScroll = () => {
      pinned =
        el.scrollHeight - el.scrollTop - el.clientHeight <= BOTTOM_THRESHOLD_PX;
    };
    const observer = new ResizeObserver(() => {
      if (pinned) el.scrollTop = el.scrollHeight;
    });

    el.addEventListener("scroll", onScroll, { passive: true });
    if (el.firstElementChild) observer.observe(el.firstElementChild);
    return () => {
      el.removeEventListener("scroll", onScroll);
      observer.disconnect();
    };
  }, []);
}

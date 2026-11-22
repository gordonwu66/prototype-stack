"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

/*
 * 3×3 pixel grid with a chevron (">") wavefront driving right. Each cell's delay
 * is its distance along the chevron; the 650ms cycle is shorter than the sweep,
 * so two fronts are always in flight. Reduced motion holds every cell dim.
 */
const CELLS = Array.from({ length: 9 }, (_, i) => {
  const row = Math.floor(i / 3);
  const col = i % 3;
  return { id: i, delay: (col + Math.abs(row - 1)) * 90 };
});

/** Fast replies never show a number; the timer fades in once a wait is noticeable. */
const SHOW_TIMER_AFTER_MS = 1000;

/**
 * Status line for work in flight: pixel grid, shimmering label, elapsed time.
 * `since` (ms or an ISO string) anchors the timer to when the work began, so it
 * survives a reload; it defaults to when the loader mounted.
 */
export function PixelLoader({
  label,
  since,
  className,
}: {
  label: string;
  since?: number | string;
  className?: string;
}) {
  return (
    <div className={cn("flex w-fit items-center gap-2.5", className)}>
      <span
        aria-hidden
        className="grid shrink-0 grid-cols-[repeat(3,4px)] gap-[1.5px] text-foreground"
      >
        {CELLS.map(({ id, delay }) => (
          <span
            key={id}
            className="size-1 rounded-[1px] bg-current opacity-15 motion-safe:animate-pixel"
            style={{ animationDelay: `${delay}ms` }}
          />
        ))}
      </span>
      {/* Only the label is live: a ticking timer inside it would be re-announced. */}
      <output className="text-shimmer text-[13px] font-medium">{label}</output>
      <ElapsedTimer since={since} />
    </div>
  );
}

/**
 * Live elapsed time, hidden until a wait is noticeable. Its own component so the
 * 100ms tick re-renders only the number. Timers sharing a `since` show the same
 * time, so one can take over from another mid-count.
 */
export function ElapsedTimer({
  since,
  className,
}: {
  since?: number | string;
  className?: string;
}) {
  const elapsed = useElapsed(since);
  // Mounting already past the threshold means taking over from another timer;
  // fading in again would make the number blink.
  const [fade] = useState(elapsed < SHOW_TIMER_AFTER_MS);

  if (elapsed < SHOW_TIMER_AFTER_MS) return null;
  return (
    <span
      aria-hidden
      className={cn(
        "font-mono text-xs text-muted-foreground tabular-nums",
        fade && "animate-in fade-in duration-300",
        className,
      )}
    >
      {formatElapsed(elapsed)}
    </span>
  );
}

function useElapsed(since?: number | string) {
  const [mountedAt] = useState(() => Date.now());
  const [now, setNow] = useState(mountedAt);

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(id);
  }, []);

  const start = typeof since === "string" ? Date.parse(since) : since;
  // A start ahead of this clock (skew with the server) counts from mount instead.
  const origin = start !== undefined && start <= mountedAt ? start : mountedAt;
  return Math.max(0, now - origin);
}

function formatElapsed(ms: number) {
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const rest = String(Math.floor(seconds % 60)).padStart(2, "0");
  return `${Math.floor(seconds / 60)}m ${rest}s`;
}

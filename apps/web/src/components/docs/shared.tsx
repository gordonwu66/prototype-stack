"use client";

import { ChevronRight, Loader, Loader2 } from "lucide-react";
import Link from "next/link";
import { Fragment, type ReactNode } from "react";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { DocumentMeta } from "@/lib/search";
import { cn } from "@/lib/utils";

/** The reading column, the same width as the chat transcript. */
export const column = "mx-auto w-full max-w-3xl px-4";

export interface Crumb {
  label: string;
  href?: string;
}

/** The chat page's header bar, with a breadcrumb in place of the title. */
export function PageHeader({
  crumbs,
  children,
}: {
  crumbs: Crumb[];
  /** Actions at the right end. */
  children?: ReactNode;
}) {
  const last = crumbs.length - 1;
  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b px-4">
      <nav
        aria-label="Breadcrumb"
        className="flex min-w-0 flex-1 items-center gap-1 text-sm"
      >
        {crumbs.map((c, i) => (
          <Fragment key={`${i}:${c.label}`}>
            {i > 0 && (
              <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" />
            )}
            {i === last ? (
              <h1 className="truncate font-semibold">{c.label}</h1>
            ) : c.href ? (
              <Link
                href={c.href}
                className="shrink-0 truncate text-muted-foreground hover:text-foreground"
              >
                {c.label}
              </Link>
            ) : (
              <span className="shrink-0 truncate text-muted-foreground">
                {c.label}
              </span>
            )}
          </Fragment>
        ))}
      </nav>
      {children && (
        <div className="flex shrink-0 items-center gap-1.5">{children}</div>
      )}
    </header>
  );
}

export function CenteredLoader({ label }: { label: string }) {
  return (
    <div className="flex flex-1 items-center justify-center">
      <Loader
        aria-label={label}
        className="size-4 animate-spin text-muted-foreground"
      />
    </div>
  );
}

/** A centred note for an empty or failed page, with optional actions below. */
export function EmptyState({
  children,
  tone = "muted",
  className,
}: {
  children: ReactNode;
  tone?: "muted" | "error";
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center gap-3 py-16 text-center text-sm",
        tone === "error" ? "text-destructive" : "text-muted-foreground",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** "Indexing 3/12" while embeddings are pending, otherwise the chunk count. */
export function StatusBadge({
  doc,
  className,
}: {
  doc: Pick<DocumentMeta, "status" | "chunk_count" | "chunks_pending">;
  className?: string;
}) {
  if (doc.status === "ready") {
    return (
      <span
        className={cn("text-xs text-muted-foreground tabular-nums", className)}
      >
        {doc.chunk_count === 1 ? "1 chunk" : `${doc.chunk_count} chunks`}
      </span>
    );
  }
  const done = doc.chunk_count - doc.chunks_pending;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={cn(
            "inline-flex items-center gap-1 text-xs text-muted-foreground tabular-nums",
            className,
          )}
        >
          <Loader2 className="size-3 animate-spin" />
          Indexing {done}/{doc.chunk_count}
        </span>
      </TooltipTrigger>
      <TooltipContent>
        Keyword search finds it already; semantic search will once every chunk
        is embedded.
      </TooltipContent>
    </Tooltip>
  );
}

const relative = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 24 * 3600],
  ["month", 30 * 24 * 3600],
  ["week", 7 * 24 * 3600],
  ["day", 24 * 3600],
  ["hour", 3600],
  ["minute", 60],
];

/** "3 minutes ago", "yesterday"; under a minute is "just now". */
export function timeAgo(iso: string) {
  const seconds = (Date.parse(iso) - Date.now()) / 1000;
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size)
      return relative.format(Math.round(seconds / size), unit);
  }
  return "just now";
}

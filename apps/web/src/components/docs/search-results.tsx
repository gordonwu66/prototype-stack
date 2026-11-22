"use client";

import Link from "next/link";
import { Fragment, type ReactNode } from "react";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { BREADCRUMB, type Hit, type SearchMode } from "@/lib/search";
import { cn } from "@/lib/utils";
import { useDocs } from "./docs-provider";
import { EmptyState } from "./shared";
import { MODES, useSearchResults } from "./use-search";

const modeLabel = (mode: SearchMode) =>
  MODES.find((m) => m.value === mode)?.label ?? mode;

export function SearchResults({
  q,
  mode,
  collectionId,
}: {
  q: string;
  mode: SearchMode;
  /** Limits the search to one collection; omitted searches them all. */
  collectionId?: string;
}) {
  const { collections } = useDocs();
  const { response, error, loading } = useSearchResults(q, mode, collectionId);
  const pattern = queryPattern(q);

  if (error) return <EmptyState tone="error">{error}</EmptyState>;
  if (!response) return <EmptyState>Searching…</EmptyState>;

  const { results, timings_ms } = response;
  const total = Object.values(timings_ms).reduce((a, b) => a + b, 0);
  const names = new Map(collections.map((c) => [c.id, c.name]));

  return (
    <div
      aria-busy={loading}
      className={cn("transition-opacity", loading && "opacity-50")}
    >
      <p className="mb-3 text-xs text-muted-foreground">
        {loading
          ? "Searching…"
          : `${results.length === 1 ? "1 result" : `${results.length} results`} · ${modeLabel(response.mode)} · ${Math.round(total)} ms`}
      </p>
      {!loading && response.mode !== mode && (
        <p className="mb-3 rounded-lg border border-dashed px-3 py-2 text-xs text-muted-foreground">
          Semantic search is unavailable (no embedding provider, or it failed),
          so these are keyword matches only.
        </p>
      )}
      {results.length === 0 ? (
        <EmptyState>No matches for “{q}”.</EmptyState>
      ) : (
        <ol className="flex flex-col gap-2">
          {results.map((hit) => (
            <li key={hit.chunk_id}>
              <HitCard
                hit={hit}
                // Only a keyword match has terms to mark; a semantic-only hit
                // shares none with the query, by definition of the BM25 leg.
                pattern={hit.lexical_rank !== null ? pattern : null}
                collection={
                  collectionId ? undefined : names.get(hit.collection_id)
                }
              />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function HitCard({
  hit,
  pattern,
  collection,
}: {
  hit: Hit;
  pattern: RegExp | null;
  collection?: string;
}) {
  const [, ...sections] = hit.heading.split(BREADCRUMB);
  const section = sections.at(-1);
  const href = `/docs/${hit.collection_id}/${hit.document_id}${section ? `?section=${encodeURIComponent(section)}` : ""}`;

  return (
    <Link
      href={href}
      className="block rounded-xl border bg-card px-4 py-3 shadow-xs transition-colors hover:bg-muted/50"
    >
      <div className="flex items-start justify-between gap-3">
        <p className="min-w-0 text-sm">
          <span className="font-medium">{hit.title}</span>
          {sections.map((s, i) => (
            <Fragment key={`${i}:${s}`}>
              <span className="text-muted-foreground">{BREADCRUMB}</span>
              <span className="text-muted-foreground">{s}</span>
            </Fragment>
          ))}
        </p>
        <div className="flex shrink-0 gap-1">
          <RankBadge
            rank={hit.lexical_rank}
            label="Keyword"
            explain="BM25: shares terms with the query"
          />
          <RankBadge
            rank={hit.semantic_rank}
            label="Semantic"
            explain="Vectors: close in meaning to the query"
          />
        </div>
      </div>
      <p className="mt-1.5 line-clamp-3 text-sm text-muted-foreground">
        {highlight(snippet(hit.content, pattern), pattern)}
      </p>
      <p className="mt-2 text-xs text-muted-foreground tabular-nums">
        {collection && `${collection} · `}RRF {hit.score.toFixed(4)}
      </p>
    </Link>
  );
}

/** Which leg found the hit, and where it ranked there. Absent if it missed. */
function RankBadge({
  rank,
  label,
  explain,
}: {
  rank: number | null;
  label: string;
  explain: string;
}) {
  if (rank === null) return null;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="rounded-md border px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground tabular-nums">
          {label} #{rank}
        </span>
      </TooltipTrigger>
      <TooltipContent>
        {explain}; ranked #{rank} in that list
      </TooltipContent>
    </Tooltip>
  );
}

// --- client-side term highlighting (the API returns no snippets in v1)

const STOPWORDS = new Set(
  "the and for are but not you all any can had her was one our out has his how its may who did get got him let she too use what when where which why with from that this have will your into than then them they were been does about there their".split(
    " ",
  ),
);

/** Crude English stemming, enough to mark "snapshot" for "snapshots". */
function stem(word: string) {
  const s = word.replace(/(?:ing|ed|es|s)$/, "");
  return s.length >= 3 ? s : word;
}

/** Matches words starting with a query term's stem; null if no term is left. */
function queryPattern(q: string): RegExp | null {
  const words = q.toLowerCase().match(/[a-z0-9]+/g) ?? [];
  const stems = new Set(
    words.filter((w) => w.length >= 3 && !STOPWORDS.has(w)).map(stem),
  );
  // Stems are [a-z0-9] only, so they need no escaping.
  return stems.size
    ? new RegExp(`\\b(?:${[...stems].join("|")})[a-z0-9]*`, "gi")
    : null;
}

const SNIPPET_CHARS = 360;

/** Flattens markdown to one line, starting near the first match so it's visible. */
function snippet(text: string, pattern: RegExp | null) {
  const flat = text
    .replace(/(^|\n)\s*(?:#{1,6}|[-*+]|\d+\.)\s+/g, "$1")
    .replace(/\*\*|__|`/g, "")
    .replace(/\s+/g, " ")
    .trim();
  let start = 0;
  if (pattern) {
    pattern.lastIndex = 0;
    const first = pattern.exec(flat);
    if (first && first.index > 120)
      start = flat.lastIndexOf(" ", first.index - 60) + 1;
  }
  const end = start + SNIPPET_CHARS;
  return `${start > 0 ? "…" : ""}${flat.slice(start, end)}${end < flat.length ? "…" : ""}`;
}

function highlight(text: string, pattern: RegExp | null): ReactNode {
  if (!pattern) return text;
  const out: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(pattern)) {
    out.push(text.slice(last, m.index));
    out.push(
      <mark
        key={m.index}
        className="rounded-sm bg-amber-200/70 px-0.5 text-foreground dark:bg-amber-400/25"
      >
        {m[0]}
      </mark>,
    );
    last = m.index + m[0].length;
  }
  out.push(text.slice(last));
  return out;
}

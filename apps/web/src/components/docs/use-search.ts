"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { errorMessage } from "@/lib/api";
import { type SearchMode, type SearchResponse, search } from "@/lib/search";

export const MODES: { value: SearchMode; label: string }[] = [
  { value: "hybrid", label: "Hybrid" },
  { value: "lexical", label: "Keyword" },
  { value: "semantic", label: "Semantic" },
];

const isMode = (value: string | null): value is SearchMode =>
  MODES.some((m) => m.value === value);

/**
 * The query lives in the URL (`?q=…&mode=…`), so results survive a reload, can
 * be linked, and Back returns to them. Callers need a Suspense boundary.
 */
export function useSearchQuery() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const q = params.get("q")?.trim() ?? "";
  const rawMode = params.get("mode");
  const mode: SearchMode = isMode(rawMode) ? rawMode : "hybrid";

  const setQuery = useCallback(
    (next: { q: string; mode: SearchMode }) => {
      const sp = new URLSearchParams();
      if (next.q) sp.set("q", next.q);
      if (next.mode !== "hybrid") sp.set("mode", next.mode);
      const qs = sp.toString();
      router.push(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [router, pathname],
  );

  return { q, mode, setQuery };
}

type Result =
  | { key: string; response: SearchResponse; error?: undefined }
  | { key: string; error: string; response?: undefined };

/**
 * Runs `POST /search` whenever the query changes. While a new query runs, the
 * previous results stay up (`stale`) so the list doesn't flash empty.
 */
export function useSearchResults(
  q: string,
  mode: SearchMode,
  collectionId?: string,
) {
  const key = JSON.stringify([q, mode, collectionId ?? null]);
  const [result, setResult] = useState<Result | null>(null);

  useEffect(() => {
    if (!q) return;
    const controller = new AbortController();
    search(
      {
        query: q,
        mode,
        collection_ids: collectionId ? [collectionId] : undefined,
        limit: 20,
      },
      controller.signal,
    ).then(
      (response) => setResult({ key, response }),
      (err) => {
        if (!controller.signal.aborted)
          setResult({ key, error: errorMessage(err, "Search failed") });
      },
    );
    return () => controller.abort();
  }, [key, q, mode, collectionId]);

  return {
    response: result?.response,
    error: result?.key === key ? result.error : undefined,
    loading: !!q && result?.key !== key,
  };
}

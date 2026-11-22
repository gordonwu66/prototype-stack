"use client";

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { errorMessage } from "@/lib/api";
import {
  type Collection,
  createCollection as createCollectionRequest,
  type DocumentMeta,
  listCollections,
  listDocuments,
} from "@/lib/search";

/** How often to re-read the lists while any document is still embedding. */
const POLL_MS = 1500;

interface DocsContextValue {
  collections: Collection[];
  /** Newest first, keyed by collection id. */
  documents: Record<string, DocumentMeta[]>;
  /** The first load has finished, successfully or not. */
  loaded: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  /** Throws with the server's message, e.g. on a duplicate name. */
  createCollection: (name: string) => Promise<Collection>;
}

const DocsContext = createContext<DocsContextValue | null>(null);

/**
 * Every collection and its documents, for the sidebar tree and the listings.
 * Nothing pushes document changes to the browser, so pages call `refresh()`
 * after they change something, and the lists poll while anything is indexing.
 */
export function DocsProvider({ children }: { children: ReactNode }) {
  const [collections, setCollections] = useState<Collection[]>([]);
  const [documents, setDocuments] = useState<Record<string, DocumentMeta[]>>(
    {},
  );
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Only the latest refresh may write, so a slow response can't undo a newer one.
  const latest = useRef(0);

  const refresh = useCallback(async () => {
    const run = ++latest.current;
    try {
      const list = await listCollections();
      const docs = await Promise.all(list.map((c) => listDocuments(c.id)));
      if (run !== latest.current) return;
      setCollections(list);
      setDocuments(Object.fromEntries(list.map((c, i) => [c.id, docs[i]])));
      setError(null);
    } catch (err) {
      if (run !== latest.current) return;
      setError(errorMessage(err, "Can't reach the server"));
    } finally {
      if (run === latest.current) setLoaded(true);
    }
  }, []);

  // Load on mount, and again when the tab regains focus to pick up other tabs' edits.
  useEffect(() => {
    refresh();
    const onFocus = () => refresh();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refresh]);

  const indexing = Object.values(documents).some((list) =>
    list.some((d) => d.status === "indexing"),
  );

  // Overlapping refreshes are fine: only the latest one writes.
  useEffect(() => {
    if (!indexing) return;
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [indexing, refresh]);

  const createCollection = useCallback(
    async (name: string) => {
      const collection = await createCollectionRequest(name);
      await refresh();
      return collection;
    },
    [refresh],
  );

  const value = useMemo(
    () => ({
      collections,
      documents,
      loaded,
      error,
      refresh,
      createCollection,
    }),
    [collections, documents, loaded, error, refresh, createCollection],
  );

  return <DocsContext value={value}>{children}</DocsContext>;
}

export function useDocs() {
  const value = useContext(DocsContext);
  if (!value) throw new Error("useDocs needs a <DocsProvider>");
  return value;
}

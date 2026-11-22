"use client";

import { Loader2, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { useStoredState } from "@/components/chat/use-chat";
import {
  confirmDeleteCollection,
  confirmDeleteDocument,
} from "@/components/docs/actions";
import { useDocs } from "@/components/docs/docs-provider";
import { errorMessage } from "@/lib/api";
import type { Collection, DocumentMeta } from "@/lib/search";
import { cn } from "@/lib/utils";
import {
  Branch,
  EmptyRow,
  InlineInput,
  LoadingRow,
  RowAction,
  RowActions,
  rowClass,
  rowLabel,
  SectionHeader,
  Toggle,
} from "./rows";

/** `/docs/{collectionId}[/{documentId}]` → its ids; "new" is not a document. */
function parseDocsPath(pathname: string) {
  const [, root, collectionId, documentId] = pathname.split("/");
  if (root !== "docs") return { collectionId: null, documentId: null };
  return {
    collectionId: collectionId || null,
    documentId: documentId && documentId !== "new" ? documentId : null,
  };
}

export function DocumentsSection({ pathname }: { pathname: string }) {
  const router = useRouter();
  const { collections, documents, loaded, error, createCollection } = useDocs();
  const [state, setState] = useStoredState<"open" | "closed">(
    "sidebar:documents",
    "open",
  );
  const open = state === "open";
  const [creating, setCreating] = useState(false);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const active = parseDocsPath(pathname);

  // Opening a collection's page expands it here; collapsing it again sticks
  // until the next time it's opened.
  const [revealed, setRevealed] = useState<string | null>(null);
  if (active.collectionId !== revealed) {
    setRevealed(active.collectionId);
    if (active.collectionId && !expanded.has(active.collectionId))
      setExpanded(new Set(expanded).add(active.collectionId));
  }

  function toggleCollection(id: string) {
    const next = new Set(expanded);
    if (!next.delete(id)) next.add(id);
    setExpanded(next);
  }

  async function create(name: string | null) {
    setCreating(false);
    if (!name) return;
    try {
      const collection = await createCollection(name);
      router.push(`/docs/${collection.id}`);
    } catch (err) {
      toast.error(errorMessage(err, "Could not create the collection"));
    }
  }

  return (
    <section aria-label="Documents">
      <SectionHeader
        label="Documents"
        href="/docs"
        active={pathname === "/docs"}
        open={open}
        onToggle={() => setState(open ? "closed" : "open")}
        actions={
          <RowAction
            label="New collection"
            onClick={() => {
              setState("open");
              setCreating(true);
            }}
            className="text-current"
          >
            <Plus />
          </RowAction>
        }
      />
      {open && (
        <div className="flex flex-col gap-0.5">
          {creating && (
            <InlineInput
              label="Collection name"
              placeholder="Collection name"
              onDone={create}
            />
          )}
          {error && <p className="px-2 text-xs text-destructive">{error}</p>}
          {!loaded && <LoadingRow label="Loading collections" />}
          {loaded && !error && collections.length === 0 && !creating && (
            <EmptyRow>No collections yet</EmptyRow>
          )}
          {collections.map((c) => (
            <CollectionItem
              key={c.id}
              collection={c}
              documents={documents[c.id] ?? []}
              open={expanded.has(c.id)}
              onToggle={() => toggleCollection(c.id)}
              active={active}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function CollectionItem({
  collection,
  documents,
  open,
  onToggle,
  active,
}: {
  collection: Collection;
  documents: DocumentMeta[];
  open: boolean;
  onToggle: () => void;
  active: ReturnType<typeof parseDocsPath>;
}) {
  const router = useRouter();
  const { refresh } = useDocs();
  const isActive = active.collectionId === collection.id && !active.documentId;

  async function remove() {
    const viewing = active.collectionId === collection.id;
    if ((await confirmDeleteCollection(collection, refresh)) && viewing)
      router.replace("/docs");
  }

  return (
    <div>
      <div className={rowClass(isActive)}>
        <Toggle open={open} label={collection.name} onClick={onToggle} />
        <Link
          href={`/docs/${collection.id}`}
          className={`${rowLabel} pl-0.5`}
          title={collection.name}
        >
          {collection.name}
        </Link>
        <span className="pr-2 text-xs text-muted-foreground tabular-nums group-focus-within:hidden group-hover:hidden">
          {documents.length}
        </span>
        <RowActions>
          <RowAction
            label="Delete collection"
            onClick={remove}
            className="hover:text-destructive"
          >
            <Trash2 />
          </RowAction>
        </RowActions>
      </div>
      {open && (
        <Branch>
          {documents.length === 0 && <EmptyRow>No documents</EmptyRow>}
          {documents.map((d) => (
            <DocumentItem
              key={d.id}
              doc={d}
              active={active.documentId === d.id}
            />
          ))}
        </Branch>
      )}
    </div>
  );
}

function DocumentItem({ doc, active }: { doc: DocumentMeta; active: boolean }) {
  const router = useRouter();
  const { refresh } = useDocs();

  async function remove() {
    if ((await confirmDeleteDocument(doc, refresh)) && active)
      router.replace(`/docs/${doc.collection_id}`);
  }

  return (
    <div className={rowClass(active)}>
      <Link
        href={`/docs/${doc.collection_id}/${doc.id}`}
        className={cn(rowLabel, "flex items-center gap-1.5")}
        title={doc.title}
      >
        <span className="truncate">{doc.title}</span>
        {doc.status === "indexing" && (
          <Loader2
            aria-label="Indexing"
            className="size-3 shrink-0 animate-spin text-muted-foreground"
          />
        )}
      </Link>
      <RowActions>
        <RowAction
          label="Delete"
          onClick={remove}
          className="hover:text-destructive"
        >
          <Trash2 />
        </RowAction>
      </RowActions>
    </div>
  );
}

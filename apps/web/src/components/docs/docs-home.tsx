"use client";

import { FolderPlus, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { errorMessage } from "@/lib/api";
import type { Collection, DocumentMeta } from "@/lib/search";
import { cn } from "@/lib/utils";
import { useDocs } from "./docs-provider";
import { DocumentRows } from "./document-list";
import { SearchBar } from "./search-bar";
import { SearchResults } from "./search-results";
import { column, EmptyState, PageHeader } from "./shared";
import { UploadButton } from "./upload";
import { useSearchQuery } from "./use-search";

/** `/docs`: search across every collection, or every collection's documents. */
export function DocsHome() {
  const { q, mode } = useSearchQuery();
  const { collections, documents, loaded, error } = useDocs();
  const [creating, setCreating] = useState(false);

  let listing: React.ReactNode;
  if (!loaded) listing = <EmptyState>Loading…</EmptyState>;
  else if (error) listing = <EmptyState tone="error">{error}</EmptyState>;
  else if (collections.length === 0 && !creating)
    listing = (
      <EmptyState>
        <p>
          No collections yet. A collection groups the documents you upload or
          write.
        </p>
        <Button size="sm" onClick={() => setCreating(true)}>
          <FolderPlus />
          New collection
        </Button>
      </EmptyState>
    );
  else
    listing = (
      <div className="flex flex-col gap-8">
        {creating && <NewCollectionForm onDone={() => setCreating(false)} />}
        {collections.map((c) => (
          <CollectionGroup
            key={c.id}
            collection={c}
            documents={documents[c.id] ?? []}
          />
        ))}
      </div>
    );

  return (
    <div className="flex h-full w-full flex-col">
      <PageHeader crumbs={[{ label: "Documents" }]}>
        <Button size="sm" variant="outline" onClick={() => setCreating(true)}>
          <FolderPlus />
          New collection
        </Button>
      </PageHeader>
      <div className={cn(column, "pt-4 pb-3")}>
        <SearchBar />
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <div className={cn(column, "pt-2 pb-10")}>
          {q ? <SearchResults q={q} mode={mode} /> : listing}
        </div>
      </ScrollArea>
    </div>
  );
}

function CollectionGroup({
  collection,
  documents,
}: {
  collection: Collection;
  documents: DocumentMeta[];
}) {
  return (
    <section aria-label={collection.name}>
      <div className="mb-2 flex items-center gap-2">
        <Link
          href={`/docs/${collection.id}`}
          className="truncate text-sm font-semibold hover:underline"
        >
          {collection.name}
        </Link>
        <span className="text-xs text-muted-foreground tabular-nums">
          {documents.length}
        </span>
        <div className="ml-auto flex items-center gap-1">
          <UploadButton
            collectionId={collection.id}
            size="xs"
            variant="ghost"
          />
          <Button asChild size="xs" variant="ghost">
            <Link href={`/docs/${collection.id}/new`}>
              <Plus />
              New
            </Link>
          </Button>
        </div>
      </div>
      <DocumentRows
        documents={documents}
        empty="No documents yet. Upload .md or .txt files, or write one."
      />
    </section>
  );
}

function NewCollectionForm({ onDone }: { onDone: () => void }) {
  const router = useRouter();
  const { createCollection } = useDocs();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    const trimmed = name.trim();
    if (!trimmed) return;
    setBusy(true);
    try {
      const collection = await createCollection(trimmed);
      onDone();
      router.push(`/docs/${collection.id}`);
    } catch (err) {
      toast.error(errorMessage(err, "Could not create the collection"));
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      className="flex items-center gap-2 rounded-xl border bg-card p-2 shadow-xs"
    >
      <Input
        aria-label="Collection name"
        placeholder="Collection name"
        autoFocus
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") onDone();
        }}
        className="border-0 shadow-none focus-visible:ring-0 dark:bg-transparent"
      />
      <Button type="button" size="sm" variant="ghost" onClick={onDone}>
        Cancel
      </Button>
      <Button type="submit" size="sm" disabled={!name.trim() || busy}>
        Create
      </Button>
    </form>
  );
}

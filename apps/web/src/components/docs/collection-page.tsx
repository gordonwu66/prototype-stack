"use client";

import { Plus, Trash2, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { confirmDeleteCollection } from "./actions";
import { useDocs } from "./docs-provider";
import { DocumentRows } from "./document-list";
import { SearchBar } from "./search-bar";
import { SearchResults } from "./search-results";
import { CenteredLoader, column, EmptyState, PageHeader } from "./shared";
import { UploadButton, useDropZone } from "./upload";
import { useSearchQuery } from "./use-search";

/** `/docs/{id}`: one collection's documents, a search limited to them, and a drop zone. */
export function CollectionPage({ collectionId }: { collectionId: string }) {
  const router = useRouter();
  const { q, mode } = useSearchQuery();
  const { collections, documents, loaded, error, refresh } = useDocs();
  const drop = useDropZone(collectionId);
  const collection = collections.find((c) => c.id === collectionId);

  if (!collection) {
    return (
      <div className="flex h-full w-full flex-col">
        <PageHeader
          crumbs={[{ label: "Documents", href: "/docs" }, { label: "" }]}
        />
        {loaded ? (
          <EmptyState tone={error ? "error" : "muted"}>
            {error ?? "Collection not found."}
          </EmptyState>
        ) : (
          <CenteredLoader label="Loading collection" />
        )}
      </div>
    );
  }

  return (
    <div {...drop.props} className="relative flex h-full w-full flex-col">
      <PageHeader
        crumbs={[
          { label: "Documents", href: "/docs" },
          { label: collection.name },
        ]}
      >
        <UploadButton collectionId={collectionId} />
        <Button asChild size="sm">
          <Link href={`/docs/${collectionId}/new`}>
            <Plus />
            New document
          </Link>
        </Button>
        <Button
          size="icon-sm"
          variant="ghost"
          aria-label="Delete collection"
          className="text-muted-foreground hover:text-destructive"
          onClick={async () => {
            if (await confirmDeleteCollection(collection, refresh))
              router.replace("/docs");
          }}
        >
          <Trash2 />
        </Button>
      </PageHeader>
      <div className={cn(column, "pt-4 pb-3")}>
        <SearchBar scope={collection.name} />
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <div className={cn(column, "pt-2 pb-10")}>
          {q ? (
            <SearchResults q={q} mode={mode} collectionId={collectionId} />
          ) : (
            <DocumentRows
              documents={documents[collectionId] ?? []}
              empty="No documents yet. Drop .md or .txt files here, upload them, or write one."
            />
          )}
        </div>
      </ScrollArea>
      {drop.over && (
        <div className="pointer-events-none absolute inset-2 flex items-center justify-center rounded-xl border-2 border-dashed border-ring bg-background/80 text-sm font-medium">
          <Upload className="mr-2 size-4" />
          Drop .md or .txt files to add them to {collection.name}
        </div>
      )}
    </div>
  );
}

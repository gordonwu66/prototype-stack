"use client";

import { Pencil, Trash2 } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Markdown } from "@/components/chat/markdown";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ApiError, errorMessage } from "@/lib/api";
import {
  createDocument,
  type Document,
  getDocument,
  updateDocument,
} from "@/lib/search";
import { cn } from "@/lib/utils";
import { confirmDeleteDocument } from "./actions";
import { useDocs } from "./docs-provider";
import { DocumentEditor, type Draft } from "./document-editor";
import {
  CenteredLoader,
  type Crumb,
  column,
  EmptyState,
  PageHeader,
  StatusBadge,
  timeAgo,
} from "./shared";

const SOURCE_LABELS: Record<string, string> = {
  upload: "Uploaded",
  note: "Written here",
  url: "From a URL",
};

/** `/docs/{collectionId}/{documentId}`: the rendered document, or its editor. */
export function DocumentPage({
  collectionId,
  documentId,
}: {
  collectionId: string;
  documentId: string;
}) {
  const router = useRouter();
  // Set by a search result: the heading of the section that matched.
  const section = useSearchParams().get("section");
  const { collections, documents, refresh } = useDocs();
  const [doc, setDoc] = useState<Document | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const bodyRef = useRef<HTMLElement>(null);

  // Content is fetched once; status comes from the provider's polled list.
  useEffect(() => {
    const controller = new AbortController();
    getDocument(documentId, { signal: controller.signal }).then(
      (d) => {
        setDoc(d);
        setError(null);
      },
      (err) => {
        if (controller.signal.aborted) return;
        setError(
          err instanceof ApiError && err.status === 404
            ? "Document not found."
            : errorMessage(err, "Could not load the document"),
        );
      },
    );
    return () => controller.abort();
  }, [documentId]);

  useScrollToSection(bodyRef, section, !!doc && !editing);

  const collection = collections.find((c) => c.id === collectionId);
  const live = documents[collectionId]?.find((d) => d.id === documentId);
  const meta = live ?? doc;
  const crumbs: Crumb[] = [
    { label: "Documents", href: "/docs" },
    { label: collection?.name ?? "…", href: `/docs/${collectionId}` },
    { label: meta?.title ?? "" },
  ];

  if (!doc) {
    return (
      <div className="flex h-full w-full flex-col">
        <PageHeader crumbs={crumbs} />
        {error ? (
          <EmptyState tone="error">{error}</EmptyState>
        ) : (
          <CenteredLoader label="Loading document" />
        )}
      </div>
    );
  }

  if (editing) {
    return (
      <DocumentEditor
        // Remount on save so the next edit starts from the saved text.
        key={doc.updated_at}
        crumbs={[...crumbs.slice(0, -1), { label: `Editing ${doc.title}` }]}
        initial={doc}
        onCancel={() => setEditing(false)}
        onSave={async (draft) => {
          try {
            // Send only what changed: an unchanged body skips re-chunking.
            const updated = await updateDocument(documentId, {
              title: draft.title !== doc.title ? draft.title : undefined,
              content:
                draft.content !== doc.content ? draft.content : undefined,
            });
            setDoc({ ...updated, content: draft.content });
            setEditing(false);
            await refresh();
          } catch (err) {
            toast.error(errorMessage(err, "Could not save the document"));
          }
        }}
      />
    );
  }

  return (
    <div className="flex h-full w-full flex-col">
      <PageHeader crumbs={crumbs}>
        {meta && <StatusBadge doc={meta} className="mr-1.5" />}
        <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
          <Pencil />
          Edit
        </Button>
        <Button
          size="icon-sm"
          variant="ghost"
          aria-label="Delete document"
          className="text-muted-foreground hover:text-destructive"
          onClick={async () => {
            if (await confirmDeleteDocument(doc, refresh))
              router.replace(`/docs/${collectionId}`);
          }}
        >
          <Trash2 />
        </Button>
      </PageHeader>
      <ScrollArea className="min-h-0 flex-1">
        <article ref={bodyRef} className={cn(column, "py-8")}>
          <h2 className="text-2xl font-semibold">{meta?.title}</h2>
          <p className="mt-1 mb-6 text-xs text-muted-foreground">
            {SOURCE_LABELS[doc.source] ?? doc.source} · Updated{" "}
            {timeAgo(meta?.updated_at ?? doc.updated_at)}
          </p>
          {doc.content.trim() ? (
            <Markdown streaming={false}>{doc.content}</Markdown>
          ) : (
            <p className="text-sm text-muted-foreground">
              This document is empty.
            </p>
          )}
        </article>
      </ScrollArea>
    </div>
  );
}

/** `/docs/{collectionId}/new`: an empty editor; saving opens the new document. */
export function NewDocumentPage({ collectionId }: { collectionId: string }) {
  const router = useRouter();
  const { collections, refresh } = useDocs();
  // Next keeps this page's state when navigating away, so bump the key after a
  // save; otherwise the next "New document" would open with the old draft.
  const [form, setForm] = useState(0);
  const collection = collections.find((c) => c.id === collectionId);

  async function save(draft: Draft) {
    try {
      const doc = await createDocument(collectionId, draft);
      await refresh();
      setForm((n) => n + 1);
      router.replace(`/docs/${collectionId}/${doc.id}`);
    } catch (err) {
      toast.error(errorMessage(err, "Could not create the document"));
    }
  }

  return (
    <DocumentEditor
      key={form}
      crumbs={[
        { label: "Documents", href: "/docs" },
        { label: collection?.name ?? "…", href: `/docs/${collectionId}` },
        { label: "New document" },
      ]}
      initial={{ title: "", content: "" }}
      onSave={save}
      onCancel={() => {
        setForm((n) => n + 1);
        router.push(`/docs/${collectionId}`);
      }}
    />
  );
}

const normalize = (s: string) =>
  s.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "");

/**
 * Scrolls the rendered heading whose text matches `section` into view and
 * flashes it. Markdown renders after the content arrives, so retry briefly.
 */
function useScrollToSection(
  ref: React.RefObject<HTMLElement | null>,
  section: string | null,
  ready: boolean,
) {
  useEffect(() => {
    if (!section || !ready) return;
    const target = normalize(section);
    const flash = ["bg-amber-200/60", "dark:bg-amber-400/20"];
    let tries = 0;
    let timer: ReturnType<typeof setTimeout>;
    let found: Element | undefined;

    const find = () => {
      const headings = ref.current?.querySelectorAll("h1,h2,h3,h4,h5,h6");
      found = [...(headings ?? [])].find(
        (h) => normalize(h.textContent ?? "") === target,
      );
      if (found) {
        found.scrollIntoView({ block: "start" });
        found.classList.add(
          "rounded-md",
          "transition-colors",
          "duration-700",
          ...flash,
        );
        timer = setTimeout(() => found?.classList.remove(...flash), 1200);
      } else if (tries++ < 20) {
        timer = setTimeout(find, 50);
      }
    };
    find();
    return () => clearTimeout(timer);
  }, [ref, section, ready]);
}

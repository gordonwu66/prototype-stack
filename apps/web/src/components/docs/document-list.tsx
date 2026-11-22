"use client";

import { FileText, Trash2 } from "lucide-react";
import Link from "next/link";
import { RowAction } from "@/components/sidebar/rows";
import type { DocumentMeta } from "@/lib/search";
import { confirmDeleteDocument } from "./actions";
import { useDocs } from "./docs-provider";
import { StatusBadge, timeAgo } from "./shared";

/** A collection's documents, newest first, as rows in one bordered card. */
export function DocumentRows({
  documents,
  empty,
}: {
  documents: DocumentMeta[];
  /** Shown in place of the card when there are no documents. */
  empty: React.ReactNode;
}) {
  const { refresh } = useDocs();

  if (documents.length === 0) {
    return (
      <div className="rounded-xl border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
        {empty}
      </div>
    );
  }

  return (
    <ul className="divide-y overflow-hidden rounded-xl border bg-card shadow-xs">
      {documents.map((d) => (
        <li
          key={d.id}
          className="group flex items-center transition-colors hover:bg-muted/50"
        >
          <Link
            href={`/docs/${d.collection_id}/${d.id}`}
            className="flex min-w-0 flex-1 items-center gap-3 py-2.5 pl-4"
          >
            <FileText className="size-4 shrink-0 text-muted-foreground" />
            <span className="min-w-0 flex-1 truncate text-sm font-medium">
              {d.title}
            </span>
            <StatusBadge doc={d} />
            <span
              className="w-24 shrink-0 text-right text-xs text-muted-foreground"
              title={new Date(d.updated_at).toLocaleString()}
            >
              {timeAgo(d.updated_at)}
            </span>
          </Link>
          {/* Hidden until hover, but keeps its width so the row doesn't shift. */}
          <div className="px-2 opacity-0 group-focus-within:opacity-100 group-hover:opacity-100">
            <RowAction
              label="Delete"
              onClick={() => confirmDeleteDocument(d, refresh)}
              className="hover:text-destructive"
            >
              <Trash2 />
            </RowAction>
          </div>
        </li>
      ))}
    </ul>
  );
}

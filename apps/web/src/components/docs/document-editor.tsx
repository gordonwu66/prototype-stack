"use client";

import { Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { type Crumb, column, PageHeader } from "./shared";

export interface Draft {
  title: string;
  content: string;
}

/**
 * Title plus Markdown source, for new and existing documents. Save is in the
 * header; ⌘/Ctrl+Enter saves too. `onSave` reports its own errors.
 */
export function DocumentEditor({
  crumbs,
  initial,
  onSave,
  onCancel,
}: {
  crumbs: Crumb[];
  initial: Draft;
  onSave: (draft: Draft) => Promise<void>;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState(initial.title);
  const [content, setContent] = useState(initial.content);
  const [saving, setSaving] = useState(false);
  const titleRef = useRef<HTMLInputElement>(null);
  const dirty = title !== initial.title || content !== initial.content;
  const canSave = !!title.trim() && dirty && !saving;

  // Only a new document starts in the title; an edit starts where you read.
  const isNew = !initial.title;
  useEffect(() => {
    if (isNew) titleRef.current?.focus();
  }, [isNew]);

  async function save() {
    if (!canSave) return;
    setSaving(true);
    try {
      await onSave({ title: title.trim(), content });
    } finally {
      setSaving(false);
    }
  }

  function cancel() {
    if (!dirty || confirm("Discard your changes?")) onCancel();
  }

  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: catches ⌘Enter from either field
    <div
      className="flex h-full w-full flex-col"
      onKeyDown={(e) => {
        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
          e.preventDefault();
          save();
        }
      }}
    >
      <PageHeader crumbs={crumbs}>
        <Button size="sm" variant="ghost" onClick={cancel}>
          Cancel
        </Button>
        <Button size="sm" onClick={save} disabled={!canSave}>
          {saving && <Loader2 className="animate-spin" />}
          Save
        </Button>
      </PageHeader>
      <ScrollArea className="min-h-0 flex-1">
        <div className={cn(column, "flex flex-col gap-2 py-8")}>
          <input
            aria-label="Title"
            placeholder="Untitled"
            ref={titleRef}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full bg-transparent text-2xl font-semibold outline-none placeholder:text-muted-foreground/60"
          />
          <Textarea
            aria-label="Content"
            placeholder="Write in Markdown. Headings split the document into sections that search can return on their own."
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="min-h-[60vh] resize-none rounded-none border-0 bg-transparent px-0 font-mono text-sm leading-relaxed shadow-none focus-visible:ring-0 dark:bg-transparent"
          />
        </div>
      </ScrollArea>
    </div>
  );
}

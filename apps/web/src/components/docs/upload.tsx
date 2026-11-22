"use client";

import { Loader2, Upload } from "lucide-react";
import { type DragEvent, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { UPLOAD_ACCEPT, uploadFiles } from "./actions";
import { useDocs } from "./docs-provider";

export function UploadButton({
  collectionId,
  size = "sm",
  variant = "outline",
}: {
  collectionId: string;
  size?: "sm" | "xs";
  variant?: "outline" | "ghost";
}) {
  const input = useRef<HTMLInputElement>(null);
  const { refresh } = useDocs();
  const [busy, setBusy] = useState(false);

  return (
    <>
      <input
        ref={input}
        type="file"
        accept={UPLOAD_ACCEPT}
        multiple
        hidden
        onChange={async (e) => {
          const files = [...(e.currentTarget.files ?? [])];
          // Reset so picking the same file again still fires a change.
          e.currentTarget.value = "";
          setBusy(true);
          await uploadFiles(collectionId, files, refresh);
          setBusy(false);
        }}
      />
      <Button
        size={size}
        variant={variant}
        disabled={busy}
        onClick={() => input.current?.click()}
      >
        {busy ? <Loader2 className="animate-spin" /> : <Upload />}
        Upload
      </Button>
    </>
  );
}

const hasFiles = (e: DragEvent) => e.dataTransfer.types.includes("Files");

/** Spread `props` on the element that takes dropped .md/.txt files. */
export function useDropZone(collectionId: string) {
  const { refresh } = useDocs();
  const [over, setOver] = useState(false);
  // dragenter/dragleave fire for every child crossed, so count the nesting.
  const depth = useRef(0);

  const props = {
    onDragEnter: (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth.current++;
      setOver(true);
    },
    onDragOver: (e: DragEvent) => {
      if (hasFiles(e)) e.preventDefault();
    },
    onDragLeave: (e: DragEvent) => {
      if (!hasFiles(e)) return;
      depth.current = Math.max(0, depth.current - 1);
      if (depth.current === 0) setOver(false);
    },
    onDrop: (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth.current = 0;
      setOver(false);
      uploadFiles(collectionId, [...e.dataTransfer.files], refresh);
    },
  };

  return { over, props };
}

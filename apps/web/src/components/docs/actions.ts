"use client";

import { toast } from "sonner";
import { errorMessage } from "@/lib/api";
import {
  type Collection,
  type DocumentMeta,
  deleteCollection,
  deleteDocument,
  uploadDocument,
} from "@/lib/search";

/** Files the upload route accepts; others are rejected before sending. */
export const UPLOAD_ACCEPT = ".md,.markdown,.txt";
const UPLOAD_EXTENSIONS = UPLOAD_ACCEPT.split(",");

/** Asks first. Resolves true once the document is gone. */
export async function confirmDeleteDocument(
  doc: Pick<DocumentMeta, "id" | "title">,
  refresh: () => Promise<void>,
) {
  if (!confirm(`Delete "${doc.title}"?`)) return false;
  try {
    await deleteDocument(doc.id);
  } catch (err) {
    toast.error(errorMessage(err, "Could not delete the document"));
    return false;
  }
  await refresh();
  return true;
}

/** Asks first. Resolves true once the collection and its documents are gone. */
export async function confirmDeleteCollection(
  collection: Collection,
  refresh: () => Promise<void>,
) {
  const count = collection.document_count;
  const docs = count === 1 ? "1 document" : `${count} documents`;
  if (!confirm(`Delete "${collection.name}" and its ${docs}?`)) return false;
  try {
    await deleteCollection(collection.id);
  } catch (err) {
    toast.error(errorMessage(err, "Could not delete the collection"));
    return false;
  }
  await refresh();
  return true;
}

/** Uploads one at a time, so a failure names its file. Resolves the count uploaded. */
export async function uploadFiles(
  collectionId: string,
  files: Iterable<File>,
  refresh: () => Promise<void>,
) {
  let uploaded = 0;
  for (const file of files) {
    const name = file.name.toLowerCase();
    if (!UPLOAD_EXTENSIONS.some((ext) => name.endsWith(ext))) {
      toast.error(`${file.name}: only .md and .txt files are supported`);
      continue;
    }
    try {
      await uploadDocument(collectionId, file);
      uploaded++;
    } catch (err) {
      toast.error(`${file.name}: ${errorMessage(err, "upload failed")}`);
    }
  }
  if (uploaded > 0) {
    toast.success(
      uploaded === 1 ? "Uploaded 1 file" : `Uploaded ${uploaded} files`,
    );
    await refresh();
  }
  return uploaded;
}

import { json, request } from "./api";

// Mirrors apps/api/src/api/search/schemas.py and the routes in api/search/routes.py.

export type SearchMode = "hybrid" | "lexical" | "semantic";

export interface Collection {
  id: string;
  name: string;
  created_at: string;
  document_count: number;
}

export interface DocumentMeta {
  id: string;
  collection_id: string;
  title: string;
  source: "upload" | "url" | "note";
  uri: string | null;
  mime_type: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  chunk_count: number;
  /** Chunks still waiting for an embedding; BM25 already finds them. */
  chunks_pending: number;
  status: "indexing" | "ready";
}

export interface Document extends DocumentMeta {
  content: string;
}

export interface Hit {
  chunk_id: number;
  document_id: string;
  collection_id: string;
  ord: number;
  title: string;
  /** Breadcrumb: "Title › Section › Subsection" */
  heading: string;
  content: string;
  /** The RRF score */
  score: number;
  /** 1-based rank in the BM25 leg; null if that leg missed it */
  lexical_rank: number | null;
  semantic_rank: number | null;
}

export interface SearchResponse {
  results: Hit[];
  /** What actually ran: hybrid falls back to lexical without embeddings. */
  mode: SearchMode;
  timings_ms: Record<string, number>;
}

export const BREADCRUMB = " › ";

export const listCollections = () => request<Collection[]>("/collections");

export const createCollection = (name: string) =>
  request<Collection>("/collections", json("POST", { name }));

export const deleteCollection = (id: string) =>
  request<void>(`/collections/${id}`, { method: "DELETE" });

export const listDocuments = (collectionId: string) =>
  request<DocumentMeta[]>(`/collections/${collectionId}/documents`);

export const getDocument = (id: string, init?: RequestInit) =>
  request<Document>(`/documents/${id}?include=content`, init);

export const createDocument = (
  collectionId: string,
  body: { title: string; content: string },
) =>
  request<DocumentMeta>(
    `/collections/${collectionId}/documents`,
    json("POST", body),
  );

export function uploadDocument(collectionId: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  // No Content-Type header: the browser sets the multipart boundary.
  return request<DocumentMeta>(
    `/collections/${collectionId}/documents/upload`,
    {
      method: "POST",
      body: form,
    },
  );
}

export const updateDocument = (
  id: string,
  body: { title?: string; content?: string },
) => request<DocumentMeta>(`/documents/${id}`, json("PUT", body));

export const deleteDocument = (id: string) =>
  request<void>(`/documents/${id}`, { method: "DELETE" });

export const search = (
  body: {
    query: string;
    mode: SearchMode;
    collection_ids?: string[];
    limit?: number;
  },
  signal?: AbortSignal,
) => request<SearchResponse>("/search", { ...json("POST", body), signal });

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** A non-2xx response. `message` is FastAPI's `detail` when it sent one. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, init);
  if (!res.ok) {
    const fallback = `${init?.method ?? "GET"} ${path}: ${res.status}`;
    const body = await res.json().catch(() => null);
    // Validation errors (422) send a list of issues; anything else sends a string.
    const detail = typeof body?.detail === "string" ? body.detail : fallback;
    throw new ApiError(detail, res.status);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const errorMessage = (err: unknown, fallback: string) =>
  err instanceof ApiError ? err.message : fallback;

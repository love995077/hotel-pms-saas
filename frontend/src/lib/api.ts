import { useAuthStore } from "@/stores/auth";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** FastAPI sends `detail` as a string, or as a list of field errors on 422. */
function messageFrom(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: string };
      // Pydantic prefixes custom validation messages with "Value error, ".
      if (first.msg) return first.msg.replace(/^Value error, /, "");
    }
  }
  return fallback;
}

type Query = Record<string, string | number | boolean | null | undefined>;

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  query?: Query;
  body?: unknown;
  /** Skip the Authorization header and the sign-out-on-401 behaviour. */
  anonymous?: boolean;
  signal?: AbortSignal;
}

/** Send a request and return the successful response; throws ApiError otherwise. */
async function request(path: string, accept: string, options: RequestOptions): Promise<Response> {
  const { method = "GET", query, body, anonymous = false, signal } = options;

  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== null && value !== undefined && value !== "") params.set(key, String(value));
  }
  const search = params.size > 0 ? `?${params}` : "";

  const headers: Record<string, string> = { Accept: accept };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const token = useAuthStore.getState().token;
  if (!anonymous && token) headers.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`/api/v1${path}${search}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "Cannot reach the server. Check your connection and try again.");
  }

  if (response.status === 401 && !anonymous) {
    // The token expired or the account was disabled; the guard sends the user to /login.
    useAuthStore.getState().clearSession();
  }
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    throw new ApiError(response.status, messageFrom(payload, `Request failed (${response.status})`));
  }
  return response;
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await request(path, "application/json", options);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export interface DownloadedFile {
  blob: Blob;
  /** The name the server gave the file, from Content-Disposition. */
  filename: string;
}

/** Fetch a file (a PDF, say) with the user's session. Errors still arrive as ApiError. */
export async function apiFile(
  path: string,
  fallbackName: string,
  options: RequestOptions = {},
): Promise<DownloadedFile> {
  const response = await request(path, "*/*", options);
  const named = /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") ?? "");
  return { blob: await response.blob(), filename: named?.[1] ?? fallbackName };
}

/** Hand a fetched file to the browser as a download. */
export function saveFile({ blob, filename }: DownloadedFile): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Revoked a little later: some browsers start the download asynchronously.
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

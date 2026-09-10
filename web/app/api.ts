// Helpers de fetch: sempre same-origin (/api/*), sem URL nem chave no cliente.

import type {
  ApiErrorBody,
  ConversationCreated,
  HealthResponse,
  MessageReply,
  TraceResponse,
} from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly conversationId: string | null;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.error;
    this.conversationId = body.conversation_id;
  }
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.error === "string" && typeof v.message === "string";
}

// Um 502 do rewrite do Next (API fora) chega como HTML: cai no fallback.
async function readErrorBody(res: Response): Promise<ApiErrorBody> {
  try {
    const parsed: unknown = await res.json();
    if (isApiErrorBody(parsed)) return parsed;
  } catch {
    // corpo não-JSON
  }
  return {
    error: `http_${res.status}`,
    message: res.statusText || `erro HTTP ${res.status}`,
    conversation_id: null,
  };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    cache: "no-store",
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new ApiError(res.status, await readErrorBody(res));
  return (await res.json()) as T;
}

export function createConversation(): Promise<ConversationCreated> {
  return request<ConversationCreated>("/api/conversations", { method: "POST" });
}

export function sendMessage(conversationId: string, text: string): Promise<MessageReply> {
  return request<MessageReply>(
    `/api/conversations/${encodeURIComponent(conversationId)}/messages`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    },
  );
}

export function getTrace(conversationId: string, signal?: AbortSignal): Promise<TraceResponse> {
  return request<TraceResponse>(
    `/api/conversations/${encodeURIComponent(conversationId)}/trace`,
    { signal },
  );
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/api/health");
}

// Mensagem legível para a UI a partir de qualquer falha (API ou rede).
export function describeError(err: unknown): string {
  if (err instanceof ApiError) return `${err.message} (${err.code})`;
  if (err instanceof DOMException && err.name === "AbortError") return "requisição cancelada";
  if (err instanceof TypeError) return "falha de rede: não foi possível alcançar a API";
  if (err instanceof Error) return err.message;
  return "erro inesperado";
}

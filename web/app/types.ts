// Tipos espelhando o contrato JSON do agent-api (servido same-origin em /api).

export type MessageStatus = "answered" | "handoff" | "refused" | "degraded";

export type BreakerState = "closed" | "open" | "half_open";

export interface BreakerSnapshot {
  state: BreakerState;
  consecutive_failures: number;
  threshold: number;
  retry_in_s?: number;
  open_count?: number;
}

export interface HandoffPayload {
  rule_id: string;
  reason: string;
  summary: string;
  collected: Record<string, unknown>;
  quote_attempts: Record<string, unknown>[];
  skills_used: string[];
}

export interface ConversationCreated {
  conversation_id: string;
  created_at: string;
}

export interface MessageReply {
  conversation_id: string;
  message_id: string;
  reply: string;
  status: MessageStatus;
  skills_used: string[];
  rules_applied: string[];
  handoff: HandoffPayload | null;
  breaker: BreakerSnapshot;
}

export interface ApiErrorBody {
  error: string;
  message: string;
  conversation_id: string | null;
}

export type TraceEventType =
  | "ingress"
  | "skill_selection"
  | "llm_call"
  | "tool_call"
  | "guard"
  | "handoff"
  | "outbound"
  | "error";

export type TraceStatus =
  | "ok"
  | "error"
  | "refused"
  | "blocked"
  | "skipped"
  | "pass"
  | "degraded";

export type InjectionVerdict = "benign" | "suspicious" | "injection";

export interface TraceError {
  kind: string;
  message: string;
  retryable: boolean;
  http_status?: number;
}

// `detail` varia por tipo de evento; os campos conhecidos ficam tipados e o
// resto permanece acessível como unknown para o JSON bruto.
export interface TraceDetail {
  gate?: string;
  reason?: string;
  evidence?: string[];
  will_retry?: boolean;
  wait_s?: number;
  plano_id?: string;
  premio_mensal?: number;
  router?: string;
  events?: string[];
  excluded?: string[];
  status?: string;
  quote_status?: string;
  [key: string]: unknown;
}

// O backend omite chaves nulas/vazias, por isso quase tudo é opcional.
export interface TraceEvent {
  ts: string;
  conversation_id: string;
  event: TraceEventType;
  status: TraceStatus;
  message_id?: string;
  turn?: number;
  span_id?: string;
  parent_span_id?: string;
  latency_ms?: number;
  tool?: string;
  input_sanitized?: unknown;
  http_status?: number;
  attempt?: number;
  attempts_total?: number;
  error?: TraceError;
  skills_used?: string[];
  rules_applied?: string[];
  breaker?: Pick<BreakerSnapshot, "state" | "consecutive_failures" | "threshold">;
  pii_masked?: string[];
  injection_verdict?: InjectionVerdict;
  model?: string;
  tokens?: { in: number; out: number };
  detail?: TraceDetail;
}

export interface TraceResponse {
  conversation_id: string;
  count: number;
  events: TraceEvent[];
}

export interface HealthResponse {
  status: string;
  ts?: string;
  llm: { mode: "openai" | "fake"; model: string | null };
  quote_api: { url: string; catalog_loaded: boolean; breaker: BreakerSnapshot };
  conversations: number;
}

// Estado local do chat (não vem da API).
export type ChatRole = "lead" | "agent" | "error";

export interface ChatMessage {
  id: string;
  role: ChatRole;
  text: string;
  status?: MessageStatus;
  skills_used?: string[];
  rules_applied?: string[];
  handoff?: HandoffPayload | null;
}

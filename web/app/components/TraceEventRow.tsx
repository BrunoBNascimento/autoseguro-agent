"use client";

import type { TraceEvent, TraceEventType } from "../types";

const EVENT_LABEL: Record<TraceEventType, string> = {
  ingress: "ingress",
  skill_selection: "skill_selection",
  llm_call: "llm_call",
  tool_call: "tool_call",
  guard: "guard",
  handoff: "handoff",
  outbound: "outbound",
  error: "error",
};

export type IconKind = "ok" | "error" | "retry" | "warn" | "neutral";

export function iconFor(ev: TraceEvent): { glyph: string; kind: IconKind } {
  if (ev.event === "tool_call" && ev.detail?.will_retry) return { glyph: "↻", kind: "retry" };
  switch (ev.status) {
    case "ok":
    case "pass":
      return { glyph: "✓", kind: "ok" };
    case "error":
    case "blocked":
      return { glyph: "✗", kind: "error" };
    case "skipped":
      return { glyph: "↻", kind: "retry" };
    case "refused":
    case "degraded":
      return { glyph: "⚠", kind: "warn" };
    default:
      return { glyph: "•", kind: "neutral" };
  }
}

function fmtLatency(ms: number | undefined): string | null {
  return typeof ms === "number" ? `${Math.round(ms)} ms` : null;
}

function fmtTime(ts: string): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleTimeString("pt-BR", { hour12: false }) +
    "." + String(d.getMilliseconds()).padStart(3, "0");
}

// Fatos inline por tipo de evento; só o que existe no evento entra na lista.
function factsFor(ev: TraceEvent): string[] {
  const facts: string[] = [];
  const d = ev.detail ?? {};
  const rules = ev.rules_applied ?? [];
  const skills = ev.skills_used ?? [];

  switch (ev.event) {
    case "tool_call":
      if (ev.tool) facts.push(ev.tool);
      if (typeof ev.http_status === "number") facts.push(`HTTP ${ev.http_status}`);
      if (typeof ev.attempt === "number") {
        facts.push(
          `tentativa ${ev.attempt}${typeof ev.attempts_total === "number" ? `/${ev.attempts_total}` : ""}`,
        );
      }
      if (d.will_retry) {
        facts.push(typeof d.wait_s === "number" ? `retry em ${d.wait_s}s` : "vai repetir");
      }
      if (d.plano_id) facts.push(`plano ${d.plano_id}`);
      if (typeof d.premio_mensal === "number") {
        facts.push(`R$ ${d.premio_mensal.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}/mês`);
      }
      break;
    case "guard":
      if (d.gate) facts.push(d.gate);
      if (rules.length) facts.push(rules.join(", "));
      if (d.reason) facts.push(d.reason);
      break;
    case "llm_call":
      if (ev.model) facts.push(ev.model);
      if (ev.tokens) facts.push(`tokens ${ev.tokens.in}→${ev.tokens.out}`);
      break;
    case "ingress":
      facts.push(ev.pii_masked && ev.pii_masked.length ? `pii: ${ev.pii_masked.join(", ")}` : "pii: nenhuma");
      if (ev.injection_verdict) facts.push(`injeção: ${ev.injection_verdict}`);
      break;
    case "skill_selection":
      facts.push(skills.length ? `skills: ${skills.join(", ")}` : "skills: nenhuma");
      break;
    case "handoff":
      if (rules.length) facts.push(rules.join(", "));
      if (d.reason) facts.push(d.reason);
      break;
    case "outbound":
      if (d.status) facts.push(d.status);
      if (d.quote_status) facts.push(`cotação: ${d.quote_status}`);
      break;
    case "error":
      break;
  }

  if (ev.error) facts.push(`${ev.error.kind}: ${ev.error.message}`);
  const lat = fmtLatency(ev.latency_ms);
  if (lat) facts.push(lat);
  return facts;
}

interface TraceEventRowProps {
  event: TraceEvent;
  expanded: boolean;
  onToggle: () => void;
}

export function TraceEventRow({ event, expanded, onToggle }: TraceEventRowProps) {
  const icon = iconFor(event);
  const facts = factsFor(event);
  const label = EVENT_LABEL[event.event] ?? String(event.event);

  return (
    <li className={`trace-row trace-row-${icon.kind}`}>
      <button
        type="button"
        className="trace-row-head"
        onClick={onToggle}
        aria-expanded={expanded}
        aria-label={`${label} ${event.status}: ${expanded ? "ocultar" : "ver"} JSON`}
      >
        <span className={`trace-icon trace-icon-${icon.kind}`} aria-hidden="true">
          {icon.glyph}
        </span>
        <span className="trace-type mono">{label}</span>
        <span className="trace-status mono">{event.status}</span>
        <span className="trace-facts">
          {facts.map((f, i) => (
            <span key={i} className="trace-fact">
              {f}
            </span>
          ))}
        </span>
        <time className="trace-time mono" dateTime={event.ts}>
          {fmtTime(event.ts)}
        </time>
      </button>
      {expanded && (
        <pre className="trace-json mono">{JSON.stringify(event, null, 2)}</pre>
      )}
    </li>
  );
}

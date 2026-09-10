"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { describeError, getTrace } from "../api";
import type { BreakerSnapshot, TraceEvent } from "../types";
import { BreakerPill } from "./BreakerPill";
import { TraceEventRow } from "./TraceEventRow";

const POLL_MS = 1500;

interface TracePanelProps {
  conversationId: string | null;
  // Incrementado pela página após cada resposta para forçar refresh imediato.
  refreshToken: number;
  breaker: BreakerSnapshot | null;
}

interface TurnGroup {
  turn: number | null;
  events: { key: string; event: TraceEvent }[];
}

function groupByTurn(events: TraceEvent[]): TurnGroup[] {
  const groups = new Map<number | null, TurnGroup>();
  events.forEach((ev, idx) => {
    const turn = typeof ev.turn === "number" ? ev.turn : null;
    let g = groups.get(turn);
    if (!g) {
      g = { turn, events: [] };
      groups.set(turn, g);
    }
    g.events.push({ key: ev.span_id ?? `${turn ?? "x"}-${idx}`, event: ev });
  });
  return [...groups.values()];
}

function toJsonl(events: TraceEvent[]): string {
  return events.map((ev) => JSON.stringify(ev)).join("\n") + (events.length ? "\n" : "");
}

export function TracePanel({ conversationId, refreshToken, breaker }: TracePanelProps) {
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const inFlight = useRef<AbortController | null>(null);

  const load = useCallback(async (): Promise<TraceEvent[] | null> => {
    if (!conversationId) return null;
    inFlight.current?.abort();
    const ctrl = new AbortController();
    inFlight.current = ctrl;
    try {
      const res = await getTrace(conversationId, ctrl.signal);
      if (ctrl.signal.aborted) return null;
      setEvents(res.events);
      setError(null);
      return res.events;
    } catch (err) {
      if (ctrl.signal.aborted) return null;
      setError(describeError(err));
      return null;
    }
  }, [conversationId]);

  // Polling enquanto houver conversa; limpa ao trocar/encerrar.
  useEffect(() => {
    if (!conversationId) {
      setEvents([]);
      setError(null);
      return;
    }
    setEvents([]);
    setExpanded(new Set());
    void load();
    const id = window.setInterval(() => void load(), POLL_MS);
    return () => {
      window.clearInterval(id);
      inFlight.current?.abort();
    };
  }, [conversationId, load]);

  useEffect(() => {
    if (refreshToken > 0) void load();
  }, [refreshToken, load]);

  function toggle(key: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  // Busca a versão mais recente antes de exportar para não perder evento.
  async function exportJsonl() {
    if (!conversationId) return;
    const latest = (await load()) ?? events;
    const blob = new Blob([toJsonl(latest)], { type: "application/x-ndjson" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `trace-${conversationId}.jsonl`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  const groups = groupByTurn(events);

  return (
    <aside className="panel trace" aria-label="Trace da conversa">
      <div className="trace-header">
        <h2>
          Trace <code className="mono">{conversationId ?? "—"}</code>
        </h2>
        <span className="trace-count">{events.length} eventos</span>
      </div>

      {error && (
        <p className="trace-error" role="status">
          trace indisponível: {error} — tentando novamente…
        </p>
      )}

      <div className="trace-body">
        {!conversationId && <p className="trace-empty">Sem conversa ativa.</p>}
        {conversationId && events.length === 0 && !error && (
          <p className="trace-empty">Nenhum evento ainda.</p>
        )}
        {groups.map((g) => (
          <section key={g.turn ?? "none"} className="trace-turn">
            <h3 className="trace-turn-title">
              {g.turn === null ? "Sem turno" : `Turno ${g.turn}`}
            </h3>
            <ul className="trace-list">
              {g.events.map(({ key, event }) => (
                <TraceEventRow
                  key={key}
                  event={event}
                  expanded={expanded.has(key)}
                  onToggle={() => toggle(key)}
                />
              ))}
            </ul>
          </section>
        ))}
      </div>

      <footer className="trace-footer">
        <div className="trace-footer-row">
          <BreakerPill breaker={breaker} />
          <button
            type="button"
            className="btn"
            onClick={() => void exportJsonl()}
            disabled={!conversationId || events.length === 0}
            aria-label="Exportar trace em JSON Lines"
          >
            Exportar trace (.jsonl)
          </button>
        </div>
        <ul className="legend" aria-label="Legenda dos ícones">
          <li><span className="trace-icon trace-icon-ok">✓</span> ok / pass</li>
          <li><span className="trace-icon trace-icon-error">✗</span> error / blocked</li>
          <li><span className="trace-icon trace-icon-retry">↻</span> retry / skipped</li>
          <li><span className="trace-icon trace-icon-warn">⚠</span> refused / degraded</li>
        </ul>
      </footer>
    </aside>
  );
}

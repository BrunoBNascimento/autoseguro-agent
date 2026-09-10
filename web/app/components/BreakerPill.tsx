"use client";

import type { BreakerSnapshot, BreakerState } from "../types";

const STATE_LABEL: Record<BreakerState, string> = {
  closed: "fechado",
  half_open: "semiaberto",
  open: "aberto",
};

interface BreakerPillProps {
  breaker: BreakerSnapshot | null;
}

export function BreakerPill({ breaker }: BreakerPillProps) {
  if (!breaker) {
    return (
      <span className="pill pill-unknown" title="Estado do circuit breaker da API de cotação">
        breaker: —
      </span>
    );
  }
  const retry =
    breaker.state === "open" && typeof breaker.retry_in_s === "number"
      ? ` · retry em ${Math.ceil(breaker.retry_in_s)}s`
      : "";
  return (
    <span
      className={`pill pill-${breaker.state}`}
      title="Estado do circuit breaker da API de cotação"
    >
      breaker: {STATE_LABEL[breaker.state] ?? breaker.state}{" "}
      <span className="mono">
        {breaker.consecutive_failures}/{breaker.threshold}
      </span>
      {retry}
    </span>
  );
}

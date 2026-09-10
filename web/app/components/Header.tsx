"use client";

import type { HealthResponse } from "../types";

interface HeaderProps {
  health: HealthResponse | null;
  healthFailed: boolean;
  conversationId: string | null;
  creating: boolean;
  onNewConversation: () => void;
}

function llmLabel(health: HealthResponse | null, failed: boolean): string {
  if (failed) return "API indisponível";
  if (!health) return "carregando…";
  if (health.llm.mode === "fake") return "modo determinístico (sem chave)";
  return `modelo: ${health.llm.model ?? "desconhecido"}`;
}

export function Header({
  health,
  healthFailed,
  conversationId,
  creating,
  onNewConversation,
}: HeaderProps) {
  return (
    <header className="header">
      <div className="header-title">
        <h1>AutoSeguro — agente de cotação</h1>
        <span className="header-meta">{llmLabel(health, healthFailed)}</span>
      </div>
      <div className="header-right">
        <span className="header-meta">
          conversa: <code className="mono">{conversationId ?? "—"}</code>
        </span>
        <button
          type="button"
          className="btn btn-primary"
          onClick={onNewConversation}
          disabled={creating}
          aria-label="Iniciar nova conversa"
        >
          {creating ? "Criando…" : "Nova conversa"}
        </button>
      </div>
    </header>
  );
}

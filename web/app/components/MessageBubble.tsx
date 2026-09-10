"use client";

import type { ChatMessage, MessageStatus } from "../types";

const STATUS_BADGE: Record<Exclude<MessageStatus, "answered">, string> = {
  handoff: "Encaminhado para atendente",
  refused: "Perfil recusado pela seguradora",
  degraded: "Cotação indisponível",
};

interface MessageBubbleProps {
  message: ChatMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  if (message.role === "error") {
    return (
      <div className="msg-row msg-row-agent">
        <div className="bubble bubble-error" role="alert">
          {message.text}
        </div>
      </div>
    );
  }

  const isLead = message.role === "lead";
  const status = message.status;
  const badge = status && status !== "answered" ? STATUS_BADGE[status] : null;
  const skills = message.skills_used ?? [];
  const rules = message.rules_applied ?? [];

  return (
    <div className={`msg-row ${isLead ? "msg-row-lead" : "msg-row-agent"}`}>
      <div className={`bubble ${isLead ? "bubble-lead" : "bubble-agent"}`}>
        {badge && (
          <span
            className={`badge badge-${status}`}
            title={message.handoff?.reason ?? undefined}
          >
            {badge}
          </span>
        )}
        <p className="bubble-text">{message.text}</p>
        {!isLead && (skills.length > 0 || rules.length > 0) && (
          <div className="chips" aria-label="Skills e regras aplicadas">
            {skills.map((s) => (
              <span key={`s-${s}`} className="chip chip-skill mono">
                {s}
              </span>
            ))}
            {rules.map((r) => (
              <span key={`r-${r}`} className="chip chip-rule mono">
                {r}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

"use client";

import { useEffect, useRef, useState } from "react";
import { describeError, sendMessage } from "../api";
import type { ChatMessage, MessageReply } from "../types";
import { Composer } from "./Composer";
import { MessageBubble } from "./MessageBubble";

interface ChatProps {
  conversationId: string | null;
  onReply: (reply: MessageReply) => void;
}

export function Chat({ conversationId, onReply }: ChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const seq = useRef(0);

  function nextId(prefix: string): string {
    seq.current += 1;
    return `${prefix}-${seq.current}`;
  }

  // Mantém a lista rolada até a última mensagem.
  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, sending]);

  async function handleSend(text: string) {
    if (!conversationId || sending) return;
    setMessages((prev) => [...prev, { id: nextId("lead"), role: "lead", text }]);
    setSending(true);
    try {
      const reply = await sendMessage(conversationId, text);
      setMessages((prev) => [
        ...prev,
        {
          id: reply.message_id || nextId("agent"),
          role: "agent",
          text: reply.reply,
          status: reply.status,
          skills_used: reply.skills_used,
          rules_applied: reply.rules_applied,
          handoff: reply.handoff,
        },
      ]);
      onReply(reply);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { id: nextId("err"), role: "error", text: `Erro ao enviar: ${describeError(err)}` },
      ]);
    } finally {
      setSending(false);
    }
  }

  return (
    <section className="panel chat" aria-label="Chat com o agente">
      <div className="chat-messages" ref={listRef} aria-live="polite" aria-relevant="additions">
        {messages.length === 0 && !sending && (
          <p className="chat-empty">
            {conversationId
              ? "Envie uma mensagem para começar a cotação."
              : "Criando conversa…"}
          </p>
        )}
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}
        {sending && (
          <div className="msg-row msg-row-agent">
            <div className="bubble bubble-agent bubble-typing" aria-label="Agente digitando">
              digitando
              <span className="dots" aria-hidden="true">
                <i />
                <i />
                <i />
              </span>
            </div>
          </div>
        )}
      </div>
      <Composer disabled={!conversationId} sending={sending} onSend={handleSend} />
    </section>
  );
}

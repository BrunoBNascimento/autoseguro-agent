"use client";

import { useState, type FormEvent, type KeyboardEvent } from "react";

interface ComposerProps {
  disabled: boolean;
  sending: boolean;
  onSend: (text: string) => void;
}

export function Composer({ disabled, sending, onSend }: ComposerProps) {
  const [text, setText] = useState("");
  const canSend = !disabled && !sending && text.trim().length > 0;

  function submit() {
    if (!canSend) return;
    onSend(text.trim());
    setText("");
  }

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    submit();
  }

  // Enter envia; Shift+Enter quebra linha.
  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <textarea
        className="composer-input"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={disabled ? "Aguardando conversa…" : "Digite sua mensagem"}
        aria-label="Mensagem para o agente"
        rows={2}
        disabled={disabled || sending}
      />
      <button
        type="submit"
        className="btn btn-primary composer-send"
        disabled={!canSend}
        aria-label="Enviar mensagem"
      >
        {sending ? "Enviando…" : "Enviar"}
      </button>
    </form>
  );
}

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createConversation, describeError, getHealth } from "./api";
import { Chat } from "./components/Chat";
import { Header } from "./components/Header";
import { Notice } from "./components/Notice";
import { TracePanel } from "./components/TracePanel";
import type { BreakerSnapshot, HealthResponse, MessageReply } from "./types";

export default function Page() {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthFailed, setHealthFailed] = useState(false);
  const [breaker, setBreaker] = useState<BreakerSnapshot | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [traceVersion, setTraceVersion] = useState(0);
  const booted = useRef(false);

  const startConversation = useCallback(async () => {
    setCreating(true);
    try {
      const created = await createConversation();
      setConversationId(created.conversation_id);
      setTraceVersion(0);
      setNotice(null);
    } catch (err) {
      setNotice(`Não foi possível criar a conversa: ${describeError(err)}`);
    } finally {
      setCreating(false);
    }
  }, []);

  // Boot: health + primeira conversa. O ref evita duplicar no StrictMode.
  useEffect(() => {
    if (booted.current) return;
    booted.current = true;
    void (async () => {
      try {
        const h = await getHealth();
        setHealth(h);
        setBreaker(h.quote_api.breaker);
      } catch (err) {
        setHealthFailed(true);
        setNotice(`API indisponível: ${describeError(err)}`);
      }
    })();
    void startConversation();
  }, [startConversation]);

  function handleReply(reply: MessageReply) {
    setBreaker(reply.breaker);
    setTraceVersion((v) => v + 1);
  }

  return (
    <div className="app">
      <Header
        health={health}
        healthFailed={healthFailed}
        conversationId={conversationId}
        creating={creating}
        onNewConversation={() => void startConversation()}
      />
      {notice && <Notice message={notice} onDismiss={() => setNotice(null)} />}
      <main className="columns">
        {/* key força remontagem do chat (limpa mensagens) a cada conversa */}
        <Chat key={conversationId ?? "none"} conversationId={conversationId} onReply={handleReply} />
        <TracePanel conversationId={conversationId} refreshToken={traceVersion} breaker={breaker} />
      </main>
    </div>
  );
}

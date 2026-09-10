"""Smoke contra o serviço REAL de cotação (compose de pé).

    QUOTE_API_URL=http://localhost:8000 uv run python -m evals.smoke --expect happy
    # com QUOTE_FAILURE_RATE=1.0 no compose:
    uv run python -m evals.smoke --expect degraded

Usa o modelo determinístico: o que se testa aqui é a integração com a /quote verdadeira."""

from __future__ import annotations

import argparse
import sys

from agent.config import Settings
from agent.llm import RuleBasedLLM
from agent.runtime import build_runtime
from agent.tracing.sink import MemorySink


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect", choices=["happy", "degraded"], default="happy")
    ap.add_argument("--url", default=None)
    args = ap.parse_args()
    settings = Settings(llm_mode="fake", **({"quote_api_url": args.url} if args.url else {}))
    sink = MemorySink()
    rt = build_runtime(settings, llm=RuleBasedLLM(), sink=sink)
    cid = rt.store.create().conversation_id
    turns = ["quero o completo", "tenho 35 anos, onix 2022, cep 01310-100", "tenta de novo"]
    results = []
    for t in turns:
        r = rt.orchestrator.handle(cid, t)
        results.append(r)
        print(
            f"lead:   {t}\nagente: {r.reply}\n        status={r.status} skills={r.skills_used} breaker={r.breaker['state']}\n"
        )
        if r.status in ("answered",) and "R$" in r.reply:
            break
    calls = [e for e in sink.events if e["event"] == "tool_call"]
    print(
        f"tool_calls: {[(e['status'], e.get('http_status'), round(e.get('latency_ms', 0), 1)) for e in calls]}"
    )
    has_price = any("R$" in r.reply for r in results)
    if args.expect == "happy":
        ok = has_price
        print(
            "RESULTADO:",
            "cotação saiu"
            if ok
            else "cotação não saiu (com FAILURE_RATE padrão isso acontece em ~2,7% dos casos)",
        )
    else:
        ok = not has_price and any(r.status in ("degraded", "handoff") for r in results)
        print("RESULTADO:", "degradação sem preço" if ok else "esperava degradação sem preço")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

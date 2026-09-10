"""Log de uma execução completa (entregável do challenge): uma conversa do início ao fim,
com a cotação saindo, em transcript legível + trace JSONL.

    uv run python -m evals.demo                 # LLM real se houver OPENAI_API_KEY; /quote real se alcançável
    uv run python -m evals.demo --scenario degraded   # simula QUOTE_FAILURE_RATE=1.0 (503 em tudo)
    uv run python -m evals.demo --offline       # força fake de LLM e lógica local de cotação

Saída em docs/demo/<scenario>-transcript.md e docs/demo/<scenario>-trace.jsonl."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

import httpx

from agent.config import get_settings
from agent.llm import RuleBasedLLM
from agent.runtime import build_runtime
from agent.security.pii import Policy, sanitize_text
from agent.tracing.sink import MemorySink
from evals import fake_transport as ft

ROOT = Path(__file__).resolve().parents[1]

LEAD_TURNS = {
    "happy": [
        "Oi, queria fazer um seguro pro meu carro",
        "é um Onix 2022, quero o plano completo",
        "tenho 35 anos, meu cpf é 389.083.863-43 e o cep é 07123-456",
        "pode começar dia 15/10/2026",
        "achei um pouco caro... o que ta incluso nisso?",
        "beleza, vou pensar e te falo. obrigado!",
    ],
    "degraded": [
        "Boa tarde, quero uma cotacao",
        "completo, tenho 35 anos, onix 2022, cep 01310-100",
        "tenta de novo por favor",
        "quanto fica mais ou menos então?",
    ],
}


def quote_api_reachable(url: str) -> bool:
    try:
        return httpx.get(f"{url.rstrip('/')}/health", timeout=2.0).status_code == 200
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", choices=list(LEAD_TURNS), default="happy")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "docs" / "demo"))
    args = ap.parse_args()

    settings = get_settings()
    sink = MemorySink()
    transport: Any
    if args.scenario == "degraded":
        transport = ft.FakeQuoteTransport([], default=503)
        transport_note = (
            "FakeQuoteTransport com 503 em toda chamada (equivale a QUOTE_FAILURE_RATE=1.0)"
        )
    elif args.offline or not quote_api_reachable(settings.quote_api_url):
        transport = ft.LocalLogicTransport(dt.date.today())
        transport_note = (
            "lógica de cotação vendorizada em processo (quote-api não alcançável ou --offline)"
        )
    else:
        transport = None
        transport_note = f"quote-api real em {settings.quote_api_url}"
    llm = RuleBasedLLM() if (args.offline or not settings.llm_enabled) else None
    rt = build_runtime(settings, transport=transport, llm=llm, sink=sink)
    llm_note = (
        f"OpenAI {settings.llm_model} (roteador {settings.llm_model_cheap})"
        if rt.llm_mode == "openai"
        else "modelo determinístico (sem chave)"
    )

    cid = rt.store.create().conversation_id
    lines = [
        f"# Execução completa — cenário `{args.scenario}`",
        "",
        f"- data: {dt.datetime.now(dt.UTC).isoformat(timespec='seconds')}",
        f"- conversa: `{cid}`",
        f"- LLM: {llm_note}",
        f"- cotação: {transport_note}",
        f"- trace completo: `{args.scenario}-trace.jsonl` (um evento por linha, já sanitizado)",
        "",
        "Mensagens do lead aparecem aqui já sanitizadas (mesma máscara que o modelo recebeu).",
        "",
    ]
    for turn in LEAD_TURNS[args.scenario]:
        r = rt.orchestrator.handle(cid, turn)
        shown = sanitize_text(turn, Policy.PERSISTENCE).text
        lines += [
            f"**lead:** {shown}",
            "",
            f"**agente:** {r.reply}",
            "",
            f"<sub>status=`{r.status}` · skills={r.skills_used} · regras={r.rules_applied} · breaker={r.breaker['state']}"
            + (f" · handoff={r.handoff['rule_id']}" if r.handoff else "")
            + "</sub>",
            "",
        ]
        print(f"lead:   {shown}\nagente: {r.reply}\n")
        if r.status == "handoff":
            break

    events = [e for e in sink.events if e["conversation_id"] == cid]
    tool = [e for e in events if e["event"] == "tool_call"]
    lines += [
        "## Resumo do trace",
        "",
        f"- {len(events)} eventos · {len(tool)} chamadas à /quote: "
        + ", ".join(
            f"{e['status']}/{e.get('http_status')}@{e.get('latency_ms', 0):.0f}ms" for e in tool
        ),
        f"- gates: {len([e for e in events if e['event'] == 'guard'])} verificações, "
        f"{len([e for e in events if e['event'] == 'guard' and e['status'] == 'blocked'])} bloqueios",
        "",
    ]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{args.scenario}-transcript.md").write_text("\n".join(lines), encoding="utf-8")
    (out / f"{args.scenario}-trace.jsonl").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n", encoding="utf-8"
    )
    print(
        f"→ {out / f'{args.scenario}-transcript.md'}\n→ {out / f'{args.scenario}-trace.jsonl'} ({len(events)} eventos)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Eval harness: `uv run python -m evals.run` → evals/REPORT.md. Sem rede, sem chave.

Grading determinístico primeiro: invariantes (BR-01..BR-06, BR-12..BR-14, SEC-01) são
asserções em Python. Meta: zero violações. Exit code 1 se algum cenário falhar."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from collections import Counter
from pathlib import Path

from evals.harness import ScenarioResult, run_scenario, summarize_latency
from evals.scenarios import all_scenarios

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default=str(ROOT / "evals" / "REPORT.md"))
    ap.add_argument("--cases", default=str(ROOT / "evals" / "cases" / "dataset_cases.json"))
    ap.add_argument("--only", default=None, help="filtra por categoria ou prefixo de id")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    scenarios = all_scenarios(Path(args.cases))
    if args.only:
        scenarios = [s for s in scenarios if s.category == args.only or s.id.startswith(args.only)]

    started = time.perf_counter()
    results: list[ScenarioResult] = []
    for sc in scenarios:
        res = run_scenario(sc)
        results.append(res)
        mark = "ok " if res.passed else "FAIL"
        if args.verbose or not res.passed:
            print(f"[{mark}] {sc.id}: {sc.title}")
            for f in res.failures:
                print(f"       - {f}")
    elapsed = time.perf_counter() - started

    report = render_report(results, elapsed)
    Path(args.report).write_text(report, encoding="utf-8")
    failed = [r for r in results if not r.passed]
    print(
        f"\n{len(results) - len(failed)}/{len(results)} cenários ok em {elapsed:.1f}s → {args.report}"
    )
    return 1 if failed else 0


def render_report(results: list[ScenarioResult], elapsed: float) -> str:
    total = len(results)
    passed = sum(r.passed for r in results)
    violations = sum(r.invariant_violations for r in results)
    labeled = [r for r in results if r.scenario.expect_handoff is not None]
    tp = sum(1 for r in labeled if r.scenario.expect_handoff and r.handoff_happened)
    fp = sum(1 for r in labeled if not r.scenario.expect_handoff and r.handoff_happened)
    fn = sum(1 for r in labeled if r.scenario.expect_handoff and not r.handoff_happened)
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0

    quote_scen = [r for r in results if r.network_calls > 0]
    quote_ok = sum(
        1
        for r in quote_scen
        if any(s in ("answered",) for s in r.statuses) and r.replies and "R$" in " ".join(r.replies)
    )
    attempts = Counter(a for r in results for a in r.attempts)
    latencies = [x for r in results for x in r.latencies_ms]
    lat = summarize_latency(latencies)
    openings = sum(r.breaker_open_count for r in results)

    by_cat: dict[str, list[ScenarioResult]] = {}
    for r in results:
        by_cat.setdefault(r.scenario.category, []).append(r)

    lines = [
        "# Relatório de avaliação — agente AutoSeguro",
        "",
        f"Gerado em {dt.datetime.now(dt.UTC).isoformat(timespec='seconds')} por `uv run python -m evals.run` "
        f"({elapsed:.1f}s, sem rede, sem chave de LLM). Transporte fake programa a sequência exata de respostas da "
        "`/quote`; o modelo é determinístico ou roteirizado para se comportar mal. As asserções são sobre o EFEITO "
        "(o que o lead viu, quantas chamadas saíram, o que ficou no trace), não sobre a opinião de um classificador.",
        "",
        "## Resumo",
        "",
        "| Métrica | Valor | Meta |",
        "|---|---|---|",
        f"| Cenários aprovados | **{passed}/{total}** | {total}/{total} |",
        f"| Violações de invariante (resposta entregue que falha em algum gate) | **{violations}** | 0 |",
        f"| Handoff — precisão / recall (sobre {len(labeled)} cenários rotulados) | {precision:.2f} / {recall:.2f} | 1.00 / 1.00 |",
        f"| Cotações com sucesso (cenários que chegaram à rede) | {quote_ok}/{len(quote_scen)} | — (depende do roteiro) |",
        f"| Aberturas de breaker | {openings} | só nos cenários que forçam |",
        f"| Distribuição de tentativas (evento `tool_call`) | {dict(sorted(attempts.items()))} | — |",
        f"| Latência dos eventos (fake, ms) p50 / p95 / máx | {lat['p50']:.2f} / {lat['p95']:.2f} / {lat['max']:.2f} | — |",
        "",
        "Cobertura de campos do trace: todo `tool_call` e `llm_call` com `latency_ms`; cada tentativa de retry é seu "
        "próprio evento; `guard` bloqueado sempre com `rules_applied`; nenhum CPF/e-mail/telefone/placa/CEP completo.",
        "",
    ]
    for cat, items in by_cat.items():
        lines += [
            f"## {cat} ({sum(r.passed for r in items)}/{len(items)})",
            "",
            "| Cenário | Resultado | Turnos | Rede | Observação |",
            "|---|---|---|---|---|",
        ]
        for r in items:
            obs = "; ".join(r.failures) if r.failures else r.scenario.title
            lines.append(
                f"| `{r.scenario.id}` | {'✅' if r.passed else '❌'} | {', '.join(r.statuses) or '—'} | {r.network_calls} | {obs} |"
            )
        lines.append("")
    failed = [r for r in results if not r.passed]
    if failed:
        lines += ["## Falhas", ""]
        for r in failed:
            lines.append(f"- `{r.scenario.id}`: " + " · ".join(r.failures))
        lines.append("")
    lines += [
        "## Como ler",
        "",
        "- **resiliencia**: taxonomia de erro pelo corpo, retry só em transitório, breaker por falhas consecutivas, pré-validação.",
        "- **invariantes**: modelo roteirizado para violar regras; o que chega ao lead passa pelos gates.",
        "- **injection**: 15 ataques + 5 controles. A métrica é efeito bloqueado e system prompt intacto, não acurácia.",
        "- **pii**: máscara antes do modelo (camada 1) e antes de persistir (camada 2); insulto preservado.",
        "- **handoff**: gatilhos explícitos com regra rastreável; objeção comum não é handoff.",
        "- **dataset**: replay dos turnos do lead (sanitizados) estratificado por desfecho × elegibilidade de recusa.",
        "",
        "Complemento com o serviço real: `make smoke` (compose de pé) roda o caminho feliz contra a `/quote` verdadeira.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())

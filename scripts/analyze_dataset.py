# /// script
# requires-python = ">=3.12"
# dependencies = ["pandas>=2.2", "pyarrow>=15"]
# ///
"""Reproduz a análise do dataset do challenge com números verificáveis.

    uv run scripts/analyze_dataset.py --ref-date 2026-09-10 [--check]

Saídas:
- evals/dataset_report.md         relatório legível (sem PII)
- evals/cases/dataset_cases.json  casos estratificados por desfecho × elegibilidade de
                                  recusa, com os turnos do lead já sanitizados

O dataset é usado para ANÁLISE e para criar casos de avaliação. Não é fonte de preço:
o relatório prova isso comparando o preço dito pelo vendedor com o que a API devolve.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import random
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # agent.security.pii é stdlib puro

from agent.security.pii import Policy, cep_prefix, find_pii, sanitize_text  # noqa: E402

VENDOR = ROOT / "vendor" / "namastex-fde-challenge"
PARQUET = VENDOR / "dataset" / "conversations.parquet"
QUOTE_LOGIC = VENDOR / "quote-service" / "app" / "quote_logic.py"

HIGH_RISK = {"07", "08", "21", "26", "59"}
PLAN_COVERS = {"essencial": 3, "completo": 5, "premium": 7}

# Valores medidos no discovery (2026-09-10). `--check` falha se divergirem.
EXPECTED = {
    "conversations": 2500,
    "messages": 26470,
    "quotable": 1749,
    "price_matches": 0,
    "refusable_any": 751,
    "refusable_age": 280,
    "refusable_vehicle": 531,
    "high_risk_cep": 895,
    "pii_messages": 4718,
    "non_monotonic": 2495,
    "franquia_antipattern": 757,
    "rever_antipattern": 538,
    "coverage_wrong_superior": 1677,
}


def load_quote_logic(ref_date: dt.date):
    spec = importlib.util.spec_from_file_location("vendored_quote_logic", QUOTE_LOGIC)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class FrozenDate(dt.date):
        @classmethod
        def today(cls):
            return cls(ref_date.year, ref_date.month, ref_date.day)

    class Shim:
        date = FrozenDate
        datetime = dt.datetime
        timedelta = dt.timedelta

    module.dt = Shim
    return module


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parquet", default=str(PARQUET))
    ap.add_argument(
        "--ref-date", default="2026-09-10", help="data de referência para a idade do veículo"
    )
    ap.add_argument("--out-report", default=str(ROOT / "evals" / "dataset_report.md"))
    ap.add_argument("--out-cases", default=str(ROOT / "evals" / "cases" / "dataset_cases.json"))
    ap.add_argument("--per-stratum", type=int, default=3)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--check", action="store_true", help="falha se os números divergirem dos medidos"
    )
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    ref_date = dt.date.fromisoformat(args.ref_date)
    logic = load_quote_logic(ref_date)

    df = pd.read_parquet(args.parquet)
    # Ordenar por message_index: 99,8% das conversas têm timestamp NÃO monótono.
    df = df.sort_values(["conversation_id", "message_index"]).reset_index(drop=True)
    n_conv = df.conversation_id.nunique()
    n_msg = len(df)

    ts = pd.to_datetime(df.timestamp)
    non_mono = 0
    for _cid, g in df.assign(_ts=ts).groupby("conversation_id", sort=False):
        if (g["_ts"].diff().dropna() < pd.Timedelta(0)).any():
            non_mono += 1

    outcomes = df.drop_duplicates("conversation_id").conversation_outcome.value_counts().to_dict()
    roles = df.sender_role.value_counts().to_dict()
    types = df.message_type.value_counts().to_dict()

    price_re = re.compile(r"plano (Essencial|Completo|Premium) por R\$ (\d+),90", re.IGNORECASE)
    cep_re = re.compile(r"\bcep (\d{5}-\d{3})\b", re.IGNORECASE)
    year_re = re.compile(r"\b(19[5-9]\d|20\d\d)\b")

    profiles: list[dict] = []
    for cid, g in df.groupby("conversation_id", sort=True):
        lead_msgs = g[g.sender_role == "lead"]
        vend_msgs = g[g.sender_role == "vendedor"]
        joined_lead = " ".join(lead_msgs.message_body)
        m_cep = cep_re.search(joined_lead)
        m_year = year_re.search(str(g.veiculo_texto.iloc[0]))
        m_price = next(
            (price_re.search(b) for b in vend_msgs.message_body if price_re.search(b)), None
        )
        profiles.append(
            {
                "conversation_id": cid,
                "outcome": g.conversation_outcome.iloc[0],
                "idade": int(g.lead_idade_informada.iloc[0]),
                "veiculo_ano": int(m_year.group(1)) if m_year else None,
                "cep": m_cep.group(1) if m_cep else None,
                "plano": m_price.group(1).lower() if m_price else None,
                "dataset_price": float(m_price.group(2)) + 0.90 if m_price else None,
                "lead_turns": [
                    sanitize_text(b, Policy.PERSISTENCE).text for b in lead_msgs.message_body
                ],
                "vendor_turns": [
                    sanitize_text(b, Policy.PERSISTENCE).text for b in vend_msgs.message_body
                ],
            }
        )

    # --- preço: dataset × API -------------------------------------------------------
    ratios: list[float] = []
    matches = 0
    quotable = 0
    refusable_age = refusable_vehicle = refusable_any = 0
    high_risk = 0
    for p in profiles:
        if p["cep"] and p["cep"][:2] in HIGH_RISK:
            high_risk += 1
        age_ref = p["idade"] > 75
        veh_ref = p["veiculo_ano"] is not None and (ref_date.year - p["veiculo_ano"]) > 20
        refusable_age += age_ref
        refusable_vehicle += veh_ref
        p["refusal_eligible"] = bool(age_ref or veh_ref)
        refusable_any += p["refusal_eligible"]
        try:
            q = logic.cotar(
                {
                    "plano_id": p["plano"],
                    "idade": p["idade"],
                    "veiculo_ano": p["veiculo_ano"],
                    "cep": p["cep"],
                }
            )
            p["api_price"] = q["premio_mensal"]
            quotable += 1
            if p["dataset_price"] is not None:
                if abs(q["premio_mensal"] - p["dataset_price"]) < 0.005:
                    matches += 1
                ratios.append(q["premio_mensal"] / p["dataset_price"])
        except logic.CotacaoRecusada as exc:
            p["api_price"] = None
            p["api_refusal"] = exc.motivo
    underestimate = sum(r > 1 for r in ratios) / len(ratios) if ratios else 0.0

    # --- anti-padrões do vendedor -----------------------------------------------------
    conv_text = {p["conversation_id"]: " ".join(p["vendor_turns"]) for p in profiles}
    franquia_ap = sum("ajustar a franquia" in t.lower() for t in conv_text.values())
    rever_ap = sum("consigo rever" in t.lower() for t in conv_text.values())
    coverage_claim = sum("cobre colisao, roubo e furto" in t.lower() for t in conv_text.values())
    coverage_wrong_superior = sum(
        1
        for p in profiles
        if p["plano"] in ("completo", "premium")
        and "cobre colisao, roubo e furto" in conv_text[p["conversation_id"]].lower()
    )
    price_for_refusable = sum(
        1 for p in profiles if p["refusal_eligible"] and p["dataset_price"] is not None
    )

    # --- PII --------------------------------------------------------------------------
    pii_msgs = 0
    pii_entities: Counter[str] = Counter()
    for body in df.message_body:
        labels = find_pii(str(body))
        if re.search(r"\b\d{5}-\d{3}\b", str(body)):
            labels.append("cep")
        if labels:
            pii_msgs += 1
            pii_entities.update(labels)
    convs_with = {
        ent: sum(
            1
            for p in profiles
            if ent in Counter(lab for t in p["lead_turns"] for lab in _labels_in_masked(t))
        )
        for ent in ("cpf", "email", "telefone", "placa")
    }

    # --- temas ausentes ---------------------------------------------------------------
    all_text = " ".join(df.message_body.astype(str)).lower()
    absent = {
        "carência": len(re.findall(r"car[êe]ncia", all_text)),
        "pro-rata/proporcional": len(re.findall(r"pro.?rata|proporcional", all_text)),
        "coberturas superiores (vidros/terceiros/carro reserva/assistência)": len(
            re.findall(r"vidro|terceiro|carro reserva|assist[êe]ncia", all_text)
        ),
        "agravo/região": len(re.findall(r"agravo|regi[ãa]o de risco|alto risco", all_text)),
        "handoff (atendente/humano/supervisor)": len(
            re.findall(r"atendente|humano|supervisor", all_text)
        ),
        "injection (ignore/esqueça/system prompt)": len(
            re.findall(r"\bignore\b|esque[çc]a|system prompt", all_text)
        ),
    }

    # --- casos estratificados -----------------------------------------------------------
    rng = random.Random(args.seed)
    strata: dict[tuple[str, bool], list[dict]] = {}
    for p in profiles:
        strata.setdefault((p["outcome"], p["refusal_eligible"]), []).append(p)
    cases = []
    for (outcome, elig), items in sorted(strata.items()):
        for p in rng.sample(items, min(args.per_stratum, len(items))):
            cases.append(
                {
                    "case_id": f"ds_{p['conversation_id']}",
                    "source_conversation_id": p["conversation_id"],
                    "outcome": outcome,
                    "refusal_eligible": elig,
                    "profile": {
                        "idade": p["idade"],
                        "veiculo_ano": p["veiculo_ano"],
                        "cep_prefix": cep_prefix(p["cep"]),
                        "plano": p["plano"],
                        "high_risk_region": bool(p["cep"] and p["cep"][:2] in HIGH_RISK),
                    },
                    "dataset_price": p["dataset_price"],
                    "api_price": p.get("api_price"),
                    "api_refusal": p.get("api_refusal"),
                    "lead_turns": p["lead_turns"],
                    "expected": {
                        "no_price_before_quote": True,
                        "refused": elig,
                        "carencia_mentioned_when_quoted": not elig,
                    },
                }
            )

    stats = {
        "conversations": n_conv,
        "messages": n_msg,
        "quotable": quotable,
        "price_matches": matches,
        "refusable_any": refusable_any,
        "refusable_age": refusable_age,
        "refusable_vehicle": refusable_vehicle,
        "high_risk_cep": high_risk,
        "pii_messages": pii_msgs,
        "non_monotonic": non_mono,
        "franquia_antipattern": franquia_ap,
        "rever_antipattern": rever_ap,
        "coverage_wrong_superior": coverage_wrong_superior,
    }

    report = _render_report(
        ref_date,
        stats,
        outcomes,
        roles,
        types,
        ratios,
        underestimate,
        coverage_claim,
        price_for_refusable,
        pii_entities,
        convs_with,
        absent,
        len(cases),
        strata,
        args,
    )
    Path(args.out_report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_report).write_text(report, encoding="utf-8")
    Path(args.out_cases).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_cases).write_text(
        json.dumps(cases, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    leaked = find_pii(report) + find_pii(Path(args.out_cases).read_text(encoding="utf-8"))
    print(f"relatório: {args.out_report}\ncasos: {args.out_cases} ({len(cases)})")
    for k, v in stats.items():
        flag = (
            ""
            if not args.check
            else (" OK" if EXPECTED.get(k) == v else f" DIVERGE (esperado {EXPECTED.get(k)})")
        )
        print(f"  {k:26s} {v}{flag}")
    if leaked:
        print(f"PII NA SAÍDA: {leaked}")
        return 2
    if args.check and any(EXPECTED[k] != stats[k] for k in EXPECTED):
        return 1
    return 0


def _labels_in_masked(text: str) -> list[str]:
    return [
        lab
        for lab, marker in (
            ("cpf", "[CPF]"),
            ("email", "[EMAIL]"),
            ("telefone", "[TELEFONE]"),
            ("placa", "[PLACA]"),
        )
        if marker in text
    ]


def _render_report(
    ref_date,
    s,
    outcomes,
    roles,
    types,
    ratios,
    underestimate,
    coverage_claim,
    price_for_refusable,
    pii_entities,
    convs_with,
    absent,
    n_cases,
    strata,
    args,
) -> str:
    pct = lambda a, b: f"{100 * a / b:.1f}%"  # noqa: E731
    lines = [
        "# Relatório do dataset — `conversations.parquet`",
        "",
        f"Gerado por `scripts/analyze_dataset.py --ref-date {ref_date.isoformat()}`. Determinístico: os números",
        "abaixo são reproduzíveis por quem avalia. A data de referência fixa a idade do veículo.",
        "",
        "## 1. Volumetria",
        "",
        f"- {s['conversations']} conversas · {s['messages']} mensagens · {s['messages'] / s['conversations']:.2f} msgs/conversa",
        f"- desfechos: {outcomes}",
        f"- papéis: {roles} · tipos: {types}",
        f"- **timestamps não monótonos: {s['non_monotonic']} de {s['conversations']} ({pct(s['non_monotonic'], s['conversations'])})** → ordenar sempre por `message_index`",
        "",
        "## 2. O dataset NÃO é fonte de preço",
        "",
        f"Preço dito pelo vendedor × preço que a API devolve para o mesmo perfil ({s['quotable']} conversas cotáveis):",
        "",
        f"- **{s['price_matches']} de {s['quotable']} batem** ({pct(s['price_matches'], s['quotable'])})",
        f"- razão API/dataset: mín {min(ratios):.2f}x · mediana {statistics.median(ratios):.2f}x · máx {max(ratios):.2f}x",
        f"- o vendedor **subestima** em {pct(underestimate * len(ratios), len(ratios))} dos casos",
        f"- o vendedor cotou preço para **{price_for_refusable}** leads que a API **recusa**",
        "",
        "Conclusão: usar o dataset como few-shot de preço ensinaria o agente a errar. Ele serve para",
        "análise de padrões e para casos de avaliação — nunca como fonte de verdade de preço (BR-01).",
        "",
        "## 3. Elegibilidade de recusa (regras do `plans.json`)",
        "",
        f"- idade > 75: {s['refusable_age']} ({pct(s['refusable_age'], s['conversations'])})",
        f"- veículo > 20 anos em {ref_date.year}: {s['refusable_vehicle']} ({pct(s['refusable_vehicle'], s['conversations'])})",
        f"- **qualquer: {s['refusable_any']} ({pct(s['refusable_any'], s['conversations'])})** → skill `underwriting_refusal` (BR-12)",
        f"- CEP em região de agravo (prefixos 07/08/21/26/59): {s['high_risk_cep']} ({pct(s['high_risk_cep'], s['conversations'])})",
        "",
        "## 4. Anti-padrões do vendedor humano (o que o agente NÃO pode imitar)",
        "",
        f'- "Posso ajustar a franquia pra baixar a parcela": {s["franquia_antipattern"]} conversas ({pct(s["franquia_antipattern"], s["conversations"])}) → BR-05',
        f'- "Consigo rever, posso te ligar?": {s["rever_antipattern"]} ({pct(s["rever_antipattern"], s["conversations"])}) → BR-03/BR-07',
        f'- cobertura anunciada sempre como "colisao, roubo e furto": {coverage_claim} ({pct(coverage_claim, s["conversations"])}); '
        f"em {s['coverage_wrong_superior']} delas o plano era Completo/Premium, que cobre mais → BR-06",
        "",
        "## 5. PII",
        "",
        f"- mensagens com ao menos uma PII: {s['pii_messages']} de {s['messages']} ({pct(s['pii_messages'], s['messages'])})",
        f"- ocorrências por entidade (mensagens): {dict(pii_entities)}",
        f"- conversas com a entidade no texto do lead: {convs_with}",
        "",
        "## 6. Temas ausentes (0 = não existe exemplo para imitar; regras são autorais por necessidade)",
        "",
        *[f"- {k}: {v}" for k, v in absent.items()],
        "",
        "## 7. Casos de avaliação gerados",
        "",
        f"`{Path(args.out_cases).relative_to(ROOT)}`: {n_cases} casos, até {args.per_stratum} por estrato desfecho × elegibilidade de recusa "
        f"(seed {args.seed}). Estratos: {', '.join(f'{o}/{"recusa" if e else "cotável"}={len(v)}' for (o, e), v in sorted(strata.items()))}.",
        "Turnos do lead já sanitizados (CPF/e-mail/telefone/placa mascarados, CEP só prefixo).",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())

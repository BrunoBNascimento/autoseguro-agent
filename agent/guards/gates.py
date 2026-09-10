"""Gates de saída: quatro funções puras sobre o texto que o modelo produziu.

Rodam antes de o lead ver a resposta, sem LLM e sem rede. É o que transforma "o agente
não pode inventar preço" de uma frase no prompt em um invariante do sistema. Cada decisão
vira um evento `guard` no trace com o id da regra.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from agent.guards.money import Amount, extract_amounts
from agent.state import ConversationState

# ----------------------------------------------------------------------------- vocabulário

COVERAGE_VOCAB: dict[str, re.Pattern[str]] = {
    "colisao": re.compile(r"\bcolis(ao|oes)\b|\bbatida\b"),
    "roubo": re.compile(r"\broubo\b"),
    "furto": re.compile(r"\bfurto\b"),
    "terceiros": re.compile(r"\bterceiros?\b|\brcf\b"),
    "vidros": re.compile(r"\bvidros?\b|\bpara.?brisas?\b|\bparabrisa\b"),
    "carro_reserva": re.compile(r"\b(carro|veiculo)[ -]reserva\b"),
    "assistencia_24h": re.compile(r"\bassistencia\b|\bguincho\b|\breboque\b"),
}

# Benefícios que não existem em nenhum plano. Se o modelo citar como cobertura, inventou.
INVENTED_COVERAGE_RE = re.compile(
    r"\b(incendio|enchente|alagamento|granizo|fenomenos? da natureza|acessorios|som automotivo|"
    r"morte|invalidez|danos pessoais|\bapp\b|residencial|internacional|seguro de vida|"
    r"saude|dentista|pneu (gratis|de graca)|blindagem|rastreador (gratis|incluso))\b"
)

# Compromissos fora de autoridade. A negação dentro da janela anterior é respeitada.
AUTHORITY_PATTERNS: list[tuple[re.Pattern[str], tuple[str, ...]]] = [
    (
        re.compile(
            r"\b(te |lhe )?(dou|dar|da|consigo|posso|vou|podemos|conseguimos|faco|arrumo|libero|aplico|garanto|ofereco|tenho)\b.{0,30}\bdesconto"
        ),
        ("BR-04",),
    ),
    (
        re.compile(
            r"\bdesconto de \d|\d\s?% de desconto|\bcom desconto\b|\bdesconto (especial|exclusivo|pra voce|para voce)\b"
        ),
        ("BR-04",),
    ),
    (
        re.compile(
            r"\b(consigo|posso|vou|da pra|da para|dá pra|podemos|conseguimos)\b.{0,25}\b(baixar|reduzir|abaixar|melhorar|rever|negociar|ajustar|mexer|diminuir)\b"
        ),
        ("BR-03", "BR-05"),
    ),
    (
        re.compile(
            r"\bajust(ar|o|amos|e) a franquia\b|\bmex(er|o) na franquia\b|\bfranquia (menor|reduzida|zero)\b"
        ),
        ("BR-05",),
    ),
    (
        re.compile(r"\b(baix|reduz|diminu)\w* a (parcela|mensalidade|prestacao)\b"),
        ("BR-03", "BR-05"),
    ),
    (re.compile(r"\b(faco|fecho|deixo|saio) por\b|\bcubro a oferta\b|\bigualo\b"), ("BR-03",)),
    (
        re.compile(
            r"\bcondicao especial\b|\bpreco especial\b|\bvalor especial\b|\bcondicoes especiais\b"
        ),
        ("BR-05",),
    ),
    (
        re.compile(
            r"\bcortesia\b|\bgratis\b|\bde graca\b|\bbonus\b|\bbrinde\b|\bsem juros\b|\bisencao\b|\bcashback\b"
        ),
        ("BR-05", "BR-06"),
    ),
    (
        re.compile(
            r"\bvou ver o que (consigo|da|dá) (fazer|pra voce)\b|\bvejo o que (consigo|da) fazer\b"
        ),
        ("BR-05",),
    ),
    (
        re.compile(
            r"\bposso te ligar\b.{0,40}\b(rever|negociar|melhorar)|\b(rever|negociar|melhorar)\b.{0,40}\bposso te ligar"
        ),
        ("BR-03", "BR-05"),
    ),
]
_NEGATION_RE = re.compile(
    r"(\bnao\b|\bnem\b|\bsem\b|\bnunca\b|\bjamais\b|\binfelizmente\b|\bimpossivel\b|"
    r"\bfora da minha\b|\bnao esta\b|\bnao e possivel\b|\bnao tenho\b|\bnao posso\b|"
    r"\bnao consigo\b)[^.!?\n]{0,45}$"
)

HANDOFF_WORDING_RE = re.compile(
    r"\b(atendente|especialista|consultor|consultora|equipe|humano|humana|pessoa do time|"
    r"transferir|encaminhar|encaminhando|encaminho|encaminhei|repassar|passar (voce|sua conversa))\b"
)

PLAN_NAME_RE = re.compile(r"\b(essencial|completo|premium)\b")

# Trechos que só existem no prompt interno. Se aparecem na resposta, o modelo vazou.
DISCLOSURE_RE = re.compile(
    r"regras inviolaveis|<lead_message>|available_skills|skills? ativas neste turno|"
    r"\bskill `|\b(identity_and_scope|quote_failure|underwriting_refusal|objection_handling|"
    r"coverage_explanation|out_of_scope|model_selected|event_triggered|always_on)\b|"
    r"catalogo de skills|system prompt|prompt do sistema"
)


def _strip(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower()


# ----------------------------------------------------------------------------- resultado


@dataclass(frozen=True)
class Verdict:
    gate: str
    passed: bool
    rules: tuple[str, ...]
    reason: str = ""
    evidence: tuple[str, ...] = ()
    force_handoff: bool = False

    @property
    def status(self) -> str:
        return "pass" if self.passed else "blocked"


@dataclass
class GateReport:
    verdicts: list[Verdict] = field(default_factory=list)

    @property
    def blocked(self) -> list[Verdict]:
        return [v for v in self.verdicts if not v.passed]

    @property
    def passed(self) -> bool:
        return not self.blocked

    @property
    def rules(self) -> list[str]:
        out: list[str] = []
        for v in self.blocked:
            for r in v.rules:
                if r not in out:
                    out.append(r)
        return out

    @property
    def force_handoff(self) -> bool:
        return any(v.force_handoff for v in self.blocked)

    def correction_hint(self) -> str:
        lines = []
        for v in self.blocked:
            lines.append(f"- {v.gate} ({', '.join(v.rules)}): {v.reason}")
        return "\n".join(lines)


# ----------------------------------------------------------------------------- gates


def catalog_franquias(catalog: Mapping[str, Any] | None) -> frozenset[float]:
    if not catalog:
        return frozenset()
    return frozenset(round(float(p["franquia"]), 2) for p in catalog.get("planos", []))


def price_gate(
    draft: str, state: ConversationState, catalog: Mapping[str, Any] | None = None
) -> Verdict:
    amounts: list[Amount] = extract_amounts(draft)
    if not amounts:
        return Verdict("price_gate", True, ("BR-01",))
    allowed: set[float] = set(catalog_franquias(catalog))
    if state.last_quote is not None:
        allowed |= set(state.last_quote.allowed_amounts)
    offending = [a for a in amounts if not any(abs(a.value - v) < 0.005 for v in allowed)]
    if not offending:
        return Verdict("price_gate", True, ("BR-01",), evidence=tuple(a.raw for a in amounts))
    evidence = tuple(a.raw for a in offending)
    if state.last_quote is None:
        return Verdict(
            "price_gate",
            False,
            ("BR-02", "BR-01"),
            "valor monetário sem cotação bem-sucedida nesta conversa; não cite nem estime valores",
            evidence,
        )
    return Verdict(
        "price_gate",
        False,
        ("BR-03", "BR-01"),
        "valor diferente do devolvido pela cotação; use exatamente os valores da última cotação",
        evidence,
    )


def coverage_gate(
    draft: str, state: ConversationState, catalog: Mapping[str, Any] | None = None
) -> Verdict:
    t = _strip(draft)
    invented = [m.group(0) for m in INVENTED_COVERAGE_RE.finditer(t)]
    if invented:
        return Verdict(
            "coverage_gate",
            False,
            ("BR-06",),
            "cobertura/benefício que não existe em nenhum plano",
            tuple(dict.fromkeys(invented)),
        )
    mentioned = {cov for cov, rx in COVERAGE_VOCAB.items() if rx.search(t)}
    if not mentioned:
        return Verdict("coverage_gate", True, ("BR-06",))

    plans = {p["id"]: set(p.get("coberturas", [])) for p in (catalog or {}).get("planos", [])}
    named = set(PLAN_NAME_RE.findall(t))
    allowed: set[str] = set()
    for plan_id in named:
        allowed |= plans.get(plan_id, set())
    if state.last_quote is not None:
        allowed |= set(state.last_quote.coberturas)
    if not named and state.last_quote is None:
        # explicação geral, sem plano cotado: o vocabulário fechado já limita ao catálogo
        for covers in plans.values():
            allowed |= covers
        if not plans:
            allowed = set(COVERAGE_VOCAB)
    extra = sorted(mentioned - allowed)
    if extra:
        return Verdict(
            "coverage_gate",
            False,
            ("BR-06", "BR-05"),
            "cobertura citada não pertence ao plano cotado nem a um plano nomeado na resposta",
            tuple(extra),
        )
    return Verdict("coverage_gate", True, ("BR-06",), evidence=tuple(sorted(mentioned)))


def authority_gate(draft: str, state: ConversationState) -> Verdict:
    t = _strip(draft)
    hits: list[str] = []
    rules: list[str] = []
    for rx, rule_ids in AUTHORITY_PATTERNS:
        for m in rx.finditer(t):
            prefix = t[max(0, m.start() - 60) : m.start()]
            if _NEGATION_RE.search(prefix):
                continue
            hits.append(m.group(0))
            for r in rule_ids:
                if r not in rules:
                    rules.append(r)
    if not hits:
        return Verdict("authority_gate", True, ("BR-04", "BR-05"))
    if "BR-08" not in rules:
        rules.append("BR-08")
    return Verdict(
        "authority_gate",
        False,
        tuple(rules),
        "compromisso fora de autoridade (desconto, alteração de preço/franquia ou condição especial)",
        tuple(dict.fromkeys(hits)),
        force_handoff=True,
    )


def handoff_gate(draft: str, state: ConversationState) -> Verdict:
    rule = state.handoff_rule or "BR-08"
    if not state.handoff_required:
        return Verdict("handoff_gate", True, (rule,))
    if HANDOFF_WORDING_RE.search(_strip(draft)):
        return Verdict("handoff_gate", True, (rule,))
    return Verdict(
        "handoff_gate",
        False,
        (rule,),
        "encaminhamento para atendente humano é obrigatório neste ponto; a resposta não encaminha",
    )


def disclosure_gate(draft: str, state: ConversationState) -> Verdict:
    hits = [m.group(0) for m in DISCLOSURE_RE.finditer(_strip(draft))]
    if not hits:
        return Verdict("disclosure_gate", True, ("SEC-01",))
    return Verdict(
        "disclosure_gate",
        False,
        ("SEC-01",),
        "a resposta expõe instruções internas, catálogo ou nomes de skills",
        tuple(dict.fromkeys(hits)),
    )


def run_gates(
    draft: str, state: ConversationState, catalog: Mapping[str, Any] | None = None
) -> GateReport:
    return GateReport(
        [
            price_gate(draft, state, catalog),
            coverage_gate(draft, state, catalog),
            authority_gate(draft, state),
            handoff_gate(draft, state),
            disclosure_gate(draft, state),
        ]
    )

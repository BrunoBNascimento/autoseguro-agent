"""Handoff para atendimento humano: gatilhos determinísticos e payload útil para quem assume.

| Gatilho                              | Regra |
|--------------------------------------|-------|
| lead pede humano                     | BR-09 |
| cotação falhou definitivamente       | BR-10 |
| negociação / exceção / desconto      | BR-08 |
| defeito interno (400, 422 ambíguo)   | BR-08 |
| fora de escopo                       | BR-11 |
| injection reincidente                | BR-11 |

Recusa de subscrição NÃO é handoff (BR-12): é regra dura da seguradora, sem o que negociar.
"""

from __future__ import annotations

import re
import unicodedata

from agent.security.pii import Policy, sanitize_obj
from agent.state import ConversationState, HandoffPayload

TRIGGER_RULES: dict[str, str] = {
    "human_request": "BR-09",
    "quote_failed_definitively": "BR-10",
    "breaker_open_insist": "BR-10",
    "authority": "BR-08",
    "internal_defect": "BR-08",
    "negotiation": "BR-08",
    "out_of_scope": "BR-11",
    "injection_repeated": "BR-11",
}

TRIGGER_LABELS: dict[str, str] = {
    "human_request": "lead pediu atendimento humano",
    "quote_failed_definitively": "cotação falhou definitivamente",
    "breaker_open_insist": "sistema de cotação indisponível e lead insistiu",
    "authority": "pedido fora da autoridade do agente (desconto/condição)",
    "internal_defect": "defeito interno na cotação",
    "negotiation": "situação exige negociação",
    "out_of_scope": "assunto fora do escopo",
    "injection_repeated": "tentativas repetidas de manipular o agente",
}

_HUMAN_RE = re.compile(
    r"\b(atendente|humano|humana|pessoa (de verdade|real|fisica)|alguem (de verdade|da equipe|"
    r"de vendas)|falar com (alguem|uma pessoa|um humano|o gerente|um gerente|o supervisor|"
    r"um consultor|um vendedor|um atendente|a equipe|um responsavel)|"
    r"quero (um|o|a) (vendedor|consultor|gerente|atendente|supervisor)|"
    r"(chama|passa|transfere) (pro|para o|pra o|ao) (gerente|supervisor|atendente)|"
    r"me (liga|ligue|ligar|chama no telefone)|robo nao|nao quero falar com (robo|bot|maquina)|"
    r"chatbot nao|transfere|transferir)\b"
)

_NEGOTIATION_RE = re.compile(
    r"\b(desconto|abate|abatimento|baixa(r)? (o|esse) (preco|valor)|melhora(r)? (o|esse) (preco|valor)|"
    r"negocia(r)?|condicao (especial|melhor)|faz (por|mais barato)|chega (mais|nos) \d|"
    r"cobre a oferta|iguala|parcela(r)? sem juros|tira(r)? a franquia|reduz(ir)? a franquia)\b"
)


def _strip(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower()


def detect_human_request(text: str) -> bool:
    return bool(_HUMAN_RE.search(_strip(text)))


def detect_negotiation_request(text: str) -> bool:
    """Pedido explícito de desconto/negociação. Não é handoff imediato: a skill de objeção
    responde uma vez com valor; só a insistência ou o compromisso do modelo encaminha."""
    return bool(_NEGOTIATION_RE.search(_strip(text)))


def build_payload(state: ConversationState, trigger: str, skills_used: list[str]) -> HandoffPayload:
    rule = TRIGGER_RULES.get(trigger, "BR-08")
    reason = TRIGGER_LABELS.get(trigger, trigger)
    collected = sanitize_obj(dict(state.collected), Policy.PERSISTENCE)
    quote_part = (
        f"última cotação {state.last_quote.plano_id} a {state.last_quote.premio_mensal:.2f}/mês"
        if state.last_quote
        else f"sem cotação bem-sucedida (status: {state.last_quote_status or 'nenhuma tentativa'})"
    )
    summary = f"{reason}; {quote_part}; {len(state.quote_attempt_log)} tentativa(s) de cotação registradas"
    return HandoffPayload(
        conversation_id=state.conversation_id,
        rule_id=rule,
        reason=reason,
        summary=summary,
        collected=collected,
        quote_attempts=[dict(a) for a in state.quote_attempt_log],
        skills_used=list(skills_used),
    )

"""Catálogo de skills e seleção híbrida.

Skills são arquivos markdown com front-matter YAML em `skills/`. Nenhuma regra comercial
vive em `.py`. O catálogo (`menu`) é montado só do front-matter e fica sempre no contexto;
os corpos entram apenas quando selecionados.

Seleção híbrida:
- `always_on` e `event_triggered` são decididas por CÓDIGO — o modelo não tem voto. Se o
  breaker está aberto, `quote_failure` entra, independentemente da intenção detectada.
- `model_selected` é escolhida pelo modelo (ou pelo roteador de fallback) pela intenção.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from agent.rules import rule_ids

Activation = Literal["always_on", "model_selected", "event_triggered"]
ACTIVATIONS: tuple[str, ...] = ("always_on", "model_selected", "event_triggered")
KNOWN_EVENTS: frozenset[str] = frozenset(
    {"quote_retries_exhausted", "breaker_open", "quote_refused", "handoff_required"}
)

_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


class SkillConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    activation: Activation
    when_to_use: str
    body: str
    path: str
    triggers: tuple[str, ...] = ()
    excludes: tuple[str, ...] = ()
    rules: tuple[str, ...] = ()
    priority: int = 100
    fallback_template: str | None = None

    def menu_line(self) -> str:
        return f"- `{self.id}`: {self.when_to_use}"

    def render(self) -> str:
        return f"### Skill `{self.id}` — {self.name}\n{self.body.strip()}\n"


@dataclass
class Selection:
    skills: list[Skill]
    selected_by: dict[str, str] = field(default_factory=dict)
    excluded: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)

    @property
    def ids(self) -> list[str]:
        return [s.id for s in self.skills]

    @property
    def rules(self) -> list[str]:
        seen: list[str] = []
        for s in self.skills:
            for r in s.rules:
                if r not in seen:
                    seen.append(r)
        return seen

    def render_bodies(self) -> str:
        return "\n".join(s.render() for s in self.skills)


def parse_skill_file(path: Path, valid_rules: frozenset[str]) -> Skill:
    text = path.read_text(encoding="utf-8")
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        raise SkillConfigError(f"{path}: front-matter YAML ausente (bloco entre '---')")
    try:
        meta: dict[str, Any] = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise SkillConfigError(f"{path}: front-matter inválido: {exc}") from exc
    body = match.group(2)

    for key in ("id", "name", "activation", "when_to_use"):
        if not meta.get(key):
            raise SkillConfigError(f"{path}: campo obrigatório '{key}' ausente")
    if meta["activation"] not in ACTIVATIONS:
        raise SkillConfigError(
            f"{path}: activation '{meta['activation']}' inválida; use {ACTIVATIONS}"
        )
    if str(meta["id"]) != path.stem:
        raise SkillConfigError(f"{path}: id '{meta['id']}' difere do nome do arquivo")

    triggers = tuple(str(t) for t in (meta.get("triggers") or []))
    if meta["activation"] == "event_triggered" and not triggers:
        raise SkillConfigError(f"{path}: skill event_triggered precisa de 'triggers'")
    unknown_events = set(triggers) - KNOWN_EVENTS
    if unknown_events:
        raise SkillConfigError(f"{path}: triggers desconhecidos {sorted(unknown_events)}")

    rules = tuple(str(r) for r in (meta.get("rules") or []))
    unknown_rules = set(rules) - valid_rules
    if unknown_rules:
        raise SkillConfigError(f"{path}: rules desconhecidas {sorted(unknown_rules)}")

    if not body.strip():
        raise SkillConfigError(f"{path}: corpo vazio")

    return Skill(
        id=str(meta["id"]),
        name=str(meta["name"]),
        activation=meta["activation"],
        when_to_use=str(meta["when_to_use"]).strip(),
        body=body,
        path=str(path),
        triggers=triggers,
        excludes=tuple(str(x) for x in (meta.get("excludes") or [])),
        rules=rules,
        priority=int(meta.get("priority", 100)),
        fallback_template=(
            str(meta["fallback_template"]).strip() if meta.get("fallback_template") else None
        ),
    )


class SkillCatalog:
    def __init__(self, skills: Iterable[Skill]):
        self._skills: dict[str, Skill] = {}
        for skill in skills:
            if skill.id in self._skills:
                raise SkillConfigError(f"skill duplicada: {skill.id}")
            self._skills[skill.id] = skill
        for skill in self._skills.values():
            for other in skill.excludes:
                if other not in self._skills:
                    raise SkillConfigError(
                        f"{skill.path}: excludes referencia '{other}' inexistente"
                    )

    @classmethod
    def load(cls, directory: Path | str = "skills") -> SkillCatalog:
        directory = Path(directory)
        rules_path = directory / "business_rules.yaml"
        valid_rules = rule_ids(rules_path) if rules_path.exists() else rule_ids()
        files = sorted(directory.glob("*.md"))
        if not files:
            raise SkillConfigError(f"nenhuma skill (*.md) em {directory}")
        return cls(parse_skill_file(p, valid_rules) for p in files)

    # ------------------------------------------------------------------ consulta
    def __len__(self) -> int:
        return len(self._skills)

    def ids(self) -> list[str]:
        return list(self._skills)

    def get(self, skill_id: str) -> Skill:
        return self._skills[skill_id]

    def all(self) -> list[Skill]:
        return list(self._skills.values())

    def model_selectable_ids(self) -> list[str]:
        return [s.id for s in self._skills.values() if s.activation == "model_selected"]

    def menu(self) -> str:
        """`available_skills`: só front-matter, nenhum corpo."""
        lines = [s.menu_line() for s in sorted(self._skills.values(), key=lambda s: s.id)]
        return "\n".join(lines)

    # ------------------------------------------------------------------ seleção
    def select(self, events: Iterable[str] = (), model_choice: Iterable[str] = ()) -> Selection:
        events_set = set(events)
        choice = [c for c in model_choice if c in self._skills]
        selected_by: dict[str, str] = {}

        for skill in self._skills.values():
            if skill.activation == "always_on":
                selected_by[skill.id] = "always_on"
            elif skill.activation == "event_triggered" and events_set.intersection(skill.triggers):
                selected_by[skill.id] = "event"
        for skill_id in choice:
            skill = self._skills[skill_id]
            if skill.activation == "model_selected" and skill_id not in selected_by:
                selected_by[skill_id] = "model"

        # Exclusões só valem vindas de skills decididas por código: o modelo não desliga
        # uma skill de evento escolhendo outra.
        excluded: list[str] = []
        for skill_id, by in list(selected_by.items()):
            if by in ("always_on", "event"):
                for other in self._skills[skill_id].excludes:
                    if other in selected_by and selected_by[other] == "model":
                        excluded.append(other)
        for other in excluded:
            selected_by.pop(other, None)

        skills = sorted((self._skills[i] for i in selected_by), key=lambda s: (-s.priority, s.id))
        return Selection(skills, selected_by, excluded, sorted(events_set))

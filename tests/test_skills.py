import re
from pathlib import Path

import pytest

from agent.rules import load_rules
from agent.skills import SkillCatalog, SkillConfigError, parse_skill_file

SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"


@pytest.fixture(scope="module")
def catalog() -> SkillCatalog:
    return SkillCatalog.load(SKILLS_DIR)


def test_catalogo_tem_as_oito_skills(catalog):
    assert set(catalog.ids()) == {
        "identity_and_scope",
        "quote",
        "quote_failure",
        "underwriting_refusal",
        "objection_handling",
        "coverage_explanation",
        "handoff",
        "out_of_scope",
    }


def test_menu_so_usa_front_matter(catalog):
    menu = catalog.menu()
    for skill in catalog.all():
        assert skill.id in menu and skill.when_to_use in menu
        # nenhuma linha do corpo aparece no menu
        first_body_line = next(ln for ln in skill.body.strip().splitlines() if ln.strip())
        assert first_body_line.strip() not in menu
    assert len(menu) < 2500


def test_so_corpos_selecionados_entram(catalog):
    sel = catalog.select(events=(), model_choice=["quote"])
    text = sel.render_bodies()
    assert "Skill `quote`" in text and "Skill `identity_and_scope`" in text
    assert "Skill `objection_handling`" not in text
    assert "Skill `handoff`" not in text


def test_breaker_open_forca_quote_failure_mesmo_com_modelo_escolhendo_quote(catalog):
    sel = catalog.select(events={"breaker_open"}, model_choice=["quote"])
    assert "quote_failure" in sel.ids
    assert "quote" not in sel.ids and sel.excluded == ["quote"]
    assert sel.selected_by["quote_failure"] == "event"


def test_recusa_ativa_underwriting_refusal_e_remove_quote(catalog):
    sel = catalog.select(events={"quote_refused"}, model_choice=["quote", "objection_handling"])
    assert "underwriting_refusal" in sel.ids and "quote" not in sel.ids
    assert "objection_handling" in sel.ids


def test_handoff_exclui_skills_de_venda(catalog):
    sel = catalog.select(events={"handoff_required"}, model_choice=["quote", "objection_handling"])
    assert sel.ids[:2] == ["identity_and_scope", "handoff"]
    assert set(sel.excluded) == {"quote", "objection_handling"}


def test_modelo_nao_consegue_ativar_skill_de_evento(catalog):
    sel = catalog.select(events=(), model_choice=["handoff", "quote_failure", "quote"])
    assert "handoff" not in sel.ids and "quote_failure" not in sel.ids and "quote" in sel.ids


def test_regras_referenciadas_existem(catalog):
    rules = load_rules(SKILLS_DIR / "business_rules.yaml")
    assert set(rules) == {f"BR-{i:02d}" for i in range(1, 15)} | {"SEC-01"}
    for skill in catalog.all():
        assert skill.rules and set(skill.rules) <= set(rules)


def test_skills_de_evento_tem_template_de_fallback(catalog):
    for sid in ("quote_failure", "underwriting_refusal", "handoff", "out_of_scope"):
        assert catalog.get(sid).fallback_template


def test_nova_skill_aparece_sem_tocar_em_python(tmp_path):
    for p in SKILLS_DIR.glob("*"):
        (tmp_path / p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "renovacao.md").write_text(
        "---\nid: renovacao\nname: Renovação\nactivation: model_selected\n"
        'when_to_use: "O lead quer renovar."\nrules: [BR-01]\n---\n## Corpo\nfaça x\n',
        encoding="utf-8",
    )
    cat = SkillCatalog.load(tmp_path)
    assert "renovacao" in cat.ids() and "`renovacao`" in cat.menu()


@pytest.mark.parametrize(
    "content,msg",
    [
        ("## sem front matter\n", "front-matter"),
        ("---\nid: x\nname: X\nactivation: sempre\nwhen_to_use: y\n---\ncorpo\n", "activation"),
        (
            "---\nid: x\nname: X\nactivation: event_triggered\nwhen_to_use: y\n---\ncorpo\n",
            "triggers",
        ),
        (
            "---\nid: x\nname: X\nactivation: model_selected\nwhen_to_use: y\nrules: [BR-99]\n---\ncorpo\n",
            "rules",
        ),
        ("---\nid: y\nname: X\nactivation: model_selected\nwhen_to_use: y\n---\ncorpo\n", "difere"),
        ("---\nid: x\nname: X\nactivation: model_selected\nwhen_to_use: y\n---\n", "vazio"),
    ],
)
def test_front_matter_invalido_falha_no_boot_com_mensagem_clara(tmp_path, content, msg):
    p = tmp_path / "x.md"
    p.write_text(content, encoding="utf-8")
    with pytest.raises(SkillConfigError, match=msg):
        parse_skill_file(p, frozenset({"BR-01"}))


def test_nenhuma_regra_comercial_em_python():
    """Vocabulário de regra comercial só pode aparecer nos gates (como padrão a detectar).
    `franquia`/`premio_mensal` como nome de campo do payload da API não contam: é schema."""
    root = Path(__file__).resolve().parents[1] / "agent"
    pattern = re.compile(
        r"desconto|ajustar a franquia|baixar a parcela|car[êe]ncia de|dias de car[êe]ncia|"
        r"R\$\s?\d|condi[çc][ãa]o especial|\b\d{2,3}[.,]90\b",
        re.IGNORECASE,
    )
    offenders = []
    # vocabulário de DETECÇÃO (gates, handoff, injection, roteador) reconhece intenção;
    # não decide o que a empresa oferece. Tudo o mais tem que estar limpo.
    detection = {"guards", "handoff.py", "injection.py", "router.py"}
    for py in root.rglob("*.py"):
        if detection & set(py.parts):
            continue
        for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{py.relative_to(root)}:{i}: {line.strip()}")
    assert offenders == [], "\n".join(offenders)

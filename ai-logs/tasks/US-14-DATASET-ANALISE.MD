# US-14 — Script de análise do dataset

**Prioridade:** MUST (pequeno) · **Estimativa:** 1,5h · **Dia:** 1 · **Depende de:** US-01 · **Habilita:** US-12

## Contexto
A análise **já foi feita** no discovery e está toda em `DISCOVERY.MD §5`. Esta US **produtiza**
o script, para que os números do README sejam reproduzíveis por quem avalia — e não uma
afirmação nossa.

Achado que viabiliza tudo: `gen_conversation(0, seed=42)` reproduz `dataset/sample.jsonl`
**campo por campo**, então dá para calcular ground truth exato.

## Escopo
`scripts/analyze_dataset.py` (uv script header, `pandas` + `pyarrow`), reproduzindo:

- Volumetria: 2.500 conversas, 26.470 mensagens, 10,59 msgs/conversa; desfechos; papéis.
- **Preço dataset × preço da API** via `quote_logic.cotar()`: **0 de 1.749 batem**;
  razão real/dataset min 0,31x, mediana 1,45x, max 7,89x; 71% subestimam.
- **Anti-padrões do vendedor:** `"ajustar a franquia"` 757 (30%), `"Consigo rever"` 538 (22%),
  cobertura errada 2.500 (100%, das quais 1.677 em Completo/Premium).
- **Elegibilidade de recusa:** idade > 75 ⇒ 280 (11,2%); veículo > 20a ⇒ 531 (21,2%);
  **qualquer ⇒ 751 (30,0%)**.
- CEP de alto risco: 895 (35,8%).
- PII por entidade e por mensagem (4.718 de 26.470 = 17,8%).
- **Timestamp não monótono: 2.495 de 2.500 (99,8%)** — assertivo, com aviso explícito.
- Temas ausentes (carência, pro-rata, coberturas superiores, agravo, handoff, injection): todos **0**.
- Saída: `evals/dataset_report.md` + `evals/cases/` com os casos estratificados para US-12.

## Critérios de aceitação
- [ ] `make analyze` roda e reproduz os números de `DISCOVERY.MD §5` (tolerância zero — é determinístico)
- [ ] Lê o parquet **ordenando por `message_index`**, com asserção que detecta o não monotonismo dos timestamps
- [ ] Gera casos estratificados por desfecho **e** por elegibilidade de recusa
- [ ] Roda com `uv run` sem venv manual
- [ ] O relatório afirma explicitamente que o dataset **não** é fonte de preço, com os números
- [ ] Nenhuma PII no relatório de saída

## Notas
`dt.date.today()` na regra de idade do veículo (I-06) torna os números sensíveis ao ano
corrente. **Fixar a data de referência** (`--ref-date 2026-09-10`) para que o relatório seja
reproduzível em 2027 (R-10).

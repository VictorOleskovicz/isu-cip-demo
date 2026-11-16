# PLAN-1 — Ingestão SAP IS-U para a Contribuição de Iluminação Pública (CIP)

## Fontes

- SPEC: `.data-eng/specs/SPEC-1.md`
- Guidelines: `.data-eng/guidelines/GENERAL.md`, `.data-eng/guidelines/CODING.md`, `.data-eng/guidelines/ENV.md`, `.data-eng/guidelines/LAYERS.md`
- Configuração: `databricks.yml`
- Gabarito do cálculo (dados fictícios): `dados_ficticios/esperado_cip.csv`
- Planos e outputs anteriores: nenhum.

## Padrões fundamentais

- **Determinismo**: silver sempre por `src/notebooks/ingest_cdc.py`; dimensão gold por
  `src/notebooks/transform_gold.py` + `scd_type1.py`. Código novo só na exceção (regra de negócio
  da OBT), partindo de `transform_gold.py` com alteração mínima.
- **Base de conhecimento**: tabelas que constam na KB são copiadas com `kb.py copy`, nunca regeradas.
- **Estado local como fonte de verdade**: um YAML por tabela em `schemas/<camada>/`; o Unity
  Catalog deve refleti-lo (`validate_state.py` sem diff).
- **Contratos**: toda tabela com comentário e chave primária; toda coluna com comentário e PII.
- **Incremental e idempotente**: watermark `_ingerido_em` e MERGE pela chave; reexecutar não
  altera contagens nem valores.
- **Configuração**: catálogo, schemas e warehouse vêm de `databricks.yml`; nada hardcoded.
- **Evidências**: registrar em `.data-eng/outputs/PLAN-1_OUT.md`, na linha de cada item.
- Artefatos em PT-BR. Compute serverless.

## Mapa de fases

| Fase | Entrega | Bloqueia |
|------|---------|----------|
| 1. Bronze | Estado local da bronze copiado da KB e contratos aplicados no UC (`specs/SPEC-1.md#bronze-modelo-fonte`) | 2 |
| 2. Silver | Estado local e tabelas silver carregadas pelo CDC (`specs/SPEC-1.md#silver-idêntico-à-fonte-limpo`) | 3 |
| 3. Gold | Estado local e tabelas gold: dimensão e OBT (`specs/SPEC-1.md#gold-modelo-destino`) | 4 |
| 4. Orquestração | Bundle e job serverless bronze → silver → gold | 5 |
| 5. Validação end-to-end | Job executado, idempotência e conferência com o gabarito | — |

## Fase 1 — Bronze

**Objetivo**: ter o estado local da bronze idêntico à KB (mais o ajuste do projeto) e o Unity
Catalog aderente aos contratos, sem recriar tabelas nem recarregar dados.

Tarefas:

- [ ] Copiar da KB, com `kb.py copy`, os YAMLs de `eanl`, `eanlh`, `ekon`, `ekong` e `ekonh` para `schemas/bronze/` (`specs/SPEC-1.md#bronze-modelo-fonte`).
- [ ] Aplicar o ajuste incremental `_ingerido_em` nos cinco YAMLs (`specs/SPEC-1.md#bronze-modelo-fonte`).
- [ ] Aplicar no UC, nas tabelas bronze existentes, os contratos: comentário de tabela e colunas, chave primária, não-nulidade das chaves e tag de PII.

Critérios de sucesso:

- [ ] Os cinco arquivos de `schemas/bronze/` diferem dos da KB apenas pela coluna `_ingerido_em`.
- [ ] `validate_state.py --layer bronze` termina sem diff.
- [ ] Contagem de linhas da bronze inalterada: `eanl` 31, `eanlh` 33, `ekon` 8, `ekong` 10, `ekonh` 1.

Referências: [Constraints](https://docs.databricks.com/aws/en/tables/constraints) · [Tags](https://docs.databricks.com/aws/en/database-objects/tags)

## Fase 2 — Silver

**Objetivo**: materializar as cinco tabelas silver pelo CDC determinístico, limpas e sem
duplicidade.

Tarefas:

- [ ] Criar os YAMLs de `instalacoes`, `instalacoes_historico`, `contratos_concessao`, `concessao_precos` e `concessao_limites` em `schemas/silver/` (`specs/SPEC-1.md#silver-idêntico-à-fonte-limpo`).
- [ ] Executar `ingest_cdc.py` para cada tabela, sem alterar o código (`specs/SPEC-1.md#transformações-da-ingestão-silver`).
- [ ] Aplicar os contratos de coluna, chave primária e PII nas tabelas silver.

Critérios de sucesso:

- [ ] `validate_state.py --layer silver` termina sem diff.
- [ ] Contagens: `instalacoes` 30, `instalacoes_historico` 33, `contratos_concessao` 8, `concessao_precos` 10, `concessao_limites` 1.
- [ ] `instalacoes` sem chave duplicada e sem valor de texto com espaço no início ou no fim.
- [ ] `src/notebooks/ingest_cdc.py` idêntico ao template do plugin.
- [ ] Reexecutar a ingestão não altera as contagens.

Referências: [MERGE](https://docs.databricks.com/aws/en/delta/merge)

## Fase 3 — Gold

**Objetivo**: materializar a dimensão de contratos de concessão e a OBT de CIP esperada.

Tarefas:

- [ ] Criar `schemas/gold/dim_concessao.yaml` e materializar a dimensão SCD Tipo 1 (`specs/SPEC-1.md#dim_concessao--dimensão-scd-tipo-1`).
- [ ] Criar `schemas/gold/cip_esperada_prefeitura_mes.yaml` (`specs/SPEC-1.md#cip_esperada_prefeitura_mes--obt-transformação-custom`).
- [ ] Implementar as regras de negócio da OBT em notebook próprio, derivado de `transform_gold.py` com alteração mínima (`specs/SPEC-1.md#transformações-da-ingestão-gold`).
- [ ] Aplicar os contratos de coluna, chave primária e PII nas tabelas gold.

Critérios de sucesso:

- [ ] `validate_state.py --layer gold` termina sem diff.
- [ ] `dim_concessao` com 8 linhas e `sk_concessao` único.
- [ ] `cip_esperada_prefeitura_mes` com 72 linhas, sem chave duplicada, e sem contrato de `tipo_calculo` diferente de `FIXO`.
- [ ] Soma de `valor_cip_esperado` igual a 3798,00.
- [ ] Reexecutar a transformação não altera contagens, valores nem `sk_concessao`.

Referências: [MERGE](https://docs.databricks.com/aws/en/delta/merge)

## Fase 4 — Orquestração

**Objetivo**: encadear silver e gold em um job serverless implantado por bundle.

Tarefas:

- [ ] Atualizar `resources/etl.job.yml`: uma tarefa por tabela silver e gold, com dependências silver → gold, parametrizadas por `${var.*}`.
- [ ] Validar e implantar o bundle no target `dev`.

Critérios de sucesso:

- [ ] `databricks bundle validate` sem erros.
- [ ] Job implantado, serverless, com 5 tarefas silver e 2 gold e as dependências corretas.
- [ ] Nenhum catálogo ou schema hardcoded em `resources/` e `src/`.

Referências: [Bundles](https://docs.databricks.com/aws/en/dev-tools/bundles/) · [Jobs serverless](https://docs.databricks.com/aws/en/jobs/run-serverless-jobs)

## Fase 5 — Validação end-to-end

**Objetivo**: comprovar que o job roda de ponta a ponta, é idempotente e produz o resultado do gabarito.

Tarefas:

- [ ] Executar o job implantado duas vezes seguidas.
- [ ] Comparar `cip_esperada_prefeitura_mes` com `dados_ficticios/esperado_cip.csv`, linha a linha.
- [ ] Rodar `validate_state.py` em todas as camadas.

Critérios de sucesso:

- [ ] As duas execuções terminam com sucesso em todas as tarefas.
- [ ] Contagens e valores idênticos entre a primeira e a segunda execução.
- [ ] Zero divergências contra o gabarito nas 72 linhas (`cod_concessao`, `mes_referencia`, `cod_parceiro_prefeitura`, `qtd_instalacoes_ativas`, `valor_cip_esperado`).
- [ ] Totais por prefeitura: 9000000001 = 1269,00; 9000000002 = 1635,00; 9000000003 = 894,00.
- [ ] `validate_state.py` sem diff nas três camadas.

## Fora de escopo

- Contratos percentuais (`vertart = 'PERC'`) e preços por escalão de consumo (`kavon`/`kabis`).
- Aplicação dos limites de `concessao_limites` no cálculo.
- Linhas de fatura e comparação entre CIP esperada e CIP faturada.
- Rateio proporcional quando a instalação troca de contrato no meio do mês (vale o dia 1º).
- Metric View, Genie space, Data Classification e Quality Monitor.
- Ingestão do SAP para a bronze.

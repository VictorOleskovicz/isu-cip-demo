# PLAN-1_OUT — Estado da execução

Plano: `.data-eng/plans/PLAN-1.md` · SPEC: `.data-eng/specs/SPEC-1.md`

## Fase 1 — Bronze

Tarefas:

- [X] Copiar da KB, com `kb.py copy`, os YAMLs de `eanl`, `eanlh`, `ekon`, `ekong` e `ekonh` para `schemas/bronze/` (`specs/SPEC-1.md#bronze-modelo-fonte`). — schemas/bronze/*.yaml via kb.py copy
- [X] Aplicar o ajuste incremental `_ingerido_em` nos cinco YAMLs (`specs/SPEC-1.md#bronze-modelo-fonte`). — bloco `_ingerido_em` (timestamp, not null, pii nenhum) no fim de `colunas`
- [X] Aplicar no UC, nas tabelas bronze existentes, os contratos: comentário de tabela e colunas, chave primária, não-nulidade das chaves e tag de PII. — workspace.isu_bronze.*: COMMENT, ALTER COLUMN COMMENT, SET TAGS ('pii'=…) em todas as colunas, SET NOT NULL, pk_<t> PRIMARY KEY NOT ENFORCED. Aprendizado: tag `pii`; PK exige SET NOT NULL antes; coluna só no UC gera diff → silver deve declarar `_ingerido_em`; tipos comparados em minúsculas sem espaço

Critérios de sucesso:

- [X] Os cinco arquivos de `schemas/bronze/` diferem dos da KB apenas pela coluna `_ingerido_em`. — diff KB×local só o bloco `_ingerido_em`
- [X] `validate_state.py --layer bronze` termina sem diff. — SEM DIFF (exit 0)
- [X] Contagem de linhas da bronze inalterada: `eanl` 31, `eanlh` 33, `ekon` 8, `ekong` 10, `ekonh` 1. — 31/33/8/10/1

## Fase 2 — Silver

Tarefas:

- [X] Criar os YAMLs de `instalacoes`, `instalacoes_historico`, `contratos_concessao`, `concessao_precos` e `concessao_limites` em `schemas/silver/` (`specs/SPEC-1.md#silver-idêntico-à-fonte-limpo`). — schemas/silver/*.yaml: corpo idêntico à bronze (inclui `_ingerido_em`), `fonte: bronze.<t>`, `watermark: _ingerido_em`
- [X] Executar `ingest_cdc.py` para cada tabela, sem alterar o código (`specs/SPEC-1.md#transformações-da-ingestão-silver`). — one-off serverless (jobs submit), runs 734929538367327 e 595706190179296; notebook+YAMLs em /Workspace/Users/<user>/.oneoff/isu-cip-demo-fase2/; `caminho_estado` = arquivo do workspace lido por open(); PyYAML já disponível no serverless
- [X] Aplicar os contratos de coluna, chave primária e PII nas tabelas silver. — SQL gerado dos YAMLs (157 stmts). Aprendizado: ingest_cdc/transform_gold não aplicam comentários de coluna/NOT NULL/PK/tags → Fase 4 precisa de etapa de contratos no job; schema isu_silver criado à mão → declarar schemas no bundle

Critérios de sucesso:

- [X] `validate_state.py --layer silver` termina sem diff. — SEM DIFF (exit 0)
- [X] Contagens: `instalacoes` 30, `instalacoes_historico` 33, `contratos_concessao` 8, `concessao_precos` 10, `concessao_limites` 1. — 30/33/8/10/1
- [X] `instalacoes` sem chave duplicada e sem valor de texto com espaço no início ou no fim. — 30 = distinct(mandt, anlage); 0 linhas com c <> trim(c) nas 14 colunas string
- [X] `src/notebooks/ingest_cdc.py` idêntico ao template do plugin. — diff vazio (local e workspace)
- [X] Reexecutar a ingestão não altera as contagens. — 2º MERGE com numSourceRows=0 em todas (DESCRIBE HISTORY)

## Fase 3 — Gold

Tarefas:

- [X] Criar `schemas/gold/dim_concessao.yaml` e materializar a dimensão SCD Tipo 1 (`specs/SPEC-1.md#dim_concessao--dimensão-scd-tipo-1`). — transform_gold.py original + scd_type1; sk LGB_COM_01=1 … VLB_RES_01=8; sem watermark (relê a silver, SCD preserva SK)
- [X] Criar `schemas/gold/cip_esperada_prefeitura_mes.yaml` (`specs/SPEC-1.md#cip_esperada_prefeitura_mes--obt-transformação-custom`). — entidade obt, ingestao custom, fontes = 3 silvers, PK (cod_concessao, mes_referencia)
- [X] Implementar as regras de negócio da OBT em notebook próprio, derivado de `transform_gold.py` com alteração mínima (`specs/SPEC-1.md#transformações-da-ingestão-gold`). — src/notebooks/transform_gold_cip_esperada.py (+81/−27 vs transform_gold.py; seção de materialização idêntica); widgets periodo_inicio/periodo_fim. Runs 849480211206996 e 296374970480487. Fase 4: tarefa OBT usa esse notebook; depende de silver instalacoes_historico, contratos_concessao, concessao_precos; dim depende de contratos_concessao; scd_type1 precisa estar em src/notebooks (%run)
- [X] Aplicar os contratos de coluna, chave primária e PII nas tabelas gold. — 39 stmts SQL; isu_gold criado com CREATE SCHEMA IF NOT EXISTS. Fase 4: contratos e schemas precisam entrar no job/bundle

Critérios de sucesso:

- [X] `validate_state.py --layer gold` termina sem diff. — SEM DIFF (exit 0)
- [X] `dim_concessao` com 8 linhas e `sk_concessao` único. — 8 linhas, 8 sk distintas
- [X] `cip_esperada_prefeitura_mes` com 72 linhas, sem chave duplicada, e sem contrato de `tipo_calculo` diferente de `FIXO`. — 72 linhas, 72 chaves distintas, 6 contratos FIXO, nenhum PTB_*
- [X] Soma de `valor_cip_esperado` igual a 3798,00. — 3798.00
- [X] Reexecutar a transformação não altera contagens, valores nem `sk_concessao`. — 2º MERGE: 0 inseridas/0 removidas; EXCEPT ALL entre versões = 0 diferenças (OBT e dim, inclusive sk)

## Fase 4 — Orquestração

Tarefas:

- [X] Atualizar `resources/etl.job.yml`: uma tarefa por tabela silver e gold, com dependências silver → gold, parametrizadas por `${var.*}`. — 7 tarefas (5 silver ingest_cdc, gold_dim_concessao transform_gold, gold_cip_esperada_prefeitura_mes transform_gold_cip_esperada); job params periodo_inicio/periodo_fim. databricks.yml: root_path dev por usuário (exigido por mode: development)
- [X] Validar e implantar o bundle no target `dev`. — job <job_id> `[dev …] etl_medallion`. Disparo: `databricks bundle run etl_medallion -t dev`. Lacunas: schemas não declarados no bundle (prefixo dev conflitaria); contratos de coluna/PK/tags fora do job; prod com host placeholder

Critérios de sucesso:

- [X] `databricks bundle validate` sem erros. — Validation OK! (-t dev)
- [X] Job implantado, serverless, com 5 tarefas silver e 2 gold e as dependências corretas. — jobs get: sem clusters; dependências conferidas
- [X] Nenhum catálogo ou schema hardcoded em `resources/` e `src/`. — grep vazio; só ${var.*} e widgets

## Fase 5 — Validação end-to-end

Tarefas:

- [X] Executar o job implantado duas vezes seguidas. — runs 925327924632497 e 216929926414119 (≈51 s cada)
- [X] Comparar `cip_esperada_prefeitura_mes` com `dados_ficticios/esperado_cip.csv`, linha a linha. — FULL OUTER JOIN 72×72, 0 divergências
- [X] Rodar `validate_state.py` em todas as camadas. — 12 tabelas, SEM DIFF

Critérios de sucesso:

- [X] As duas execuções terminam com sucesso em todas as tarefas. — 7/7 tarefas SUCCESS nas duas
- [X] Contagens e valores idênticos entre a primeira e a segunda execução. — EXCEPT ALL entre versões = 0 (dim difere só em _atualizado_em)
- [X] Zero divergências contra o gabarito nas 72 linhas (`cod_concessao`, `mes_referencia`, `cod_parceiro_prefeitura`, `qtd_instalacoes_ativas`, `valor_cip_esperado`). — 0 faltantes, 0 extras, 0 divergências
- [X] Totais por prefeitura: 9000000001 = 1269,00; 9000000002 = 1635,00; 9000000003 = 894,00. — 1269.00 / 1635.00 / 894.00
- [X] `validate_state.py` sem diff nas três camadas. — exit 0


## Resumo

PLAN-1 concluído: 5 fases aprovadas na 1ª iteração. Job <job_id> (`etl_medallion`, dev). Gold confere com o gabarito (72 linhas, R$ 3.798,00).

## Revisão SPEC-1-1 (15/11/2026)

- [X] `ekong`/`concessao_precos`: `aklasse` → `konzigr` na KB e no estado local; bronze `ekong` recarregada, silver `concessao_precos` recriada pelo job (run 90962150934069, 7/7 SUCCESS); contratos reaplicados (58 stmts); `validate_state.py` SEM DIFF nas 12 tabelas; gold igual ao gabarito (72/72, R$ 3.798,00).

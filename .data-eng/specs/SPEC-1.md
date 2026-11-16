# SPEC-1 — Ingestão SAP IS-U para a Contribuição de Iluminação Pública (CIP)

## Fontes

- Guidelines: `.data-eng/guidelines/GENERAL.md`, `.data-eng/guidelines/CODING.md`, `.data-eng/guidelines/ENV.md`, `.data-eng/guidelines/LAYERS.md`
- Configuração: `databricks.yml` (catálogo e schemas por camada)
- Base de conhecimento do plugin (KB): `knowledge/sap/bronze/{eanl,eanlh,ekon,ekong,ekonh}.yaml`
- SPEC anterior: nenhuma. Outputs anteriores: nenhum.
- Validação de estado: sem definições locais; sem diff.

## Objetivo

Disponibilizar o cadastro de instalações e de contratos de concessão do SAP IS-U nas camadas
bronze e silver e, na gold, a **CIP esperada por contrato de concessão e mês**, calculada a
partir do cadastro (faixas de validade da instalação × preço vigente do contrato).

## Bronze (modelo fonte)

As cinco tabelas constam na KB. O `/run` deve **copiá-las deterministicamente** para
`schemas/bronze/<tabela>.yaml` (via `kb.py copy`), sem regerar colunas.

| Tabela | Arquivo da KB | Chave primária |
|--------|---------------|----------------|
| `eanl` | `knowledge/sap/bronze/eanl.yaml` | `mandt, anlage` |
| `eanlh` | `knowledge/sap/bronze/eanlh.yaml` | `mandt, anlage, bis` |
| `ekon` | `knowledge/sap/bronze/ekon.yaml` | `mandt, konzver` |
| `ekong` | `knowledge/sap/bronze/ekong.yaml` | `mandt, konzver, aklasse, ab, kabis` |
| `ekonh` | `knowledge/sap/bronze/ekonh.yaml` | `mandt, konzver, ab` |

Ajustes incrementais deste projeto (aplicar após a cópia, em todas as cinco):

- Acrescentar a coluna `_ingerido_em` (`timestamp`, não nula, PII `nenhum`, comentário
  "Timestamp de ingestão na bronze (auditoria)").
- As tabelas **já existem** no Unity Catalog (schema bronze do `databricks.yml`), tipadas e com
  dados. Não recriar nem recarregar: apenas aplicar os contratos (comentário da tabela e das
  colunas, chave primária, não-nulidade das chaves e tag de PII por coluna).

## Silver (idêntico à fonte, limpo)

Uma tabela silver por tabela bronze, com o mesmo grão, a mesma chave primária, os mesmos nomes
de coluna, tipos, comentários e classificação de PII da bronze, incluindo `_ingerido_em`
(watermark do incremental).

| Tabela silver | Fonte | Comentário da tabela |
|---------------|-------|----------------------|
| `instalacoes` | `bronze.eanl` | Instalações IS-U limpas e sem duplicidade — espelho de `eanl`. |
| `instalacoes_historico` | `bronze.eanlh` | Faixas de validade das instalações IS-U, limpas — espelho de `eanlh`. |
| `contratos_concessao` | `bronze.ekon` | Contratos de concessão (CIP), limpos — espelho de `ekon`. |
| `concessao_precos` | `bronze.ekong` | Preços dos contratos de concessão, limpos — espelho de `ekong`. |
| `concessao_limites` | `bronze.ekonh` | Limites dos contratos de concessão, limpos — espelho de `ekonh`. |

### Transformações da ingestão silver

Somente a limpeza padrão do CDC, sem alteração de código:

- Remoção de espaços no início e no fim de todas as colunas de texto.
- Uma linha por chave primária: em caso de duplicidade, permanece a de `_ingerido_em` mais recente.
- Ingestão incremental por `_ingerido_em` e idempotente (MERGE pela chave primária).

## Gold (modelo destino)

### `dim_concessao` — dimensão SCD Tipo 1

- Comentário: "Dimensão de contratos de concessão (CIP) — um registro por contrato, com a prefeitura beneficiária e o tipo de cálculo."
- Fonte: `silver.contratos_concessao`. Chave de negócio: `cod_concessao`. Chave surrogada e chave primária: `sk_concessao`.

| Coluna | Tipo | Origem | Comentário | PII | Nulo |
|--------|------|--------|------------|-----|------|
| `sk_concessao` | bigint | gerada | Chave surrogada da dimensão (gerada). | nenhum | não |
| `cod_concessao` | string | `konzver` | Contrato de concessão. | nenhum | não |
| `cod_parceiro_prefeitura` | string | `kunde` | Parceiro de negócio da prefeitura beneficiária da CIP. | indireto | sim |
| `tipo_calculo` | string | `vertart` | Tipo do contrato: valor fixo ou percentual sobre o consumo faturado. | nenhum | sim |
| `empresa` | string | `bukrs` | Empresa. | nenhum | sim |
| `dt_inicio_contrato` | date | `vbeginn` | Data de início do contrato de concessão. | nenhum | sim |
| `dt_fim_contrato` | date | `vende` | Data de fim do contrato de concessão. | nenhum | sim |
| `_atualizado_em` | timestamp | gerada | Timestamp da última atualização do registro (gerado). | nenhum | não |

### `cip_esperada_prefeitura_mes` — OBT (transformação custom)

- Comentário: "CIP esperada por contrato de concessão e mês, calculada pelo cadastro: instalações com faixa vigente × preço vigente do contrato. Somente contratos de valor fixo."
- Entidade: `obt`. Ingestão: `custom`.
- Fontes: `silver.instalacoes_historico`, `silver.contratos_concessao`, `silver.concessao_precos`.
- Chave primária: `cod_concessao, mes_referencia`.

| Coluna | Tipo | Comentário | PII | Nulo |
|--------|------|------------|-----|------|
| `cod_concessao` | string | Contrato de concessão. | nenhum | não |
| `mes_referencia` | date | Mês de referência (primeiro dia do mês). | nenhum | não |
| `cod_parceiro_prefeitura` | string | Parceiro de negócio da prefeitura beneficiária da CIP. | indireto | sim |
| `qtd_instalacoes_ativas` | int | Instalações com faixa vigente no contrato no primeiro dia do mês. | nenhum | não |
| `valor_cip_esperado` | decimal(23,2) | CIP esperada no mês: soma do preço vigente por instalação ativa. | nenhum | não |

### Transformações da ingestão gold

Regras de negócio de `cip_esperada_prefeitura_mes`:

1. **Meses de referência**: janeiro a dezembro de 2025, um registro de data por mês (dia 1º).
   O período é parâmetro da transformação (início e fim), com esse padrão.
2. **Instalação ativa no mês**: a instalação conta no mês quando possui faixa em
   `instalacoes_historico` com `ab <= mes_referencia <= bis` e `konzver` preenchido
   (não nulo e não vazio). O contrato do mês é o `konzver` dessa faixa.
3. **Preço vigente**: o preço do contrato no mês é o `konkun` do registro de `concessao_precos`
   de maior `ab` tal que `ab <= mes_referencia`, para o mesmo `konzver`. A tabela de preços só
   possui data de início; o fim de cada preço é a véspera do próximo `ab` do mesmo contrato.
4. **Somente contratos de valor fixo**: entram apenas contratos com `vertart = 'FIXO'` em
   `contratos_concessao`.
5. **Agregação**: por `cod_concessao` e `mes_referencia`: `qtd_instalacoes_ativas` é a contagem
   de instalações distintas e `valor_cip_esperado` é a soma do preço vigente dessas instalações.
   Combinações sem instalação ativa não geram linha.
6. **Prefeitura**: `cod_parceiro_prefeitura` é o `kunde` do contrato. Um mesmo parceiro pode ter
   vários contratos; a visão por prefeitura é a soma por `cod_parceiro_prefeitura`.
7. **Idempotência**: reprocessar o mesmo período não duplica linhas nem altera valores.

## Fora de escopo

- Contratos percentuais (`vertart = 'PERC'`) e preços por escalão de consumo (`kavon`/`kabis`).
- Aplicação dos limites de `concessao_limites` no cálculo.
- Linhas de fatura e comparação entre CIP esperada e CIP faturada.
- Rateio proporcional quando a instalação troca de contrato no meio do mês (vale o dia 1º).
- Metric View, Genie space, Data Classification e Quality Monitor.
- Ingestão do SAP para a bronze.

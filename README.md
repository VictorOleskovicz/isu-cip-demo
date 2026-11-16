# Demo: SAP IS-U (CIP) no plugin `data-eng-agent`

Este projeto testa o plugin [`databricks-data-eng-agent`](https://github.com/vorodrigues/databricks-data-eng-agent)
com um caso de **SAP IS-U** (utilities), que a base de conhecimento do plugin ainda não cobria.
O caso escolhido é a **Contribuição de Iluminação Pública (CIP)**: quanto cada prefeitura deve
receber por mês, calculado a partir do cadastro de instalações e contratos de concessão.

> Todos os dados são **fictícios**. Municípios, parceiros, contratos e valores foram inventados.

## 1. O que o plugin faz

O plugin é uma extensão do Claude Code para construir pipelines no Databricks em três camadas:

| Camada | O que é | Quem produz |
|--------|---------|-------------|
| **Bronze** | Dado bruto, como vem do SAP | Fora do plugin (replicação, Auto Loader etc.) |
| **Silver** | O mesmo dado, limpo e sem duplicidade | Notebook fixo do plugin (`ingest_cdc.py`) |
| **Gold** | Tabelas de negócio | Notebook fixo (`transform_gold.py`) + regra de negócio |

A ideia central é o **determinismo**: em vez de a IA escrever um pipeline novo para cada tabela,
o plugin tem notebooks fixos que leem um **YAML** com a ficha da tabela (colunas, tipos, chave,
comentários, dados pessoais). O YAML é o contrato do resultado. A IA só entra para:

1. transformar o pedido em uma especificação (`/specify`) e um plano (`/plan`);
2. montar os YAMLs — **copiando** da base de conhecimento quando a tabela já existe lá;
3. escrever a regra de negócio da gold quando nenhum notebook fixo resolve (a "exceção").

O ciclo é `specify → plan → run`. Só o `run` altera o Databricks.

## 2. A contribuição: IS-U na base de conhecimento

A base de conhecimento (`knowledge/sap/`) tinha 207 tabelas bronze e 84 data products gold,
importados do Cortex Framework — sem nenhuma tabela de IS-U. Sem a tabela na base, a IA precisa
inventar a definição a cada execução, que é justamente o que o plugin tenta evitar.

Foram adicionadas cinco tabelas bronze, no formato do plugin:

| Tabela | Conteúdo | Chave |
|--------|----------|-------|
| `eanl` | Instalação (dados sem validade) | `mandt, anlage` |
| `eanlh` | Instalação (faixas de validade: tarifa, classe, contrato de concessão) | `mandt, anlage, bis` |
| `ekon` | Contrato de concessão — cabeçalho (prefeitura, tipo) | `mandt, konzver` |
| `ekong` | Contrato de concessão — preços | `mandt, konzver, konzigr, ab, kabis` |
| `ekonh` | Contrato de concessão — limites | `mandt, konzver, ab` |

Arquivos alterados no fork do plugin ([`feat/isu-kb`](https://github.com/VictorOleskovicz/databricks-data-eng-agent/tree/feat/isu-kb), [ver a alteração](https://github.com/VictorOleskovicz/databricks-data-eng-agent/compare/main...feat/isu-kb)):

- `knowledge/sap/bronze/{eanl,eanlh,ekon,ekong,ekonh}.yaml` (novos)
- `knowledge/sap/INDEX.md` (regenerado com `python3 scripts/kb.py index`)

### Pontos a validar na SE11 antes de publicar

- `ekong`: o campo de classe foi confirmado como `KONZIGR` (revisão `SPEC-1-1`). Falta conferir
  se a chave está correta e se existe data fim.
- `ekonh`: a chave é só contrato + data, ou inclui a classe?
- `ekon`: a moeda (`TWAERS`) fica no cabeçalho?
- `eanl` × `eanlh`: conferir em qual das duas ficam `anlart`, `spebene`, `nodisconct`,
  `deregstat`, `ablesartst`, `konzver`, `temp_area` e `istype`.
- Os YAMLs trazem só os campos principais, não a tabela inteira.

## 3. O caso de uso da demo

**Pergunta:** quanto de CIP cada prefeitura deve receber em cada mês de 2025?

O SAP calcula isso na hora do faturamento, mas não grava em lugar nenhum uma **projeção** feita
só com o cadastro. A gold `cip_esperada_prefeitura_mes` faz esse cálculo:

1. Para cada mês, a instalação conta se tiver uma faixa da `eanlh` vigente no **dia 1º** com
   contrato de concessão (`konzver`) preenchido.
2. Vale o preço da `ekong` vigente nesse dia. A `ekong` só tem data de início; o fim de um
   preço é a véspera do próximo.
3. Entram só contratos de **valor fixo** (`vertart = 'FIXO'`).
4. Soma por contrato e mês. A visão por prefeitura soma pelo parceiro (`kunde`), porque uma
   prefeitura tem vários contratos (um por classe).

Fora do escopo desta demo: contratos percentuais, preço por faixa de consumo, limites, rateio
quando a instalação troca de contrato no meio do mês e comparação com o valor faturado.

## 4. Dados fictícios

Gerados por `dados_ficticios/gerar.py`:

- **30 instalações** e **8 contratos de concessão** de 4 municípios inventados. A chave do
  contrato segue o formato `MMG_CCC_IZ` (município, grupo de tensão, classe, sufixo).
- **Casos de borda plantados**: reajuste de preço no meio do ano; instalação que muda de classe
  no dia 1º e outra no meio do mês; instalação nova em abril; instalação encerrada em agosto;
  instalações sem contrato de concessão; uma linha duplicada e um campo com espaços sobrando.
- **Gabarito** (`esperado_cip.csv`): o script calcula a resposta certa por força bruta,
  instalação a instalação. O total esperado em 2025 é **R$ 3.798,00**:

| Prefeitura (parceiro) | CIP esperada em 2025 |
|-----------------------|----------------------|
| 9000000001 | R$ 1.269,00 |
| 9000000002 | R$ 1.635,00 |
| 9000000003 | R$ 894,00 |
| 9000000004 | fora do cálculo (contratos percentuais) |

`dados_ficticios/carregar_bronze.sh` envia os CSVs para um Volume e cria as tabelas bronze
tipadas, com a coluna `_ingerido_em`. Ele faz o papel da replicação do SAP.

## 5. Onde está cada coisa

| O quê | Onde |
|-------|------|
| Fork do plugin com as tabelas IS-U | [VictorOleskovicz/databricks-data-eng-agent](https://github.com/VictorOleskovicz/databricks-data-eng-agent/tree/feat/isu-kb) (branch `feat/isu-kb`) |
| Este projeto de demo | este repositório |
| Especificação | `.data-eng/specs/SPEC-1.md` |
| Plano e registro da execução | `.data-eng/plans/`, `.data-eng/outputs/` |
| Fichas das tabelas (estado local) | `schemas/{bronze,silver,gold}/` |
| Notebooks do plugin | `src/notebooks/` |
| Configuração (catálogo, schemas, warehouse) | `databricks.yml` |
| Dados fictícios e gabarito | `dados_ficticios/` |
| Bronze no Databricks | `workspace.isu_bronze` |
| Silver e gold no Databricks | `workspace.isu_silver`, `workspace.isu_gold` (criadas pelo `run`) |

## 6. Passo a passo do que foi feito

1. **Ambiente**: instalados `jq`, Databricks CLI e `pyyaml`; login no workspace (Free Edition).
2. **Leitura do plugin**: README, skills, notebooks e a base de conhecimento.
3. **Diagnóstico da base**: nenhuma tabela IS-U; 26 golds sem chave primária; 8 tabelas citadas
   como fonte de golds e ausentes da bronze (`bsid`, `bsad`, `bsik`, `bsak`, `matdoc`, `prhi`,
   `rpsco`, `tf201`).
4. **Tabelas IS-U**: escritos os cinco YAMLs e regenerado o índice.
5. **Dados fictícios**: gerados com gabarito e carregados em `workspace.isu_bronze`.
6. **Projeto de demo**: `init` do plugin, `databricks.yml` preenchido e plugin instalado a partir
   do clone local, para o teste usar as tabelas novas.
7. **`specify`**: o plugin encontrou as cinco tabelas na base e a SPEC apenas as **referencia**,
   sem detalhar colunas — o comportamento que a contribuição buscava.
8. **`plan`**: 5 fases com critérios verificáveis (`.data-eng/plans/PLAN-1.md`).
9. **`run`**: as 5 fases foram aprovadas pelo avaliador na 1ª tentativa
   (registro em `.data-eng/outputs/PLAN-1_OUT.md`):
   - bronze: YAMLs copiados da base e contratos aplicados, sem recarregar dados;
   - silver: 5 tabelas pelo `ingest_cdc.py` original (31 → 30 instalações, espaços limpos);
   - gold: `dim_concessao` (notebook original) e `cip_esperada_prefeitura_mes` (notebook novo
     `src/notebooks/transform_gold_cip_esperada.py`, o único código escrito);
   - orquestração: job `etl_medallion` (7 tarefas, serverless) implantado por bundle;
   - validação: job executado duas vezes (≈51 s cada), resultados idênticos.
10. **Conferência com o gabarito**: 72 de 72 linhas, zero divergências; R$ 3.798,00 no total.

## 7. Como reproduzir

```bash
# 1. dados fictícios e bronze
cd dados_ficticios
python3 gerar.py
./carregar_bronze.sh <warehouse_id>

# 2. no Claude Code, dentro desta pasta
/data-eng-agent:specify <pedido>
/data-eng-agent:plan
/data-eng-agent:run
```

## 8. Observações sobre o plugin

Pontos notados durante o uso, que não foram alterados:

1. **Cruzamento de faixas de validade.** O plugin só tem dimensão SCD Tipo 1 (valor atual).
   Tabelas com vigência, como a `eanlh` e a `ekong`, caem na "exceção", com código escrito pela
   IA. O padrão se repete em outras tabelas SAP (`DATAB`/`DATBI`, `BEGDA`/`ENDDA`) e poderia
   virar um notebook determinístico.
2. **YAML de bronze é quase duplicata da tabela.** Poderia ser gerado da própria tabela no
   Unity Catalog ou do dicionário do SAP (`DD03L`/`DD04T`, que já estão na base).
3. **A silver não converte tipos.** O `ingest_cdc.py` projeta e limpa espaços, mas não aplica o
   `tipo` do YAML; a bronze precisa chegar tipada.
4. **Furos na base**: os itens do diagnóstico no passo 3.
5. **Permissões do `init`**: libera qualquer comando `databricks`, inclusive os destrutivos.
6. **Nomes de tabela**: o plugin espera a bronze com o nome SAP original; ambientes existentes
   com outros nomes precisariam de um mapeamento.
7. **Sem quarentena.** O `ingest_cdc.py` descarta duplicados sem registro e deixa passar chaves
   nulas, datas inválidas e referências quebradas. Sugestão: regras de qualidade declaradas no
   YAML da silver, com os registros rejeitados gravados em uma tabela de quarentena com o motivo.

## 9. Estado atual

Atualizado em 16/11/2026: fluxo completo executado e conferido com o gabarito. Falta a revisão
de alguns campos na SE11 (lista na seção 2).

Para reproduzir, preencha em `databricks.yml` o host do workspace e o `warehouse_id`.

Lacunas observadas na execução (os subagentes contornaram com SQL avulso, fora do job):
- os notebooks não aplicam comentários de coluna, chave primária, NOT NULL nem as tags de PII;
- os schemas `isu_silver` e `isu_gold` foram criados à mão, fora do bundle.

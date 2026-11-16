# SPEC-1-1 — Revisão: campo de classe na tabela de preços da concessão

## Fontes

- SPEC revisada: `.data-eng/specs/SPEC-1.md`
- Output anterior: `.data-eng/outputs/PLAN-1_OUT.md`
- Base de conhecimento do plugin (KB): `knowledge/sap/bronze/ekong.yaml`

## Alteração

Na tabela `ekong` (preços do contrato de concessão), a classe de cálculo tem o nome técnico
**`konzigr`**, e não `aklasse`. A KB foi corrigida; o `/run` deve copiar de novo o arquivo da KB.

| Tabela | Arquivo da KB | Chave primária |
|--------|---------------|----------------|
| `ekong` | `knowledge/sap/bronze/ekong.yaml` | `mandt, konzver, konzigr, ab, kabis` |

- Bronze `ekong` e silver `concessao_precos`: a coluna `aklasse` passa a se chamar `konzigr`,
  com o mesmo tipo, comentário ("Classe de cálculo") e PII (`nenhum`). A chave primária muda
  da mesma forma. Demais colunas e contratos inalterados.
- `eanlh` e `instalacoes_historico` mantêm `aklasse`: é o campo da própria instalação.
- Gold: sem alteração. As regras de `cip_esperada_prefeitura_mes` não usam a classe.

## Fora de escopo

O mesmo da SPEC-1.

#!/usr/bin/env bash
# Carrega os CSVs ficticios no Volume e (re)cria as tabelas bronze tipadas, com _ingerido_em.
# Uso: ./carregar_bronze.sh <warehouse_id> [catalogo] [schema_bronze]
set -euo pipefail
WH="$1"; CAT="${2:-workspace}"; SCH="${3:-isu_bronze}"
V="/Volumes/$CAT/$SCH/raw"
q() {
  databricks api post /api/2.0/sql/statements --json "$(jq -n --arg s "$1" --arg w "$WH" '{warehouse_id:$w, statement:$s, wait_timeout:"50s"}')" \
    | jq -r '.status.state as $st | if $st=="SUCCEEDED" then "OK " + ((.result.data_array // []) | map(join("=")) | join("  ")) else "\($st): \(.status.error.message // "")" end'
}
ctas() {  # tabela, schema do csv, lista de colunas com casts
  databricks fs mkdir "dbfs:$V/$1" 2>/dev/null
  databricks fs cp "$1.csv" "dbfs:$V/$1/$1.csv" --overwrite >/dev/null 2>&1
  printf '%s: ' "$1"
  q "CREATE OR REPLACE TABLE $CAT.$SCH.$1 AS SELECT $3, current_timestamp() AS _ingerido_em FROM read_files('$V/$1/', format=>'csv', header=>true, schema=>'$2')"
}
q "CREATE SCHEMA IF NOT EXISTS $CAT.$SCH COMMENT 'Demo IS-U/CIP: dados ficticios brutos (modelo SAP)'" >/dev/null
q "CREATE VOLUME IF NOT EXISTS $CAT.$SCH.raw" >/dev/null
ctas eanl  'mandt string, anlage string, sparte string, vstelle string, anlart string, spebene string, erdat string, ernam string, aedat string, aenam string, loevm string' \
           'mandt, anlage, sparte, vstelle, cast(null as string) bezug, anlart, spebene, cast(null as string) ablesartst, cast(null as string) nodisconct, cast(null as string) deregstat, to_date(erdat) erdat, ernam, to_date(aedat) aedat, aenam, cast(null as string) begru, loevm'
ctas eanlh 'mandt string, anlage string, bis string, ab string, tariftyp string, aklasse string, ableinh string, konzver string' \
           'mandt, anlage, to_date(bis) bis, to_date(ab) ab, tariftyp, cast(null as string) branche, aklasse, ableinh, cast(null as string) temp_area, konzver, cast(null as string) maininst, cast(null as string) instrole, cast(null as string) instgrtype, cast(null as string) istype'
ctas ekon  'mandt string, konzver string, sparte string, bukrs string, kunde string, twaers string, vbeginn string, vende string, vertart string, erdat string' \
           'mandt, konzver, sparte, bukrs, kunde, twaers, to_date(vbeginn) vbeginn, to_date(vende) vende, vertart, to_date(erdat) erdat'
ctas ekong 'mandt string, konzver string, konzigr string, ab string, kabis string, kavon string, konkun string, konevu string, twaers string' \
           'mandt, konzver, konzigr, to_date(ab) ab, cast(kabis as decimal(23,2)) kabis, cast(kavon as decimal(23,2)) kavon, cast(konkun as decimal(38,9)) konkun, cast(konevu as decimal(38,9)) konevu, twaers'
ctas ekonh 'mandt string, konzver string, ab string, mass string, grenzmng string, grenzpr string, twaers string' \
           'mandt, konzver, to_date(ab) ab, mass, cast(grenzmng as decimal(23,2)) grenzmng, cast(grenzpr as decimal(23,2)) grenzpr, twaers'
q "SELECT 'eanl', count(*) FROM $CAT.$SCH.eanl UNION ALL SELECT 'eanlh', count(*) FROM $CAT.$SCH.eanlh UNION ALL SELECT 'ekon', count(*) FROM $CAT.$SCH.ekon UNION ALL SELECT 'ekong', count(*) FROM $CAT.$SCH.ekong UNION ALL SELECT 'ekonh', count(*) FROM $CAT.$SCH.ekonh"

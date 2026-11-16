# Databricks notebook source
# MAGIC %md
# MAGIC # Transformacao — silver -> gold (OBT `cip_esperada_prefeitura_mes`)
# MAGIC
# MAGIC Derivado de `transform_gold.py`, dirigido pelo **estado da gold**
# MAGIC (`schemas/gold/cip_esperada_prefeitura_mes.yaml`). O YAML e a fonte de verdade: dele saem
# MAGIC as fontes (`fontes`, lista de silvers), a entidade (`obt`), a chave primaria e o comentario.
# MAGIC
# MAGIC Fluxo:
# MAGIC 1. Le o estado e as tres silvers de origem (`instalacoes_historico`, `contratos_concessao`,
# MAGIC    `concessao_precos`).
# MAGIC 2. Gera os meses de referencia do periodo (`periodo_inicio` a `periodo_fim`, dia 1o).
# MAGIC 3. Na funcao `transformar`, aplica as regras de negocio da CIP esperada:
# MAGIC    - instalacao ativa no 1o dia do mes (`ab <= mes <= bis`) com `konzver` preenchido;
# MAGIC    - somente contratos de valor fixo (`vertart = 'FIXO'`);
# MAGIC    - preco vigente = `konkun` do maior `ab <= mes` do mesmo contrato;
# MAGIC    - agregacao por contrato e mes (instalacoes distintas e soma do preco).
# MAGIC 4. Materializa por **MERGE pela chave primaria** (`cod_concessao, mes_referencia`):
# MAGIC    reprocessar o mesmo periodo nao duplica linhas nem altera valores (idempotente).

# COMMAND ----------
# MAGIC %run ../notebooks/scd_type1

# COMMAND ----------
dbutils.widgets.text("catalogo", "")
dbutils.widgets.text("schema_origem", "")      # schema UC da silver
dbutils.widgets.text("schema_destino", "")     # schema UC da gold
dbutils.widgets.text("caminho_estado", "")     # path do YAML de estado da gold
dbutils.widgets.text("periodo_inicio", "2025-01-01")  # primeiro mes de referencia (yyyy-MM-01)
dbutils.widgets.text("periodo_fim", "2025-12-01")     # ultimo mes de referencia (yyyy-MM-01)

catalogo = dbutils.widgets.get("catalogo")
schema_origem = dbutils.widgets.get("schema_origem")
schema_destino = dbutils.widgets.get("schema_destino")
caminho_estado = dbutils.widgets.get("caminho_estado")
periodo_inicio = dbutils.widgets.get("periodo_inicio")
periodo_fim = dbutils.widgets.get("periodo_fim")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 1. Estado (YAML da gold)

# COMMAND ----------
import yaml
from pyspark.sql import functions as F
from delta.tables import DeltaTable

with open(caminho_estado) as f:
    estado = yaml.safe_load(f)

tabela_destino = estado["tabela"]
fontes_tabelas = [f.split(".")[-1] for f in estado["fontes"]]  # OBT: varias silvers
entidade = estado.get("entidade", "dimensao")            # dimensao | fato | obt
comentario_tabela = (estado.get("comentario") or "").strip()
chave_negocio = list(estado.get("chave_negocio", []) or [])
chave_surrogada = estado.get("chave_surrogada")
chave_primaria = list(estado.get("chave_primaria", []) or [])
wm_destino = estado.get("watermark")

# colunas com 'origem' sao projetadas da silver; as demais (sk, metricas) sao geradas
proj = {c["nome"]: c["origem"] for c in estado["colunas"] if "origem" in c}
wm_origem = proj.get(wm_destino) if wm_destino else None

fontes = {t: f"{catalogo}.{schema_origem}.{t}" for t in fontes_tabelas}
destino = f"{catalogo}.{schema_destino}.{tabela_destino}"

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. Leitura das silvers + meses de referencia
# MAGIC O resultado depende do periodo inteiro (faixas e precos vigentes), entao as fontes sao
# MAGIC lidas por completo; a idempotencia vem do MERGE pela chave primaria na etapa 4.

# COMMAND ----------
destino_existe = spark.catalog.tableExists(destino)

base = {t: spark.table(nome) for t, nome in fontes.items()}

# um registro por mes (dia 1o) entre periodo_inicio e periodo_fim
meses = spark.sql(
    f"SELECT explode(sequence(to_date('{periodo_inicio}'), to_date('{periodo_fim}'), interval 1 month)) AS mes_referencia"
)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3. Logica de negocio (excecao)
# MAGIC Regras da CIP esperada (SPEC-1, "Transformacoes da ingestao gold"):
# MAGIC - **Instalacao ativa**: faixa de `instalacoes_historico` com `ab <= mes <= bis` e
# MAGIC   `konzver` nao nulo e nao vazio; o contrato do mes e o `konzver` da faixa.
# MAGIC - **Somente valor fixo**: contratos com `vertart = 'FIXO'`; a prefeitura e o `kunde`.
# MAGIC - **Preco vigente**: `konkun` do registro de `concessao_precos` com maior `ab <= mes`
# MAGIC   para o mesmo contrato (o preco vale ate a vespera do proximo `ab`).
# MAGIC - **Agregacao**: por contrato e mes — instalacoes distintas e soma do preco vigente.
# MAGIC   Combinacoes sem instalacao ativa nao geram linha.

# COMMAND ----------
from pyspark.sql import Window


def transformar(fontes_df):
    hist = fontes_df["instalacoes_historico"]
    contratos = fontes_df["contratos_concessao"]
    precos = fontes_df["concessao_precos"]

    # instalacoes ativas no 1o dia do mes, com contrato preenchido (1 linha por instalacao/mes)
    ativas = (
        hist.filter(F.col("konzver").isNotNull() & (F.trim(F.col("konzver")) != ""))
        .join(meses, (F.col("ab") <= F.col("mes_referencia")) & (F.col("mes_referencia") <= F.col("bis")))
        .select("mandt", "anlage", "konzver", "mes_referencia")
        .dropDuplicates()
    )

    # somente contratos de valor fixo
    fixos = contratos.filter(F.col("vertart") == "FIXO").select("mandt", "konzver", "kunde")

    # preco vigente: maior ab <= mes para o mesmo contrato
    w = Window.partitionBy("mandt", "konzver", "mes_referencia").orderBy(F.col("ab").desc())
    preco_mes = (
        precos.join(meses, F.col("ab") <= F.col("mes_referencia"))
        .withColumn("_ordem", F.row_number().over(w))
        .filter(F.col("_ordem") == 1)
        .select("mandt", "konzver", "mes_referencia", "konkun")
    )

    return (
        ativas.join(fixos, ["mandt", "konzver"])
        .join(preco_mes, ["mandt", "konzver", "mes_referencia"])
        .groupBy(
            F.col("konzver").alias("cod_concessao"),
            "mes_referencia",
            F.col("kunde").alias("cod_parceiro_prefeitura"),
        )
        .agg(
            F.countDistinct("anlage").cast("int").alias("qtd_instalacoes_ativas"),
            F.sum("konkun").cast("decimal(23,2)").alias("valor_cip_esperado"),
        )
        .select([c["nome"] for c in estado["colunas"]])  # ordem das colunas do YAML
    )


df = transformar(base)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 4. Materializacao
# MAGIC Dimensao -> SCD Tipo 1 (gera a chave surrogada). Fato -> MERGE incremental pela PK.
# MAGIC OBT (tabela larga denormalizada) -> MERGE pela PK se houver; senao, overwrite idempotente.

# COMMAND ----------
def _cria_vazia_com_comentario():
    df.limit(0).write.format("delta").mode("overwrite").saveAsTable(destino)
    if comentario_tabela:
        spark.sql(f"COMMENT ON TABLE {destino} IS '{comentario_tabela.replace(chr(39), chr(39)*2)}'")


if entidade == "dimensao":
    colunas_atributo = [c for c in df.columns if c not in chave_negocio and c != chave_surrogada]
    aplicar_scd_tipo1(
        spark,
        df_origem=df,
        tabela_destino=destino,
        chave_negocio=chave_negocio,
        coluna_sk=chave_surrogada,
        colunas_atributo=colunas_atributo,
        comentario_tabela=comentario_tabela,
    )
elif entidade == "obt" and not chave_primaria:
    # OBT sem PK declarada: overwrite completo (idempotente). Preferivel definir a PK
    # do produto para permitir MERGE incremental — ver revisao dos data products.
    df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(destino)
    if comentario_tabela:
        spark.sql(f"COMMENT ON TABLE {destino} IS '{comentario_tabela.replace(chr(39), chr(39)*2)}'")
else:
    # fato ou OBT com PK: MERGE incremental idempotente pela chave primaria.
    if not chave_primaria:
        raise ValueError(f"{destino}: entidade '{entidade}' exige chave_primaria para o MERGE.")
    if not destino_existe:
        _cria_vazia_com_comentario()
    cond = " AND ".join([f"d.{k} = o.{k}" for k in chave_primaria])
    (
        DeltaTable.forName(spark, destino).alias("d")
        .merge(df.alias("o"), cond)
        .whenMatchedUpdateAll()
        .whenNotMatchedInsertAll()
        .execute()
    )

print(f"OK: {destino} materializada ({entidade}).")

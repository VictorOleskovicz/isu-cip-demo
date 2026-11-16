#!/usr/bin/env python3
"""Gera dados 100% ficticios de IS-U (instalacoes e contratos de concessao/CIP) para a demo.

Saida: um CSV por tabela SAP (eanl, eanlh, ekon, ekong, ekonh) e o gabarito
`esperado_cip.csv`, calculado aqui por forca bruta (instalacao a instalacao, mes a mes)
para conferir o resultado da gold de forma independente.

Regra do gabarito: a instalacao conta no mes se tiver faixa vigente no 1o dia do mes;
vale o preco do contrato vigente nesse mesmo dia. So contratos de valor fixo (FIXO).
"""
import csv
from datetime import date

MANDT = "100"
FIM = date(9999, 12, 31)
MESES = [date(2025, m, 1) for m in range(1, 13)]

# --- contratos de concessao (municipios ficticios) ------------------------------
# Chave no formato MMG_CCC_IZ (10 posicoes): MM = sigla do municipio, G = grupo de tensao,
# CCC = classe, IZ = sufixo. Um mesmo municipio (prefeitura) tem varios contratos, um por
# classe; por isso a visao "por prefeitura" agrupa pelo parceiro (KUNDE), nao pelo KONZVER.
MUNICIPIOS = {"VL": "9000000001", "SR": "9000000002", "LG": "9000000003", "PT": "9000000004"}
def kz(mm, classe): return f"{mm}B_{classe}_01"
EKON = [(kz(mm, c), p, "PERC" if mm == "PT" else "FIXO") for mm, p in MUNICIPIOS.items() for c in ("RES", "COM")]
EKONG = [  # konzver, a partir de, valor/percentual
    (kz("VL", "RES"), date(2025, 1, 1), "10.00"),
    (kz("VL", "RES"), date(2025, 7, 1), "12.00"),   # reajuste no meio do ano
    (kz("VL", "COM"), date(2025, 1, 1), "25.00"),
    (kz("SR", "RES"), date(2025, 1, 1), "15.00"),
    (kz("SR", "COM"), date(2025, 1, 1), "30.00"),
    (kz("LG", "RES"), date(2025, 1, 1), "8.50"),
    (kz("LG", "RES"), date(2025, 10, 1), "9.00"),   # reajuste em outubro
    (kz("LG", "COM"), date(2025, 1, 1), "20.00"),
    (kz("PT", "RES"), date(2025, 1, 1), "5.00"),    # percentual
    (kz("PT", "COM"), date(2025, 1, 1), "7.00"),    # percentual
]
EKONH = [(kz("PT", "RES"), date(2025, 1, 1), "kWh", "300.00")]

# --- instalacoes e faixas --------------------------------------------------------
# anlage -> lista de faixas (ab, bis, konzver)
FAIXAS = {}
def inst(n): return f"{500000 + n:010d}"
def classe(n): return "COM" if n % 5 == 0 else "RES"
for n in range(1, 31):
    mm = ["VL", "SR", "LG", "PT"][(n - 1) % 4]
    FAIXAS[inst(n)] = [(date(2025, 1, 1), FIM, kz(mm, classe(n)))]
# casos especiais (cada um testa uma borda do calculo)
FAIXAS[inst(1)] = [(date(2025, 1, 1), date(2025, 9, 30), kz("VL", "RES")),   # muda de classe no dia 1
                   (date(2025, 10, 1), FIM, kz("VL", "COM"))]
FAIXAS[inst(7)] = [(date(2025, 1, 1), date(2025, 9, 14), kz("LG", "RES")),   # muda de classe no meio do mes
                   (date(2025, 9, 15), FIM, kz("LG", "COM"))]
FAIXAS[inst(9)] = [(date(2025, 4, 1), FIM, kz("VL", "RES"))]                 # instalacao nova em abril
FAIXAS[inst(6)] = [(date(2025, 1, 1), date(2025, 8, 31), kz("SR", "RES"))]   # encerrada em agosto
FAIXAS[inst(13)] = [(date(2025, 1, 1), FIM, "")]                             # sem contrato de concessao
FAIXAS[inst(14)] = [(date(2025, 1, 1), date(2025, 5, 31), kz("SR", "RES")),  # perde o contrato em junho
                    (date(2025, 6, 1), FIM, "")]

d = lambda x: x.strftime("%Y-%m-%d")

def grava(nome, cab, linhas):
    with open(f"{nome}.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(cab); w.writerows(linhas)
    print(f"{nome}.csv: {len(linhas)} linhas")

eanl = []
for n in range(1, 31):
    eanl.append([MANDT, inst(n), "01", f"{700000 + n:010d}", classe(n), "B1", "2024-12-15", "CARGA", "", "", ""])
eanl.append(eanl[2][:])            # sujeira: linha duplicada (mesma chave)
eanl[3][4] = "RES   "              # sujeira: espacos sobrando
grava("eanl", ["mandt", "anlage", "sparte", "vstelle", "anlart", "spebene", "erdat", "ernam", "aedat", "aenam", "loevm"], eanl)

grava("eanlh", ["mandt", "anlage", "bis", "ab", "tariftyp", "aklasse", "ableinh", "konzver"],
      [[MANDT, a, d(bis), d(ab), "B1_CONV", "GPB", "UL000001", k] for a, fs in FAIXAS.items() for ab, bis, k in fs])
grava("ekon", ["mandt", "konzver", "sparte", "bukrs", "kunde", "twaers", "vbeginn", "vende", "vertart", "erdat"],
      [[MANDT, k, "01", "X001", p, "BRL", "2025-01-01", "9999-12-31", t, "2024-12-01"] for k, p, t in EKON])
grava("ekong", ["mandt", "konzver", "konzigr", "ab", "kabis", "kavon", "konkun", "konevu", "twaers"],
      [[MANDT, k, "GPB", d(ab), "9999999999", "0", v, v, "BRL"] for k, ab, v in EKONG])
grava("ekonh", ["mandt", "konzver", "ab", "mass", "grenzmng", "grenzpr", "twaers"],
      [[MANDT, k, d(ab), u, lim, "", "BRL"] for k, ab, u, lim in EKONH])

# --- gabarito (forca bruta) -------------------------------------------------------
tipo = {k: t for k, _, t in EKON}
def preco(k, dia):
    vig = [(ab, v) for kk, ab, v in EKONG if kk == k and ab <= dia]
    return max(vig)[1] if vig else None

gab = {}
for a, fs in FAIXAS.items():
    for mes in MESES:
        for ab, bis, k in fs:
            if ab <= mes <= bis and k and tipo[k] == "FIXO":
                q, v = gab.get((k, mes), (0, 0.0))
                gab[(k, mes)] = (q + 1, v + float(preco(k, mes)))
parc = {k: p for k, p, _ in EKON}
grava("esperado_cip", ["cod_concessao", "cod_parceiro_prefeitura", "mes_referencia", "qtd_instalacoes_ativas", "valor_cip_esperado"],
      [[k, parc[k], d(m), q, f"{v:.2f}"] for (k, m), (q, v) in sorted(gab.items())])
tot = {}
for (k, m), (q, v) in gab.items(): tot[parc[k]] = tot.get(parc[k], 0) + v
for p, v in sorted(tot.items()): print(f"  prefeitura {p}: R$ {v:.2f}")
print("total esperado no ano: R$ %.2f" % sum(v for _, v in gab.values()))

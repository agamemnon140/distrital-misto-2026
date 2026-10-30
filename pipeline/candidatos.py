"""Candidatos a deputado federal 2026 (consulta_cand pos-totalizacao) + totais por UF.

Saidas:
  TRAB/candidatos.parquet  uf, nr, nome, partido (nr), sigla, agr, eleito_real (bool), situacao
  TRAB/totais_uf.parquet   uf, agr, partido, nominal, legenda
"""
from __future__ import annotations

import json
import zipfile

import pandas as pd

from .caminhos import APURACAO, BRUTO_TSE, TRAB

PARTIDOS = json.loads((APURACAO / "config" / "partidos.json").read_text("utf-8"))
FED = {nr: nome for nome, nrs in PARTIDOS["federacoes"]["2026"].items() for nr in nrs}
SIGLA = {nr: p["sigla"] for nr, p in PARTIDOS["partidos"]["2026"].items()}
CAMPO = {nr: p["eixo"] for nr, p in PARTIDOS["partidos"]["2026"].items()}
COR = {nr: p["cor"] for nr, p in PARTIDOS["partidos"]["2026"].items()}


def agr(partido: str) -> str:
    return FED.get(partido, partido)


def candidatos() -> pd.DataFrame:
    z = zipfile.ZipFile(BRUTO_TSE / "2026" / "consulta_cand_2026_pos.zip")
    d = pd.concat([pd.read_csv(z.open(n), sep=";", encoding="latin-1", dtype=str)
                   for n in z.namelist() if n.endswith(".csv") and "BRASIL" not in n])
    d = d[d["DS_CARGO"].str.upper() == "DEPUTADO FEDERAL"]
    s = d["DS_SIT_TOT_TURNO"].str.upper()
    out = pd.DataFrame({"uf": d["SG_UF"], "nr": d["NR_CANDIDATO"], "nome": d["NM_URNA_CANDIDATO"].str.title(),
                        "partido": d["NR_PARTIDO"], "eleito_real": s.str.startswith("ELEITO"),
                        "situacao": d["DS_SIT_TOT_TURNO"]})
    out["sigla"] = out["partido"].map(SIGLA).fillna(d["SG_PARTIDO"])
    out["agr"] = out["partido"].map(agr)
    return (out.sort_values("eleito_real", ascending=False)
               .drop_duplicates(["uf", "nr"]).reset_index(drop=True))


def destinos() -> pd.DataFrame:
    """Destino oficial do voto de cada candidato (votacao_candidato_munzona): 'Valido',
    'Valido (legenda)' (conta para a agremiacao, candidato nao assume) ou 'Anulado sub judice'
    / 'Anulado' (nao conta para ninguem)."""
    z = zipfile.ZipFile(BRUTO_TSE / "2026" / "votacao_candidato_munzona_2026.zip")
    cols = ["SG_UF", "DS_CARGO", "NR_CANDIDATO", "NM_TIPO_DESTINACAO_VOTOS"]
    partes = []
    for n in z.namelist():
        if n.endswith(".csv") and not n.endswith(("_BRASIL.csv", "_BR.csv")):
            d = pd.read_csv(z.open(n), sep=";", encoding="latin-1", usecols=cols, dtype=str)
            d = d[d["DS_CARGO"].str.upper() == "DEPUTADO FEDERAL"]
            partes.append(d.drop_duplicates(["SG_UF", "NR_CANDIDATO"]))
    d = pd.concat(partes)
    return pd.DataFrame({"uf": d["SG_UF"], "nr": d["NR_CANDIDATO"], "destino": d["NM_TIPO_DESTINACAO_VOTOS"]})


def totais(cand: pd.DataFrame) -> pd.DataFrame:
    d = pd.read_parquet(TRAB / "depfed_local.parquet")
    d = d[~d["nr"].isin(["95", "96"])]
    g = d.groupby(["uf", "nr"], as_index=False)["votos"].sum()
    g["partido"] = g["nr"].str[:2]
    g["tipo"] = g["nr"].str.len().map(lambda n: "legenda" if n == 2 else "nominal")
    t = g.pivot_table(index=["uf", "partido"], columns="tipo", values="votos", aggfunc="sum", fill_value=0).reset_index()
    t.columns.name = None
    t["agr"] = t["partido"].map(agr)
    return t


def main() -> None:
    c = candidatos().merge(destinos(), on=["uf", "nr"], how="left")
    c["destino"] = c["destino"].fillna("Válido")
    c["vale_agr"] = c["destino"].str.startswith("Válido")      # voto conta para a agremiacao
    c["elegivel"] = c["destino"] == "Válido"                   # candidato pode assumir
    print(c.groupby("destino").size().to_dict())
    c.to_parquet(TRAB / "candidatos.parquet", index=False)
    t = totais(c)
    t.to_parquet(TRAB / "totais_uf.parquet", index=False)
    print(f"{len(c):,} candidatos, {c['eleito_real'].sum()} eleitos reais; "
          f"validos {int(t[['nominal','legenda']].sum().sum()):,} (legenda {int(t['legenda'].sum()):,})")


if __name__ == "__main__":
    main()

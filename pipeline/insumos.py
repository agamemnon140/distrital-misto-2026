"""Compila o voto de 2026 por LOCAL DE VOTACAO (uf, municipio TSE, zona, local).

Saidas em TRAB:
  depfed_local.parquet   uf, mun, zona, local, nr (str: 2 dig = legenda, 4-5 = candidato), votos
  pres2t_local.parquet   uf, mun, zona, local, lula, flavio, branco, nulo (arquivo _BR)
  aptos_local.parquet    uf, mun, zona, local, aptos (deputado federal, 1o turno)

Uso:  py -m pipeline.insumos [UF ...]
"""
from __future__ import annotations

import sys
import time
import zipfile

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv

from .caminhos import BRUTO_TSE, TRAB, UFS

S, I = pa.string(), pa.int64()
COLS = {"SG_UF": S, "CD_MUNICIPIO": I, "NR_ZONA": I, "NR_TURNO": I, "DS_CARGO": S,
        "DT_ELEICAO": S, "NR_VOTAVEL": S, "QT_VOTOS": I, "NR_LOCAL_VOTACAO": I}
DET = {"SG_UF": S, "CD_MUNICIPIO": I, "NR_ZONA": I, "NR_TURNO": I, "DS_CARGO": S,
       "QT_APTOS": I, "NR_LOCAL_VOTACAO": I}
CHAVE = ["mun", "zona", "local"]


def lotes(zpath, colunas, so=None):
    z = zipfile.ZipFile(zpath)
    for nome in z.namelist():
        if not nome.lower().endswith(".csv") or nome.endswith("_BRASIL.csv"):
            continue
        if so and not nome.endswith(f"_{so}.csv"):
            continue
        with z.open(nome) as fh:
            rd = pacsv.open_csv(fh, read_options=pacsv.ReadOptions(encoding="latin1", block_size=16 << 20),
                                parse_options=pacsv.ParseOptions(delimiter=";"),
                                convert_options=pacsv.ConvertOptions(column_types=colunas,
                                                                     include_columns=list(colunas)))
            for b in rd:
                yield pa.Table.from_batches([b])


def agrega(partes: list[pd.DataFrame], chave: list[str]) -> pd.DataFrame:
    d = pd.concat(partes, ignore_index=True)
    return d.groupby(chave, as_index=False, sort=False)["votos"].sum()


def _por_local(t: pa.Table, chave_uf: bool = False) -> pd.DataFrame:
    cols = (["SG_UF"] if chave_uf else []) + ["CD_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO", "NR_VOTAVEL", "QT_VOTOS"]
    d = t.select(cols).to_pandas()
    d.columns = (["uf"] if chave_uf else []) + CHAVE + ["nr", "votos"]
    return d.groupby(list(d.columns[:-1]), as_index=False, sort=False)["votos"].sum()


def compila_uf(uf: str) -> pd.DataFrame:
    dep = []
    for t in lotes(BRUTO_TSE / "2026" / f"votacao_secao_2026_{uf}.zip", COLS):
        t = t.filter(pc.ends_with(t["DT_ELEICAO"], "2026"))
        f = t.filter(pc.and_(pc.equal(pc.utf8_upper(t["DS_CARGO"]), "DEPUTADO FEDERAL"),
                             pc.equal(t["NR_TURNO"], 1)))
        if f.num_rows:
            dep.append(_por_local(f))
    dep = agrega(dep, CHAVE + ["nr"])
    dep.insert(0, "uf", uf)
    return dep


def presidente_2t() -> pd.DataFrame:
    """Presidente vem no arquivo _BR (eleicao federal), nao nos arquivos por UF."""
    partes = []
    for t in lotes(BRUTO_TSE / "2026" / "votacao_secao_2026_BR.zip", COLS):
        t = t.filter(pc.and_(pc.equal(t["NR_TURNO"], 2), pc.ends_with(t["DT_ELEICAO"], "2026")))
        if t.num_rows:
            partes.append(_por_local(t, chave_uf=True))
    p = agrega(partes, ["uf"] + CHAVE + ["nr"])
    p = p[p["uf"] != "ZZ"]                               # exterior nao entra em distrito
    p["nr"] = p["nr"].map({"13": "lula", "22": "flavio", "95": "branco", "96": "nulo"}).fillna("outro")
    p = p.pivot_table(index=["uf"] + CHAVE, columns="nr", values="votos", aggfunc="sum", fill_value=0).reset_index()
    p.columns.name = None
    return p


def aptos() -> pd.DataFrame:
    partes = []
    for t in lotes(BRUTO_TSE / "2026" / "detalhe_votacao_secao_2026.zip", DET):
        cargo = pc.utf8_upper(t["DS_CARGO"])
        t = t.filter(pc.and_(pc.equal(cargo, "DEPUTADO FEDERAL"), pc.equal(t["NR_TURNO"], 1)))
        if t.num_rows:
            d = t.select(["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO", "QT_APTOS"]).to_pandas()
            d.columns = ["uf"] + CHAVE + ["votos"]
            partes.append(d.groupby(["uf"] + CHAVE, as_index=False)["votos"].sum())
    a = agrega(partes, ["uf"] + CHAVE).rename(columns={"votos": "aptos"})
    return a


def main() -> None:
    ufs = sys.argv[1:] or UFS
    deps = []
    for uf in ufs:
        t0 = time.time()
        deps.append(compila_uf(uf))
        print(f"{uf}: {len(deps[-1]):>9,} linhas dep  ({time.time()-t0:.0f}s)", flush=True)
    sufixo = "" if not sys.argv[1:] else "_" + "_".join(ufs)
    pd.concat(deps).to_parquet(TRAB / f"depfed_local{sufixo}.parquet", index=False)
    if not sys.argv[1:]:
        p = presidente_2t()
        p.to_parquet(TRAB / "pres2t_local.parquet", index=False)
        print(f"2T: {len(p):,} locais, lula {p['lula'].sum():,} flavio {p['flavio'].sum():,}", flush=True)
        a = aptos()
        a.to_parquet(TRAB / "aptos_local.parquet", index=False)
        print(f"aptos: {len(a):,} locais, {a['aptos'].sum():,} eleitores", flush=True)


if __name__ == "__main__":
    main()

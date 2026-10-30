"""Votos por distrito, para cada mapa amostrado, e o emparelhamento candidato x distrito.

Por UF e k (numero de distritos) e para cada um dos N_MAPAS mapas:
  - soma, por distrito, os votos validos de cada candidato e a legenda de cada agremiacao;
  - escolhe o candidato de cada agremiacao em cada distrito (emparelhamento guloso: pares
    (candidato, distrito) em ordem decrescente do voto do candidato ali; cada candidato fica com
    um distrito so, e cada agremiacao com um candidato por distrito). Nao depende de alfa/beta,
    por isso fica pronto aqui;
  - guarda eleitorado, populacao (Censo 2022, rateada pelo eleitorado) e 2o turno presidencial.

Saida: TRAB/matrizes/{UF}_k{k}.pkl
"""
from __future__ import annotations

import pickle
import sys
import time

import numpy as np
import pandas as pd
from scipy import sparse

from .caminhos import ELEICOES, TRAB, UFS
from .mapas import ks_da_uf

SAIDA = TRAB / "matrizes"
SAIDA.mkdir(parents=True, exist_ok=True)

_CACHE: dict = {}


def _base():
    if not _CACHE:
        _CACHE["dep"] = pd.read_parquet(TRAB / "depfed_local.parquet")
        _CACHE["pres"] = pd.read_parquet(TRAB / "pres2t_local.parquet")
        _CACHE["cand"] = pd.read_parquet(TRAB / "candidatos.parquet")
        b = pd.read_parquet(ELEICOES / "analise" / "dados" / "base_2022_mun.parquet", columns=["cd_mun", "pop_2022"])
        a = pd.read_parquet(ELEICOES / "dados-secao" / "sintetico" / "municipio_atributos_2022.parquet",
                            columns=["cd_mun", "cd_municipio_tse"]).dropna()
        a["cd_mun"] = a["cd_mun"].astype(str)
        b["cd_mun"] = b["cd_mun"].astype(str)
        m = a.merge(b, on="cd_mun")
        _CACHE["pop"] = dict(zip(m["cd_municipio_tse"].astype(int), m["pop_2022"]))
    return _CACHE


def insumos(uf: str) -> dict:
    """Matrizes por tijolo de uma UF."""
    B = _base()
    with open(TRAB / "tijolos" / f"{uf}.pkl", "rb") as fh:
        t = pickle.load(fh)
    nos = t["nos"]
    n = len(nos)
    no_de: dict[tuple, int] = {}
    for i, no in enumerate(nos):
        for k in no["membros"]:
            no_de[k] = i
    # fallback: local sem cadastro -> tijolo da mesma zona/municipio com mais eleitores
    maior_zona, maior_mun = {}, {}
    for i, no in enumerate(nos):
        for (m, z, _l) in no["membros"]:
            if no["aptos"] > nos[maior_zona.get((m, z), i)]["aptos"] or (m, z) not in maior_zona:
                maior_zona[(m, z)] = i
            if (m not in maior_mun) or no["aptos"] > nos[maior_mun[m]]["aptos"]:
                maior_mun[m] = i

    def no_do_local(m, z, l):
        return no_de.get((m, z, l), maior_zona.get((m, z), maior_mun.get(m, -1)))

    cand = B["cand"][B["cand"]["uf"] == uf]
    vale = dict(zip(cand["nr"], cand["vale_agr"]))
    agr_de = dict(zip(cand["nr"], cand["agr"]))
    from .candidatos import agr as agr_do_partido

    d = B["dep"][B["dep"]["uf"] == uf]
    d = d[~d["nr"].isin(["95", "96"])]
    d = d[[len(x) == 2 or vale.get(x, True) for x in d["nr"]]]           # anulados fora
    no_idx = np.array([no_do_local(m, z, l) for m, z, l in zip(d["mun"], d["zona"], d["local"])])
    perdidos = int(d["votos"].values[no_idx < 0].sum())
    if perdidos:
        print(f"  {uf}: {perdidos:,} votos sem tijolo")
    d = d.assign(no=no_idx)[no_idx >= 0]

    cands = cand[cand["elegivel"]].copy()
    tot = d.groupby("nr")["votos"].sum()
    cands["votos"] = cands["nr"].map(tot).fillna(0).astype(int)
    agrs = sorted(set(d["nr"].map(lambda x: agr_de.get(x, agr_do_partido(x[:2])))))
    idx_a = {a: i for i, a in enumerate(agrs)}
    cands = cands[(cands["votos"] > 0) & cands["agr"].isin(idx_a)]
    cands = cands.sort_values("votos", ascending=False).reset_index(drop=True)
    idx_c = {nr: i for i, nr in enumerate(cands["nr"])}
    d_agr = d["nr"].map(lambda x: agr_de.get(x, agr_do_partido(x[:2])))
    # total da agremiacao por tijolo (nominal valido + legenda)
    A = sparse.coo_matrix((d["votos"].values, (d["no"].values, d_agr.map(idx_a).values)),
                          shape=(n, len(agrs))).tocsr()
    nom = d[d["nr"].isin(idx_c)]
    C = sparse.coo_matrix((nom["votos"].values, (nom["no"].values, nom["nr"].map(idx_c).values)),
                          shape=(n, len(cands))).tocsr()

    p = B["pres"][B["pres"]["uf"] == uf]
    pi = np.array([no_do_local(m, z, l) for m, z, l in zip(p["mun"], p["zona"], p["local"])])
    lula = np.bincount(pi[pi >= 0], weights=p["lula"].values[pi >= 0], minlength=n)
    flavio = np.bincount(pi[pi >= 0], weights=p["flavio"].values[pi >= 0], minlength=n)

    aptos = np.array([no["aptos"] for no in nos], dtype=float)
    # populacao: municipio rateado pelo eleitorado de cada local
    ap_mun: dict[int, float] = {}
    from .tijolos import locais_2026
    L = locais_2026()
    L = L[L["uf"] == uf]
    loc_ap = dict(zip(zip(L["mun"], L["zona"], L["local"]), L["aptos"]))
    for (m, z, l), a in loc_ap.items():
        ap_mun[m] = ap_mun.get(m, 0) + a
    razao_uf = sum(B["pop"].get(m, 0) for m in ap_mun) / max(1, sum(a for m, a in ap_mun.items() if m in B["pop"]))
    pop = np.zeros(n)
    for i, no in enumerate(nos):
        for k in no["membros"]:
            m = k[0]
            a = loc_ap.get(k, 0)
            pop[i] += B["pop"][m] * a / ap_mun[m] if m in B["pop"] and ap_mun.get(m) else a * razao_uf
    return {"uf": uf, "n": n, "cands": cands, "agrs": agrs, "A": A, "C": C, "lula": lula,
            "tot_agr": np.asarray(A.sum(axis=0)).ravel(),
            "flavio": flavio, "aptos": aptos, "pop": pop,
            "cand_agr": np.array([idx_a.get(a, -1) for a in cands["agr"]])}


def emparelha(Vc: np.ndarray, cand_agr: np.ndarray, n_agr: int) -> np.ndarray:
    """Vc [k, n_cand] votos do candidato em cada distrito -> escolhido[k, n_agr] (indice ou -1)."""
    k = Vc.shape[0]
    escolhido = -np.ones((k, n_agr), dtype=np.int32)
    for a in range(n_agr):
        cs = np.flatnonzero(cand_agr == a)
        if len(cs) == 0:
            continue
        sub = Vc[:, cs]
        ordem = np.argsort(-sub, axis=None, kind="stable")
        usado = set()
        livres = k
        for flat in ordem:
            d, j = divmod(int(flat), len(cs))
            if sub[d, j] <= 0:
                break
            if escolhido[d, a] >= 0 or j in usado:
                continue
            escolhido[d, a] = cs[j]
            usado.add(j)
            livres -= 1
            if livres == 0 or len(usado) == len(cs):
                break
    return escolhido


def processa(uf: str, k: int, ins: dict) -> dict:
    mapas = np.load(TRAB / "mapas" / f"{uf}_k{k}.npy")
    n_agr = len(ins["agrs"])
    G = sparse.coo_matrix((np.ones(len(ins["cand_agr"])), (np.arange(len(ins["cand_agr"])), ins["cand_agr"])),
                          shape=(len(ins["cand_agr"]), n_agr)).tocsr()       # candidato -> agremiacao
    saida = []
    for m in mapas:
        P = sparse.coo_matrix((np.ones(ins["n"]), (m, np.arange(ins["n"]))), shape=(k, ins["n"])).tocsr()
        Va = (P @ ins["A"]).toarray()
        Vc = (P @ ins["C"]).toarray()
        esc = emparelha(Vc, ins["cand_agr"], n_agr)
        own = np.where(esc >= 0, np.take_along_axis(Vc, np.maximum(esc, 0), axis=1), 0)
        saida.append({"Va": Va.astype(np.int64), "esc": esc, "own": own.astype(np.int64),
                      "nom": np.asarray(Vc @ G).astype(np.int64),
                      "aptos": P @ ins["aptos"], "pop": P @ ins["pop"],
                      "lula": P @ ins["lula"], "flavio": P @ ins["flavio"]})
    return {"mapas": mapas, "dist": saida}


def main() -> None:
    for uf in sys.argv[1:] or UFS:
        t0 = time.time()
        ins = insumos(uf)
        res = {"ins": {k: v for k, v in ins.items() if k not in ("A", "C")}, "por_k": {}}
        res["ins"]["aptos_tij"] = ins["aptos"]
        for k in ks_da_uf(uf):
            res["por_k"][k] = processa(uf, k, ins)
        # conferencia: com qualquer mapa, a soma dos distritos = total estadual por agremiacao
        tot = np.asarray(ins["A"].sum(axis=0)).ravel()
        for k, r in res["por_k"].items():
            assert np.allclose(r["dist"][0]["Va"].sum(axis=0), tot), (uf, k)
        with open(SAIDA / f"{uf}.pkl", "wb") as fh:
            pickle.dump(res, fh)
        print(f"{uf}: {len(ins['cands'])} candidatos, {len(ins['agrs'])} agremiacoes, ks {list(res['por_k'])} "
              f"({time.time()-t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()

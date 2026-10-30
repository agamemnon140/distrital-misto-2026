"""Validacao: a regra brasileira com 100% das cadeiras reproduz os eleitos reais de 2026?

Destino do voto oficial (votacao_candidato_munzona): 'Valido (legenda)' conta para a agremiacao
mas o candidato nao assume (art. 175 par. 4o); 'Anulado sub judice' nao conta para ninguem.

Uso:  py -m pipeline.valida
"""
from __future__ import annotations

import pandas as pd

from .caminhos import TRAB
from .quociente import brasil
from .rateio import ATUAL


def insumos_uf():
    cand = pd.read_parquet(TRAB / "candidatos.parquet")
    d = pd.read_parquet(TRAB / "depfed_local.parquet")
    d = d[~d["nr"].isin(["95", "96"])]
    g = d.groupby(["uf", "nr"], as_index=False)["votos"].sum()
    eleg = dict(zip(zip(cand["uf"], cand["nr"]), cand["elegivel"]))
    vale = dict(zip(zip(cand["uf"], cand["nr"]), cand["vale_agr"]))
    g = g[[len(n) == 2 or vale.get((u, n), True) for u, n in zip(g["uf"], g["nr"])]]
    eh_nulo = [len(n) > 2 and not eleg.get((u, n), True) for u, n in zip(g["uf"], g["nr"])]
    agr_de = dict(zip(zip(cand["uf"], cand["nr"]), cand["agr"]))
    from .candidatos import agr
    out = {}
    g["nulo"] = eh_nulo
    for uf, gu in g.groupby("uf"):
        nom = {n: float(v) for n, v, z in zip(gu["nr"], gu["votos"], gu["nulo"]) if len(n) > 2 and not z}
        votos_agr: dict[str, float] = {}
        for n, v in zip(gu["nr"], gu["votos"]):
            a = agr_de.get((uf, n), agr(n[:2]))
            votos_agr[a] = votos_agr.get(a, 0) + float(v)
        out[uf] = (votos_agr, nom, lambda nr, uf=uf: agr_de.get((uf, nr), agr(nr[:2])))
    return out, cand


def main() -> None:
    ins, cand = insumos_uf()
    real = cand[cand["eleito_real"]]
    erro = 0
    for uf, (va, nom, f) in sorted(ins.items()):
        e = set(brasil(va, nom, ATUAL[uf], f))
        r = set(real.loc[real["uf"] == uf, "nr"])
        if e != r:
            erro += 1
            nomes = dict(zip(cand.loc[cand.uf == uf, "nr"], cand.loc[cand.uf == uf, "nome"] + " (" + cand.loc[cand.uf == uf, "sigla"] + ")"))
            print(f"{uf}: {len(e & r)}/{ATUAL[uf]} iguais | so simulado: {[nomes.get(x, x) for x in e - r]} "
                  f"| so real: {[nomes.get(x, x) for x in r - e]}")
    print(f"{27 - erro}/27 UFs reproduzidas exatamente")


if __name__ == "__main__":
    main()

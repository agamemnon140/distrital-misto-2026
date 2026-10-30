"""Posicao de cada agremiacao no espectro esquerda-direita (0-10) e os vizinhos que coordenam.

Notas por partido: config/espectro.json (pesquisa com especialistas, rodada 2022). A federacao fica
na media das suas siglas ponderada pelo voto para deputado federal de 2026 no pais.

Coordenacao: duas agremiacoes sao "vizinhas" -- e dividem os distritos em vez de lancar candidato
forte no mesmo -- quando estao a ate LIMIAR pontos uma da outra.
"""
from __future__ import annotations

import json
from functools import lru_cache

import pandas as pd

from .caminhos import RAIZ, TRAB

LIMIARES = (1.0, 1.5, 2.1, 2.5)


@lru_cache(maxsize=1)
def notas() -> dict[str, float]:
    return {k: float(v) for k, v in json.loads((RAIZ / "config" / "espectro.json").read_text("utf-8"))["notas"].items()}


@lru_cache(maxsize=1)
def posicoes() -> dict[str, float]:
    """agremiacao (id) -> posicao 0-10."""
    from .candidatos import FED, SIGLA
    d = pd.read_parquet(TRAB / "depfed_local.parquet", columns=["nr", "votos"])
    d = d[~d["nr"].isin(["95", "96"])]
    votos = d.groupby(d["nr"].str[:2])["votos"].sum().to_dict()
    nt = notas()
    out = {nr: nt[nr] for nr in SIGLA if nr in nt and nr not in FED}
    for fed in sorted(set(FED.values())):
        membros = [nr for nr, f in FED.items() if f == fed]
        peso = sum(votos.get(nr, 0) for nr in membros)
        out[fed] = sum(nt[nr] * votos.get(nr, 0) for nr in membros) / peso
    return out


def vizinhas(limiar: float) -> set[frozenset]:
    pos = posicoes()
    ids = sorted(pos)
    return {frozenset((a, b)) for i, a in enumerate(ids) for b in ids[i + 1:] if abs(pos[a] - pos[b]) <= limiar}


if __name__ == "__main__":
    for a, x in sorted(posicoes().items(), key=lambda p: p[1]):
        print(f"{a:18} {x:5.2f}")

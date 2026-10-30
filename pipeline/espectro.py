"""Posicao de cada agremiacao no espectro esquerda-direita (0-10) e os vizinhos que coordenam.

Notas por partido: config/espectro.json (pesquisa com especialistas, rodada 2022). A federacao fica
na media das suas siglas ponderada pelo voto para deputado federal de 2026 no pais.

Coordenacao: dois candidatos "se atrapalham" num distrito quando a forca do mais fraco dos dois --
voto esperado ali como candidato do partido (proprio + legenda + o que herda dos colegas) mais o voto
pessoal de novo, em fracao do distrito -- passa de um limite que cresce com a distancia entre os
partidos:
    limite(d) = t0 * (t2 / t0) ** (d / 2)
t0 = limite na distancia 0 (so um nome muito fraco convive com o partido-irmao) e t2 = limite na
distancia 2 (so se os dois forem realmente fortes). Quem e barrado por um partido a ate `dw` pontos
retira o partido do distrito; mais longe, o partido pode lancar um nome fraco que nao atrapalhe.
"""
from __future__ import annotations

import json
from functools import lru_cache

import pandas as pd

from .caminhos import RAIZ, TRAB

# intensidade da coordenacao: (t0, t2, dw)
# media: Samia (~15% esperado) x Tabata (~9%), a 2,07 pontos, se atrapalham; PT x PSOL tipicos (7-8%,
# a 1,21) tambem; Edilene (PSOL, ~2%) x Tabata nao
NIVEIS = {"baixa": (0.04, 0.12, 0.5), "media": (0.03, 0.08, 1.0), "alta": (0.02, 0.05, 1.5)}


def limite(d: float, t0: float, t2: float) -> float:
    return t0 * (t2 / t0) ** (d / 2)


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


if __name__ == "__main__":
    for a, x in sorted(posicoes().items(), key=lambda p: p[1]):
        print(f"{a:18} {x:5.2f}")

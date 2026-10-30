"""Amostra de mapas distritais por UF e numero de distritos k (ReCom, GerryChain).

Cada mapa: distritos conexos com eleitorado (aptos) a +-EPSILON da media do estado.
Semente: particao recursiva por arvore geradora; depois a cadeia ReCom anda AQUECIMENTO
passos e guarda um mapa a cada INTERVALO passos, ate N_MAPAS.

Saida: TRAB/mapas/{UF}_k{k}.npy  int16 [N_MAPAS, n_tijolos]

Uso:  py -m pipeline.mapas [UF ...]
"""
from __future__ import annotations

import pickle
import random
import sys
import time
from functools import partial

import networkx as nx
import numpy as np
from gerrychain import Graph, MarkovChain, Partition
from gerrychain.accept import always_accept
from gerrychain.constraints import within_percent_of_ideal_population
from gerrychain.proposals import recom
from gerrychain.tree import recursive_tree_part
from gerrychain.updaters import Tally, cut_edges

from .caminhos import TRAB, UFS
from .rateio import rateios

EPSILON = 0.10
N_MAPAS = 50
SAIDA = TRAB / "mapas"
SAIDA.mkdir(parents=True, exist_ok=True)


def ks_da_uf(uf: str) -> list[int]:
    return sorted({max(1, r[uf] // 2) for r in rateios().values()})


def grafo(uf: str) -> tuple[Graph, int]:
    t = pickle.load(open(TRAB / "tijolos" / f"{uf}.pkl", "rb"))
    G = nx.Graph()
    for i, n in enumerate(t["nos"]):
        G.add_node(i, aptos=n["aptos"])
    G.add_edges_from(t["arestas"])
    return Graph.from_networkx(G), len(t["nos"])


def semente(g: Graph, k: int, ideal: float, rng: random.Random) -> dict:
    for tentativa in range(20):
        try:
            return recursive_tree_part(g, range(k), ideal, "aptos", EPSILON * 0.8,
                                       node_repeats=3 + tentativa, rng=rng)
        except Exception as e:                       # noqa: BLE001 -- tenta de novo com outra arvore
            erro = e
    raise RuntimeError(f"sem semente valida: {erro}")


def amostra(uf: str, k: int, semente_rng: int = 2026) -> np.ndarray:
    g, n = grafo(uf)
    if k == 1:
        return np.zeros((N_MAPAS, n), dtype=np.int16)
    rng = random.Random(semente_rng * 100 + k)
    total = sum(g.node_data(v)["aptos"] for v in g.nodes)
    ideal = total / k
    ini = Partition(g, semente(g, k, ideal, rng), updaters={"population": Tally("aptos", alias="population"),
                                                             "cut_edges": cut_edges})
    proposta = partial(recom, pop_col="aptos", pop_target=ideal, epsilon=EPSILON, node_repeats=2, rng=rng)
    aquecimento = max(100, 10 * k)
    intervalo = max(10, 2 * k)
    passos = aquecimento + intervalo * N_MAPAS
    cadeia = MarkovChain(proposta, constraints=[within_percent_of_ideal_population(ini, EPSILON)],
                         accept=always_accept, initial_state=ini, total_steps=passos)
    mapas = []
    for i, part in enumerate(cadeia):
        if i >= aquecimento and (i - aquecimento) % intervalo == intervalo - 1:
            a = np.zeros(n, dtype=np.int16)
            for v, d in part.assignment.items():
                a[v] = d
            mapas.append(a)
    return np.array(mapas[:N_MAPAS])


def main() -> None:
    for uf in sys.argv[1:] or UFS:
        for k in ks_da_uf(uf):
            arq = SAIDA / f"{uf}_k{k}.npy"
            if arq.exists():
                continue
            t0 = time.time()
            m = amostra(uf, k)
            np.save(arq, m)
            print(f"{uf} k={k:>3}: {m.shape[0]} mapas, {m.shape[1]} tijolos  ({time.time()-t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()

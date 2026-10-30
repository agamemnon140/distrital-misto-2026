"""Mapas: todo distrito e conexo, fica a +-10% do eleitorado medio do estado, e o numero de
distritos bate com floor(cadeiras/2) em cada rateio.  Uso:  python -m pytest tests"""
from __future__ import annotations

import pickle

import networkx as nx
import numpy as np
import pytest

from pipeline.caminhos import TRAB, UFS
from pipeline.mapas import EPSILON, ks_da_uf
from pipeline.rateio import rateios


@pytest.mark.parametrize("uf", UFS)
def test_mapas_validos(uf):
    with open(TRAB / "tijolos" / f"{uf}.pkl", "rb") as fh:
        t = pickle.load(fh)
    G = nx.Graph()
    G.add_nodes_from(range(len(t["nos"])))
    G.add_edges_from(t["arestas"])
    aptos = np.array([n["aptos"] for n in t["nos"]])
    for k in ks_da_uf(uf):
        mapas = np.load(TRAB / "mapas" / f"{uf}_k{k}.npy")
        assert mapas.shape == (50, len(t["nos"]))
        ideal = aptos.sum() / k
        for m in mapas:
            assert set(np.unique(m)) == set(range(k))
            pop = np.bincount(m, weights=aptos, minlength=k)
            assert np.all(np.abs(pop / ideal - 1) <= EPSILON + 1e-9), (uf, k, pop / ideal)
            for d in range(k):
                assert nx.is_connected(G.subgraph(np.flatnonzero(m == d))), (uf, k, d)


def test_numero_de_distritos():
    for nome, r in rateios().items():
        for uf in UFS:
            assert max(1, r[uf] // 2) in ks_da_uf(uf)
    assert sum(r // 2 for r in rateios()["atual"].values()) == 253


def test_eleitorado_conservado():
    """Nenhum local de votacao se perde na montagem dos tijolos (cadastro de 06/09/2026)."""
    from pipeline.tijolos import locais_2026
    a = locais_2026().groupby("uf")["aptos"].sum()
    for uf in UFS:
        with open(TRAB / "tijolos" / f"{uf}.pkl", "rb") as fh:
            t = pickle.load(fh)
        tot = sum(n["aptos"] for n in t["nos"])
        assert tot == a[uf], (uf, tot, a[uf])

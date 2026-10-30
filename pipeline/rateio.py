"""Tres rateios das 513 cadeiras entre os estados (Censo 2022, maiores restos).

  atual     tabela vigente (piso 8, teto 70; a de 2022, nao atualizada pelo Censo)
  sem_teto  piso 8, sem teto
  puro      proporcional puro, piso 1
"""
from __future__ import annotations

import json

import pandas as pd

from .caminhos import ELEICOES, SAIDA_WEB

TOTAL = 513
ATUAL = {"SP": 70, "MG": 53, "RJ": 46, "BA": 39, "RS": 31, "PR": 30, "PE": 25, "CE": 22,
         "MA": 18, "GO": 17, "PA": 17, "SC": 16, "PB": 12, "ES": 10, "PI": 10, "AL": 9,
         "AC": 8, "AM": 8, "AP": 8, "DF": 8, "MS": 8, "MT": 8, "RN": 8, "RO": 8,
         "RR": 8, "SE": 8, "TO": 8}
RATEIOS = ["atual", "sem_teto", "puro"]


def populacao() -> dict[str, int]:
    b = pd.read_parquet(ELEICOES / "analise" / "dados" / "base_2022_mun.parquet", columns=["uf", "pop_2022"])
    return {uf: int(v) for uf, v in b.groupby("uf")["pop_2022"].sum().items()}


def maiores_restos(pop: dict[str, int], total: int, piso: int) -> dict[str, int]:
    """Hamilton com piso: quem fica abaixo do piso recebe o piso e sai da conta; repete."""
    fixos: dict[str, int] = {}
    while True:
        livres = {u: p for u, p in pop.items() if u not in fixos}
        vagas = total - sum(fixos.values())
        q = sum(livres.values()) / vagas
        cota = {u: p / q for u, p in livres.items()}
        abaixo = {u for u, c in cota.items() if c < piso}
        if not abaixo:
            break
        fixos.update({u: piso for u in abaixo})
    base = {u: int(c) for u, c in cota.items()}
    sobra = vagas - sum(base.values())
    for u in sorted(cota, key=lambda u: -(cota[u] - base[u]))[:sobra]:
        base[u] += 1
    return {**fixos, **base}


def rateios() -> dict[str, dict[str, int]]:
    pop = populacao()
    return {"atual": dict(ATUAL),
            "sem_teto": maiores_restos(pop, TOTAL, 8),
            "puro": maiores_restos(pop, TOTAL, 1)}


def main() -> None:
    r = rateios()
    pop = populacao()
    for nome, t in r.items():
        assert sum(t.values()) == TOTAL, (nome, sum(t.values()))
    SAIDA_WEB.mkdir(parents=True, exist_ok=True)
    (SAIDA_WEB / "rateios.json").write_text(json.dumps({"pop": pop, "rateios": r}, ensure_ascii=False), "utf-8")
    print(f"{'UF':3s} {'pop':>11s} " + " ".join(f"{n:>8s}" for n in r))
    for uf in sorted(pop, key=lambda u: -pop[u]):
        print(f"{uf:3s} {pop[uf]:>11,} " + " ".join(f"{r[n][uf]:>8d}" for n in r))


if __name__ == "__main__":
    main()

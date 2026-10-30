"""Alocadores de cadeiras proporcionais dentro de um estado.

`brasil()` e o `aloca()` de apuracao-2t-2026/pipeline/quociente.py (regras pos-EC 111/2021,
com a 3a fase das sobras aberta a todos quando ninguem cumpre 80%/20% -- STF, ADIs 7228,
7263 e 7325), com o QE calculado sobre o numero de vagas recebido. `dhondt()` e a
alternativa sem barreira. Os dois devolvem a lista de candidatos eleitos, em ordem.

Entrada comum:
  votos_agr  {agremiacao: votos validos (nominal + legenda)}
  nominais   {nr_candidato: votos} -- so os candidatos que PODEM levar a vaga
  agr_de     funcao nr_candidato -> agremiacao
"""
from __future__ import annotations

from collections.abc import Callable


def qe_oficial(validos: float, cadeiras: int) -> int:
    q = validos / cadeiras
    inteiro = int(q)
    return inteiro + 1 if (q - inteiro) > 0.5 else max(inteiro, 1)


def _por_agr(nominais, agr_de):
    por: dict[str, list[str]] = {}
    for nr in sorted(nominais, key=lambda n: (-nominais[n], n)):
        por.setdefault(agr_de(nr), []).append(nr)
    return por


def brasil(votos_agr: dict[str, float], nominais: dict[str, float], vagas: int,
           agr_de: Callable[[str], str], validos: float | None = None) -> list[str]:
    if vagas <= 0:
        return []
    validos = validos if validos is not None else sum(votos_agr.values())
    qe = qe_oficial(validos, vagas)
    por_agr = _por_agr(nominais, agr_de)
    eleitos: list[str] = []
    ja = set()
    obtidas = {a: 0 for a in votos_agr}

    for a, v in votos_agr.items():                         # 1) quociente partidario
        qp = int(v // qe)
        leva = [nr for nr in por_agr.get(a, []) if nominais[nr] >= 0.10 * qe][:qp]
        eleitos += leva
        ja.update(leva)
        obtidas[a] = len(leva)

    def melhor(a: str, piso: float) -> str | None:
        for nr in por_agr.get(a, []):
            if nr not in ja and nominais[nr] >= piso:
                return nr
        return None

    # 2) sobras: maior media entre quem tem >= 80% do QE e candidato com >= 20% do QE;
    # 3) se ninguem cumpre os dois pisos, as vagas restantes vao por maior media entre todas
    #    as agremiacoes, sem pisos (STF, ADIs 7228/7263/7325)
    while len(eleitos) < vagas:
        com_piso = [(votos_agr[a] / (obtidas[a] + 1), a) for a in votos_agr
                    if votos_agr[a] >= 0.80 * qe and melhor(a, 0.20 * qe)]
        if com_piso:
            _, a = max(com_piso)
            nr = melhor(a, 0.20 * qe)
        else:
            livres = [(votos_agr[a] / (obtidas[a] + 1), a) for a in votos_agr if melhor(a, 0.0)]
            if not livres:
                break
            _, a = max(livres)
            nr = melhor(a, 0.0)
        eleitos.append(nr)
        ja.add(nr)
        obtidas[a] += 1
    return eleitos


def dhondt_cadeiras(votos_agr: dict[str, float], vagas: int) -> dict[str, int]:
    c = {a: 0 for a in votos_agr}
    for _ in range(vagas):
        a = max(votos_agr, key=lambda a: (votos_agr[a] / (c[a] + 1), a))
        c[a] += 1
    return c


def dhondt(votos_agr: dict[str, float], nominais: dict[str, float], vagas: int,
           agr_de: Callable[[str], str], validos: float | None = None) -> list[str]:
    por_agr = _por_agr(nominais, agr_de)
    vot = {a: v for a, v in votos_agr.items() if por_agr.get(a)}
    c = {a: 0 for a in vot}
    eleitos = []
    for _ in range(vagas):
        cand = [a for a in vot if c[a] < len(por_agr[a])]
        if not cand:
            break
        a = max(cand, key=lambda a: (vot[a] / (c[a] + 1), a))
        eleitos.append(por_agr[a][c[a]])
        c[a] += 1
    return eleitos


REGRAS = {"brasil": brasil, "dhondt": dhondt}

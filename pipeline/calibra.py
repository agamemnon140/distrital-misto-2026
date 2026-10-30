"""Calibra o voto util (beta, dentro do campo) e a polarizacao (pi, entre campos) com as eleicoes
de prefeito de 2024 em turno unico.

Em municipio com menos de 200 mil eleitores o prefeito sai num turno so, por maioria simples: e o
mesmo jogo do distrito. O simulador poe todas as agremiacoes na disputa, entao o analogo e o
"desenho sem coligacao": cada partido/federacao vira um candidato com o seu voto para vereador,
e o modelo tem de levar essa dispersao ate a concentracao real da eleicao de prefeito.

Regra (a mesma de js/aloca.js):
  beta: quem fica do 3o lugar para baixo e nao lidera o proprio campo passa beta dos votos ao
        mais bem colocado do campo;
  pi:   depois disso, todo mundo do 3o lugar para baixo passa pi dos votos que restam a um dos
        dois primeiros -- o de campo mais proximo (esquerda-centro-direita); empate (ou campo
        desconhecido) divide na proporcao dos dois.

Dois momentos. (1) A fatia dos dois primeiros: e o alvo. Ela sozinha nao separa beta de pi (ha
uma curva de pares que a reproduzem). (2) A votacao de cada campo: beta nao a muda (so mexe dentro
do campo); pi muda. Entre os pares da curva, fica o que erra menos a votacao por campo.

Amostra: cidades de 60 a 170 mil eleitores -- as mais parecidas com um distrito (que tem ~600
mil), com 4 a 5 candidatos em media. A concentracao cai com o tamanho da cidade (tabela por
faixa vai junto). Usa o eleitorado de 2026 como aproximacao do de 2024 e exclui a faixa de
170-230 mil, onde nao da para saber se houve 2o turno.

Saida: docs/dados/calibra.json
"""
from __future__ import annotations

import json
import zipfile

import numpy as np
import pandas as pd

from .caminhos import APURACAO, BRUTO_TSE, SAIDA_WEB

GRADE = np.round(np.arange(0, 1.0001, 0.05), 2)
FAIXAS = [0, 10_000, 30_000, 60_000, 100_000, 170_000]
AMOSTRA = (60_000, 170_000)
TOLERANCIA = 0.02          # par "na curva": fatia dos dois primeiros a ate 2 pp do observado
POS = {"esquerda": 0, "centro": 1, "direita": 2}
FED24 = {"13": "FE", "65": "FE", "43": "FE", "45": "PSDB/CID", "23": "PSDB/CID", "50": "PSOL/REDE", "18": "PSOL/REDE"}
CAMPO_FED24 = {"FE": "esquerda", "PSDB/CID": "centro", "PSOL/REDE": "esquerda"}


def campo_partido() -> dict[str, str]:
    cfg = json.loads((APURACAO / "config" / "partidos.json").read_text("utf-8"))
    c = {nr: p["eixo"] for nr, p in cfg["partidos"]["2022"].items()}
    c.update({nr: p["eixo"] for nr, p in cfg["partidos"]["2026"].items()})
    c.update(CAMPO_FED24)
    return c


def carrega() -> pd.DataFrame:
    z = zipfile.ZipFile(BRUTO_TSE / "2024" / "votacao_partido_munzona_2024.zip")
    cols = ["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "DS_CARGO", "NR_PARTIDO", "SQ_COLIGACAO",
            "QT_TOTAL_VOTOS_LEG_VALIDOS", "QT_VOTOS_NOMINAIS_VALIDOS"]
    partes = []
    for n in z.namelist():
        if n.endswith(".csv") and not n.endswith(("_BRASIL.csv", "_BR.csv")):
            d = pd.read_csv(z.open(n), sep=";", encoding="latin-1", usecols=cols, dtype={"NR_PARTIDO": str})
            partes.append(d[d["NR_TURNO"] == 1])
    d = pd.concat(partes)
    d["votos"] = d["QT_TOTAL_VOTOS_LEG_VALIDOS"] + d["QT_VOTOS_NOMINAIS_VALIDOS"]
    d["cargo"] = d["DS_CARGO"].str.upper()
    return d


def modelo(s: np.ndarray, pc: np.ndarray, beta: float, pi: float) -> np.ndarray:
    """s: votos; pc: posicao do campo (0, 1, 2; -1 = sem campo). Espelho de Aloca.distrito."""
    V = s.astype(float).copy()
    n = len(V)
    if beta > 0 and n > 2:
        ordem = np.argsort(-V, kind="stable")
        lider = {}
        for i in ordem:
            if pc[i] >= 0 and pc[i] not in lider:
                lider[pc[i]] = i
        V0 = V.copy()
        for i in ordem[2:]:
            if pc[i] < 0 or lider[pc[i]] == i:
                continue
            V[i] -= beta * V0[i]
            V[lider[pc[i]]] += beta * V0[i]
    if pi > 0 and n > 2:
        ordem = np.argsort(-V, kind="stable")
        a, b = ordem[0], ordem[1]
        V1 = V.copy()
        for i in ordem[2:]:
            m = pi * V1[i]
            V[i] -= m
            da = abs(pc[i] - pc[a]) if pc[i] >= 0 and pc[a] >= 0 else 9
            db = abs(pc[i] - pc[b]) if pc[i] >= 0 and pc[b] >= 0 else 9
            if da < db:
                V[a] += m
            elif db < da:
                V[b] += m
            else:
                V[a] += m * V1[a] / (V1[a] + V1[b])
                V[b] += m * V1[b] / (V1[a] + V1[b])
    return V


def cidades(d: pd.DataFrame) -> list[dict]:
    campo = campo_partido()
    aptos = {cd: n for cd, uf, _, n in json.loads((APURACAO / "docs" / "dados" / "municipios.json").read_text("utf-8"))}
    ver = d[d["cargo"] == "VEREADOR"].assign(agr=lambda x: x["NR_PARTIDO"].map(lambda n: FED24.get(n, n)))
    ver = ver.groupby(["CD_MUNICIPIO", "agr"], as_index=False)["votos"].sum()
    pre = d[d["cargo"] == "PREFEITO"].groupby(["CD_MUNICIPIO", "SQ_COLIGACAO", "NR_PARTIDO"], as_index=False)["votos"].sum()
    pre_por = {cd: g for cd, g in pre.groupby("CD_MUNICIPIO")}
    out = []
    for cd, g in ver.groupby("CD_MUNICIPIO"):
        n = aptos.get(cd)
        if n is None or n >= 170_000 or cd not in pre_por or g["votos"].sum() <= 0:
            continue
        p = pre_por[cd]
        if p["votos"].sum() <= 0:
            continue
        so = p["votos"].values / p["votos"].sum()
        fo = np.zeros(3)
        for nr, x in zip(p["NR_PARTIDO"], so):
            if campo.get(nr) in POS:
                fo[POS[campo[nr]]] += x
        out.append({"aptos": n, "s": g["votos"].values / g["votos"].sum(),
                    "pc": np.array([POS.get(campo.get(a), -1) for a in g["agr"]]),
                    "top2": float(np.sort(so)[-2:].sum()), "fo": fo, "ncand": len(p)})
    return out


def superficies(cs: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    """T[c, b, p] = fatia prevista dos dois primeiros; F[c, b, p] = erro quadratico por campo."""
    T = np.zeros((len(cs), len(GRADE), len(GRADE)))
    F = np.zeros_like(T)
    for k, c in enumerate(cs):
        for i, b in enumerate(GRADE):
            for j, p in enumerate(GRADE):
                V = modelo(c["s"], c["pc"], b, p)
                T[k, i, j] = np.sort(V)[-2:].sum()
                fp = np.array([V[c["pc"] == q].sum() for q in range(3)])
                F[k, i, j] = ((fp - c["fo"]) ** 2).sum()
    return T, F


def na_curva(T: np.ndarray, F: np.ndarray, alvo: float) -> tuple[list, tuple]:
    t, f = T.mean(0), F.mean(0)
    curva = []
    for i, b in enumerate(GRADE):
        j = int(np.abs(t[i] - alvo).argmin())
        if abs(t[i, j] - alvo) <= TOLERANCIA:
            curva.append((float(b), float(GRADE[j]), float(f[i, j]), float(t[i, j])))
    melhor = min(curva, key=lambda x: x[2])
    return curva, melhor


def main() -> None:
    cs = cidades(carrega())
    tab = pd.DataFrame({"aptos": [c["aptos"] for c in cs], "top2": [c["top2"] for c in cs],
                        "ncand": [c["ncand"] for c in cs]})
    tab["faixa"] = pd.cut(tab["aptos"], FAIXAS)
    por_faixa = [{"de": int(f.left), "ate": int(f.right), "cidades": int(len(g)), "top2": round(float(g["top2"].mean()), 3),
                  "candidatos": round(float(g["ncand"].mean()), 1)}
                 for f, g in tab.groupby("faixa", observed=True)]
    sel = [c for c in cs if AMOSTRA[0] <= c["aptos"] < AMOSTRA[1]]
    obs = np.array([c["top2"] for c in sel])
    T, F = superficies(sel)
    curva, (beta, pi, _, t2) = na_curva(T, F, obs.mean())
    rng = np.random.default_rng(2024)
    boot = []
    for _ in range(300):
        idx = rng.integers(0, len(sel), len(sel))
        boot.append(na_curva(T[idx], F[idx], obs[idx].mean())[1][:2])
    boot = np.array(boot)
    r = {"amostra": {"de": AMOSTRA[0], "ate": AMOSTRA[1], "cidades": len(sel),
                     "candidatos": round(float(np.mean([c["ncand"] for c in sel])), 1)},
         "top2_observado": round(float(obs.mean()), 3), "top2_previsto": round(t2, 3),
         "por_faixa": por_faixa,
         "curva": [{"beta": b, "pi": p, "erro_campo": round(e, 4)} for b, p, e, _ in curva],
         "top2_sem_ajuste": round(float(T.mean(0)[0, 0]), 3),
         "beta_padrao": beta, "pi_padrao": pi,
         "ic90_beta": [float(x) for x in np.percentile(boot[:, 0], [5, 95])],
         "ic90_pi": [float(x) for x in np.percentile(boot[:, 1], [5, 95])]}
    (SAIDA_WEB / "calibra.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps(r, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

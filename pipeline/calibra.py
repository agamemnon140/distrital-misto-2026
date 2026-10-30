"""Calibra o comportamento do eleitor no distrito com as eleicoes de prefeito de 2024 em turno unico.

Em municipio com menos de 200 mil eleitores o prefeito sai num turno so, por maioria simples: e o
mesmo jogo do distrito. Amostra: cidades de 60 a 170 mil eleitores -- as mais parecidas com um
distrito (que tem ~600 mil), com 4 a 5 candidatos em media. Usa o eleitorado de 2026 como
aproximacao do de 2024 e exclui a faixa de 170-230 mil, onde nao da para saber se houve 2o turno.

Regra do voto (a mesma de js/aloca.js), em duas versoes de "afinidade":
  campos   esquerda | centro | direita, posicoes fixas;
  espectro nota 0-10 dos especialistas (config/espectro.json); afinidade K(d) = exp(-d / lambda).
  beta: quem fica do 3o lugar para baixo passa beta dos votos a quem esta a sua frente -- no modo
        campos, ao mais bem colocado do proprio campo (se nao for ele mesmo); no espectro, beta x
        (maior afinidade com quem esta a frente), dividido por afinidade x votos;
  pi:   depois, do 3o lugar para baixo, pi do que resta vai para um dos dois primeiros -- o de campo
        mais proximo (campos; empate divide na proporcao dos dois) ou na proporcao das afinidades
        (espectro).

Dois desenhos, um para cada simulador:
  sem coordenacao: cada partido vira um "candidato" com o seu voto para vereador (o simulador sem
    coordenacao tambem poe todo mundo na disputa). Alvo: a fatia dos dois primeiros, que sozinha
    nao separa os parametros (ha uma curva deles); entre os pontos da curva, fica o que erra menos
    a votacao de prefeito por campo.
  com coordenacao: as coligacoes de verdade. O candidato a prefeito leva o voto do proprio partido
    (e da federacao) e kappa do voto dos partidos coligados; o resto se espalha. Depois vem
    beta/pi. Alvo: a votacao de cada candidato (erro quadratico das fatias). kappa e a fracao do
    eleitor do aliado que segue o candidato do acordo.

Saida: docs/dados/calibra.json
"""
from __future__ import annotations

import json
import re
import zipfile
from itertools import product

import numpy as np
import pandas as pd

from .caminhos import APURACAO, BRUTO_TSE, SAIDA_WEB
from .espectro import notas

GRADE_FINA = np.round(np.arange(0, 1.0001, 0.05), 2)
GRADE = np.round(np.arange(0, 1.0001, 0.1), 2)
LAMBDAS = (0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0)
FAIXAS = [0, 10_000, 30_000, 60_000, 100_000, 170_000]
AMOSTRA = (60_000, 170_000)
TOLERANCIA = 0.02          # ponto "na curva": fatia dos dois primeiros a ate 2 pp do observado
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
    cols = ["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "DS_CARGO", "NR_PARTIDO", "SG_PARTIDO", "SQ_COLIGACAO",
            "DS_COMPOSICAO_COLIGACAO", "QT_TOTAL_VOTOS_LEG_VALIDOS", "QT_VOTOS_NOMINAIS_VALIDOS"]
    partes = []
    for n in z.namelist():
        if n.endswith(".csv") and not n.endswith(("_BRASIL.csv", "_BR.csv")):
            d = pd.read_csv(z.open(n), sep=";", encoding="latin-1", usecols=cols, dtype={"NR_PARTIDO": str})
            partes.append(d[d["NR_TURNO"] == 1])
    d = pd.concat(partes)
    d["votos"] = d["QT_TOTAL_VOTOS_LEG_VALIDOS"] + d["QT_VOTOS_NOMINAIS_VALIDOS"]
    d["cargo"] = d["DS_CARGO"].str.upper()
    return d


# ------------------------------------------------------------------------------- modelo
def afinidade(x: np.ndarray, lam: float):
    def K(i, j):
        if np.isnan(x[i]) or np.isnan(x[j]):
            return 0.0
        return float(np.exp(-abs(x[i] - x[j]) / lam))
    return K


def modelo(s: np.ndarray, pc: np.ndarray, beta: float, pi: float, x: np.ndarray | None = None,
           lam: float = 1.0) -> np.ndarray:
    """s: votos; pc: campo (0, 1, 2; -1 = sem); x: nota 0-10 (nan = sem) -> modo espectro.
    Espelho de Aloca.distrito (etapas de beta e pi)."""
    V = s.astype(float).copy()
    n = len(V)
    K = afinidade(x, lam) if x is not None else None
    if beta > 0 and n > 2:
        ordem = np.argsort(-V, kind="stable")
        V0 = V.copy()
        if K is None:
            lider = {}
            for i in ordem:
                if pc[i] >= 0 and pc[i] not in lider:
                    lider[pc[i]] = i
            for i in ordem[2:]:
                if pc[i] < 0 or lider[pc[i]] == i:
                    continue
                V[i] -= beta * V0[i]
                V[lider[pc[i]]] += beta * V0[i]
        else:
            for pos in range(2, n):
                i, acima = ordem[pos], ordem[:pos]
                k = np.array([K(i, j) for j in acima])
                w = k * V0[acima]
                if k.max() <= 0 or w.sum() <= 0:
                    continue
                m = beta * V0[i] * k.max()
                V[i] -= m
                V[acima] += m * w / w.sum()
    if pi > 0 and n > 2:
        ordem = np.argsort(-V, kind="stable")
        a, b = ordem[0], ordem[1]
        V1 = V.copy()
        for i in ordem[2:]:
            m = pi * V1[i]
            V[i] -= m
            if K is None:
                da = abs(pc[i] - pc[a]) if pc[i] >= 0 and pc[a] >= 0 else 9
                db = abs(pc[i] - pc[b]) if pc[i] >= 0 and pc[b] >= 0 else 9
                fa = 1.0 if da < db else 0.0 if db < da else V1[a] / (V1[a] + V1[b])
            else:
                ka, kb = K(i, a), K(i, b)
                fa = ka / (ka + kb) if ka + kb > 0 else V1[a] / (V1[a] + V1[b])
            V[a] += m * fa
            V[b] += m * (1 - fa)
    return V


# ------------------------------------------------------------------------------- dados
def _siglas(comp: str) -> set[str]:
    """'REPUBLICANOS / Federacao PSDB CIDADANIA (PSDB / CIDADANIA) / PL' -> siglas."""
    comp = re.sub(r"Federa\S*[^(]*\(([^)]*)\)", r"\1", str(comp))
    return {s.strip().upper().replace(" ", "") for s in comp.split("/") if s.strip()}


def cidades(d: pd.DataFrame) -> list[dict]:
    campo = campo_partido()
    nt = notas()
    aptos = {cd: n for cd, uf, _, n in json.loads((APURACAO / "docs" / "dados" / "municipios.json").read_text("utf-8"))}
    ver = d[d["cargo"] == "VEREADOR"].groupby(["CD_MUNICIPIO", "NR_PARTIDO", "SG_PARTIDO"], as_index=False)["votos"].sum()
    nr_da_sigla = dict(zip(ver["SG_PARTIDO"].str.upper().str.replace(" ", ""), ver["NR_PARTIDO"]))
    pre = d[d["cargo"] == "PREFEITO"].groupby(["CD_MUNICIPIO", "SQ_COLIGACAO", "NR_PARTIDO", "DS_COMPOSICAO_COLIGACAO"],
                                               as_index=False)["votos"].sum()
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
        vp = dict(zip(g["NR_PARTIDO"], g["votos"].astype(float)))
        tot = sum(vp.values())
        # desenho sem coordenacao: um "candidato" por partido/federacao
        agr = {}
        for nr, v in vp.items():
            agr.setdefault(FED24.get(nr, nr), []).append(nr)
        ids = sorted(agr)
        s = np.array([sum(vp[nr] for nr in agr[a]) for a in ids]) / tot
        x = np.array([sum(nt[nr] * vp[nr] for nr in agr[a] if nr in nt) / max(1e-9, sum(vp[nr] for nr in agr[a] if nr in nt))
                      if any(nr in nt for nr in agr[a]) else np.nan for a in ids])
        pc = np.array([POS.get(campo.get(a), -1) for a in ids])
        # desenho com coordenacao: as coligacoes de verdade
        proprio, aliado, usados = [], [], set()
        for cab, comp in zip(p["NR_PARTIDO"], p["DS_COMPOSICAO_COLIGACAO"]):
            membros = {nr_da_sigla.get(sg) for sg in _siglas(comp)} | {cab}
            membros.discard(None)
            fed = {nr for nr in membros if cab in FED24 and FED24.get(nr) == FED24[cab]} | {cab}
            proprio.append(sum(vp.get(nr, 0) for nr in fed))
            aliado.append(sum(vp.get(nr, 0) for nr in membros - fed))
            usados |= membros
        livre = sum(v for nr, v in vp.items() if nr not in usados)
        out.append({"aptos": n, "top2": float(np.sort(so)[-2:].sum()), "ncand": len(p), "fo": fo,
                    "s": s, "x": x, "pc": pc,
                    "c_proprio": np.array(proprio) / tot, "c_aliado": np.array(aliado) / tot, "c_livre": livre / tot,
                    "c_obs": so, "c_pc": np.array([POS.get(campo.get(nr), -1) for nr in p["NR_PARTIDO"]]),
                    "c_x": np.array([nt.get(nr, np.nan) for nr in p["NR_PARTIDO"]])})
    return out


# ------------------------------------------------------------------------------- sem coordenacao
def sem_coordenacao(cs: list[dict], espectro: bool) -> dict:
    grade_b = GRADE if espectro else GRADE_FINA
    lams = LAMBDAS if espectro else (None,)
    obs = np.array([c["top2"] for c in cs])
    T = np.zeros((len(cs), len(grade_b), len(GRADE_FINA), len(lams)))
    F = np.zeros_like(T)
    for k, c in enumerate(cs):
        for (i, b), (j, p), (q, lam) in product(enumerate(grade_b), enumerate(GRADE_FINA), enumerate(lams)):
            V = modelo(c["s"], c["pc"], b, p, c["x"] if espectro else None, lam or 1.0)
            T[k, i, j, q] = np.sort(V)[-2:].sum()
            fp = np.array([V[c["pc"] == r].sum() for r in range(3)])
            F[k, i, j, q] = ((fp - c["fo"]) ** 2).sum()

    def melhor(idx):
        # para cada (beta, lambda), o pi que mais se aproxima do alvo; entre esses pontos da curva
        # (a ate TOLERANCIA do alvo), o de menor erro por campo
        t, f, alvo = T[idx].mean(0), F[idx].mean(0), obs[idx].mean()
        j = np.abs(t - alvo).argmin(axis=1)                               # [beta, lambda]
        tj = np.take_along_axis(t, j[:, None, :], 1)[:, 0, :]
        fj = np.take_along_axis(f, j[:, None, :], 1)[:, 0, :]
        ok = np.abs(tj - alvo) <= TOLERANCIA
        if not ok.any():
            ok = np.abs(tj - alvo) == np.abs(tj - alvo).min()
        i, q = np.unravel_index(np.where(ok, fj, np.inf).argmin(), fj.shape)
        return grade_b[i], GRADE_FINA[j[i, q]], lams[q], tj[i, q]

    b, p, lam, t2 = melhor(np.arange(len(cs)))
    rng = np.random.default_rng(2024)
    boot = np.array([melhor(rng.integers(0, len(cs), len(cs)))[:2] for _ in range(200)], dtype=float)
    r = {"beta": float(b), "pi": float(p), "top2_previsto": round(float(t2), 3),
         "ic90_beta": [float(x) for x in np.percentile(boot[:, 0], [5, 95])],
         "ic90_pi": [float(x) for x in np.percentile(boot[:, 1], [5, 95])]}
    if espectro:
        r["lambda"] = float(lam)
    # a curva (para a pagina): para cada beta, o pi que acerta a fatia dos dois primeiros
    t, f = T.mean(0), F.mean(0)
    q = LAMBDAS.index(lam) if espectro else 0
    r["curva"] = [{"beta": float(bb), "pi": float(GRADE_FINA[np.abs(t[i, :, q] - obs.mean()).argmin()]),
                   "erro_campo": round(float(f[i, np.abs(t[i, :, q] - obs.mean()).argmin(), q]), 4)}
                  for i, bb in enumerate(grade_b) if np.abs(t[i, :, q] - obs.mean()).min() <= TOLERANCIA]
    r["top2_sem_ajuste"] = round(float(t[0, 0, 0]), 3)
    return r


# ------------------------------------------------------------------------------- com coordenacao
def com_coordenacao(cs: list[dict], espectro: bool) -> dict:
    lams = LAMBDAS if espectro else (None,)
    combos = list(product(GRADE, GRADE, GRADE, lams))           # kappa, beta, pi, lambda
    E = np.zeros((len(cs), len(combos)))
    T2 = np.zeros_like(E)
    for k, c in enumerate(cs):
        for n_, (ka, b, p, lam) in enumerate(combos):
            base = c["c_proprio"] + ka * c["c_aliado"]
            solto = (1 - ka) * c["c_aliado"].sum() + c["c_livre"]
            s = base + solto * base / base.sum() if base.sum() > 0 else base
            V = modelo(s, c["c_pc"], b, p, c["c_x"] if espectro else None, lam or 1.0)
            V = V / V.sum()
            E[k, n_] = ((V - c["c_obs"]) ** 2).sum()
            T2[k, n_] = np.sort(V)[-2:].sum()
    j = int(E.sum(0).argmin())
    rng = np.random.default_rng(2024)
    boot = np.array([combos[int(E[rng.integers(0, len(cs), len(cs))].sum(0).argmin())][:3] for _ in range(300)], dtype=float)
    ka, b, p, lam = combos[j]
    sem_k = [n_ for n_, cmb in enumerate(combos) if cmb[1:] == (b, p, lam) and cmb[0] == 0]
    r = {"kappa": float(ka), "beta": float(b), "pi": float(p),
         "top2_previsto": round(float(T2[:, j].mean()), 3),
         "erro": round(float(E[:, j].mean()), 4), "erro_kappa0": round(float(E[:, sem_k[0]].mean()), 4),
         "ic90_kappa": [float(x) for x in np.percentile(boot[:, 0], [5, 95])],
         "ic90_beta": [float(x) for x in np.percentile(boot[:, 1], [5, 95])],
         "ic90_pi": [float(x) for x in np.percentile(boot[:, 2], [5, 95])]}
    if espectro:
        r["lambda"] = float(lam)
    return r


def main() -> None:
    cs = cidades(carrega())
    tab = pd.DataFrame({"aptos": [c["aptos"] for c in cs], "top2": [c["top2"] for c in cs],
                        "ncand": [c["ncand"] for c in cs]})
    tab["faixa"] = pd.cut(tab["aptos"], FAIXAS)
    por_faixa = [{"de": int(f.left), "ate": int(f.right), "cidades": int(len(g)), "top2": round(float(g["top2"].mean()), 3),
                  "candidatos": round(float(g["ncand"].mean()), 1)}
                 for f, g in tab.groupby("faixa", observed=True)]
    sel = [c for c in cs if AMOSTRA[0] <= c["aptos"] < AMOSTRA[1]]
    r = {"amostra": {"de": AMOSTRA[0], "ate": AMOSTRA[1], "cidades": len(sel),
                     "candidatos": round(float(np.mean([c["ncand"] for c in sel])), 1)},
         "top2_observado": round(float(np.mean([c["top2"] for c in sel])), 3),
         "por_faixa": por_faixa}
    for modo, esp in (("campos", False), ("espectro", True)):
        r[modo] = {"sem": sem_coordenacao(sel, esp), "com": com_coordenacao(sel, esp)}
        print(modo, json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "curva"} for k, v in r[modo].items()}), flush=True)
    r["top2_sem_ajuste"] = r["campos"]["sem"]["top2_sem_ajuste"]
    (SAIDA_WEB / "calibra.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), "utf-8")


if __name__ == "__main__":
    main()

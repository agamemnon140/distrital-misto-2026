"""Calibra o voto util (beta) com as eleicoes de prefeito de 2024 em turno unico.

Em municipio com menos de 200 mil eleitores o prefeito sai num turno so, por maioria simples:
e o mesmo jogo do distrito. Para cada cidade com 3+ candidatos:
  base do candidato = voto para vereador dos partidos da sua coligacao (o voto de partido sem
  candidato se espalha na proporcao das bases);
  previsto(beta) = mesma regra do simulador: quem fica do 3o lugar para baixo e nao lidera o
  proprio campo passa beta dos votos ao mais bem colocado do campo;
  observado = votacao real de prefeito.
beta-chapeu minimiza o erro quadratico das fatias; o IC vem de bootstrap por cidade.

Desenho 2 (sem coligacao, como no simulador): cada partido/federacao e um "candidato" com o seu
voto de vereador; procura o beta que reproduz a fatia media dos dois primeiros prefeitos.

Resultado de 2024: desenho 1 da beta = 0 (a coligacao ja concentra tudo: coordenacao e de
cupula, nao de eleitor) e desenho 2 satura (nem beta = 1 chega aos 95% dos dois primeiros).
Nenhum dos dois cai limpo em [0; 0,5] -> padrao 0,3, como combinado.
Usa o eleitorado de 2026 como aproximacao do de 2024 e exclui a faixa de 170-230 mil.

Saida: docs/dados/beta.json
"""
from __future__ import annotations

import json
import zipfile

import numpy as np
import pandas as pd

from .caminhos import APURACAO, BRUTO_TSE, SAIDA_WEB

GRADE = np.round(np.arange(0, 1.0001, 0.01), 2)


def campo_partido() -> dict[str, str]:
    cfg = json.loads((APURACAO / "config" / "partidos.json").read_text("utf-8"))
    c = {nr: p["eixo"] for nr, p in cfg["partidos"]["2022"].items()}
    c.update({nr: p["eixo"] for nr, p in cfg["partidos"]["2026"].items()})
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
    return d


def cidades(d: pd.DataFrame, campo: dict) -> list[dict]:
    aptos = {cd: n for cd, uf, _, n in json.loads((APURACAO / "docs" / "dados" / "municipios.json").read_text("utf-8"))}
    cargo = d["DS_CARGO"].str.upper()
    ver = d[cargo == "VEREADOR"].groupby(["CD_MUNICIPIO", "SG_PARTIDO", "NR_PARTIDO"], as_index=False)["votos"].sum()
    pre = d[cargo == "PREFEITO"].groupby(["CD_MUNICIPIO", "SQ_COLIGACAO", "NR_PARTIDO", "DS_COMPOSICAO_COLIGACAO"],
                                         as_index=False)["votos"].sum()
    ver_por = {cd: g for cd, g in ver.groupby("CD_MUNICIPIO")}
    out = []
    for cd, g in pre.groupby("CD_MUNICIPIO"):
        n = aptos.get(cd)
        if n is None or 170_000 <= n <= 230_000 or n > 230_000 or len(g) < 3 or cd not in ver_por:
            continue
        v = ver_por[cd]
        vsig = dict(zip(v["SG_PARTIDO"].str.upper(), v["votos"]))
        bases, usados = [], set()
        for comp, nr in zip(g["DS_COMPOSICAO_COLIGACAO"], g["NR_PARTIDO"]):
            sig = {s.strip().upper() for s in str(comp).split("/")}
            b = sum(vsig.get(s, 0) for s in sig)
            usados |= sig
            bases.append(b)
        bases = np.array(bases, dtype=float)
        if bases.sum() <= 0:
            continue
        livre = sum(x for s, x in vsig.items() if s not in usados)
        prev = bases + livre * bases / bases.sum()
        obs = g["votos"].values.astype(float)
        if obs.sum() <= 0:
            continue
        out.append({"prev": prev / prev.sum(), "obs": obs / obs.sum(),
                    "campo": [campo.get(nr) for nr in g["NR_PARTIDO"]]})
    return out


def aplica_beta(s: np.ndarray, campos: list, beta: float) -> np.ndarray:
    V = s.copy()
    ordem = np.argsort(-s, kind="stable")
    lider = {}
    for i in ordem:
        if campos[i] and campos[i] not in lider:
            lider[campos[i]] = i
    for pos in range(2, len(ordem)):
        i = ordem[pos]
        c = campos[i]
        if not c or lider[c] == i:
            continue
        V[i] -= beta * s[i]
        V[lider[c]] += beta * s[i]
    return V


def erros(cs: list[dict]) -> np.ndarray:
    """[n_cidades, n_grade] erro quadratico por cidade."""
    E = np.zeros((len(cs), len(GRADE)))
    for i, c in enumerate(cs):
        for j, b in enumerate(GRADE):
            E[i, j] = ((aplica_beta(c["prev"], c["campo"], b) - c["obs"]) ** 2).sum()
    return E


FED24 = {"13": "FE", "65": "FE", "43": "FE", "45": "PSDB/CID", "23": "PSDB/CID", "50": "PSOL/REDE", "18": "PSOL/REDE"}
CAMPO_FED24 = {"FE": "esquerda", "PSDB/CID": "centro", "PSOL/REDE": "esquerda"}


def desenho_partidos(d: pd.DataFrame, campo: dict) -> dict:
    aptos = {cd: n for cd, uf, _, n in json.loads((APURACAO / "docs" / "dados" / "municipios.json").read_text("utf-8"))}
    cargo = d["DS_CARGO"].str.upper()
    ver = d[cargo == "VEREADOR"].assign(agr=lambda x: x["NR_PARTIDO"].map(lambda n: FED24.get(n, n)))
    ver = ver.groupby(["CD_MUNICIPIO", "agr"], as_index=False)["votos"].sum()
    pre = d[cargo == "PREFEITO"].groupby(["CD_MUNICIPIO", "SQ_COLIGACAO"], as_index=False)["votos"].sum()
    obs = {cd: np.sort(g["votos"].values / g["votos"].sum())[-2:].sum()
           for cd, g in pre.groupby("CD_MUNICIPIO") if g["votos"].sum() > 0 and len(g) >= 2}
    cs = []
    for cd, g in ver.groupby("CD_MUNICIPIO"):
        n = aptos.get(cd)
        if n is None or n >= 170_000 or cd not in obs or g["votos"].sum() <= 0:
            continue
        cs.append((g["votos"].values / g["votos"].sum(), [CAMPO_FED24.get(a, campo.get(a)) for a in g["agr"]]))
    alvo = float(np.mean([obs[cd] for cd, g in ver.groupby("CD_MUNICIPIO") if cd in obs and aptos.get(cd, 1e9) < 170_000]))
    curva = {float(b): float(np.mean([np.sort(aplica_beta(s, c, b))[-2:].sum() for s, c in cs])) for b in (0, .25, .5, .75, 1)}
    return {"cidades": len(cs), "top2_observado": round(alvo, 3), "top2_previsto_por_beta": {k: round(v, 3) for k, v in curva.items()},
            "satura": curva[1.0] < alvo}


def main() -> None:
    cs = cidades(carrega(), campo_partido())
    E = erros(cs)
    j = int(E.sum(0).argmin())
    rng = np.random.default_rng(2024)
    boot = [GRADE[int(E[rng.integers(0, len(cs), len(cs))].sum(0).argmin())] for _ in range(300)]
    lo, hi = np.percentile(boot, [5, 95])
    # quantas cidades tem algum movimento possivel (nao-lider do campo em 3o ou abaixo)
    ativas = sum(1 for c in cs if not np.allclose(aplica_beta(c["prev"], c["campo"], 1.0), c["prev"]))
    ganho = 1 - E[:, j].sum() / E[:, 0].sum()
    limpo = (hi - lo) <= 0.15 and 0 < GRADE[j] < 1
    usado = float(GRADE[j]) if limpo and GRADE[j] <= 0.5 else 0.3
    r = {"beta_hat": float(GRADE[j]), "ic90": [float(lo), float(hi)], "cidades": len(cs),
         "cidades_com_movimento": ativas, "reducao_erro": round(float(ganho), 4),
         "beta_padrao": usado, "limpo": bool(limpo and GRADE[j] <= 0.5),
         "nota": "beta-chapeu usado como padrao" if limpo and GRADE[j] <= 0.5 else
                 "estimativa fora de [0; 0,5] ou IC largo: padrao 0,3"}
    r = {"desenho_coligacoes": r, "desenho_partidos": desenho_partidos(carrega(), campo_partido()),
         "beta_padrao": usado,
         "nota": ("Prefeito 2024, turno unico: com as coligacoes como base, beta = 0 (a coordenacao e de "
                  "cupula); sem coligacao, nem beta = 1 alcanca a concentracao real nos dois primeiros. "
                  "Sem estimativa limpa, o padrao fica em 0,3.") if not r["limpo"] else r["nota"]}
    (SAIDA_WEB / "beta.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps(r, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

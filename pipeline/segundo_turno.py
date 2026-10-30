"""Quanto o eleitor de cada agremiacao votou em Lula no 2o turno de 2026, por UF.

Regressao ecologica por local de votacao, dentro de cada UF:
    lula_l / (lula_l + flavio_l) = sum_a s_{a,l} * L_a + erro
s_{a,l} = fatia da agremiacao a no voto para deputado federal no local l; L_a em [0, 1];
minimos quadrados com limites (scipy.optimize.lsq_linear), ponderados pelo voto do local.
Agremiacao com menos de MIN_FATIA do voto da UF fica no grupo "pequenos" (um L so) e herda o L
nacional dela (media das UFs ponderada pelo voto) -- estimativa pequena e muito ruidosa.

E a afinidade "2o turno" do simulador: o eleitor do PSD da Bahia (aliado do PT) e o de SP nao
tem o mesmo comportamento, e a escala nacional dos especialistas nao enxerga isso.

Saida: TRAB/segundo_turno.json  {uf: {agr: L}, "_nacional": {agr: L}}
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy.optimize import lsq_linear

from .caminhos import TRAB, UFS
from .candidatos import agr as agr_do_partido

MIN_FATIA = 0.01


def main() -> None:
    d = pd.read_parquet(TRAB / "depfed_local.parquet")
    d = d[~d["nr"].isin(["95", "96"])]
    c = pd.read_parquet(TRAB / "candidatos.parquet")
    ad = dict(zip(zip(c["uf"], c["nr"]), c["agr"]))
    d["agr"] = [ad.get((u, n), agr_do_partido(n[:2])) for u, n in zip(d["uf"], d["nr"])]
    k = ["uf", "mun", "zona", "local"]
    pres = pd.read_parquet(TRAB / "pres2t_local.parquet")
    pres = pres[(pres["lula"] + pres["flavio"]) > 0]
    out, pesos = {}, {}
    for uf in UFS:
        du = d[d["uf"] == uf].groupby(k + ["agr"], as_index=False)["votos"].sum()
        tot_a = du.groupby("agr")["votos"].sum()
        fatia = tot_a / tot_a.sum()
        grandes = sorted(fatia[fatia >= MIN_FATIA].index)
        du["g"] = du["agr"].where(du["agr"].isin(grandes), "_pequenos")
        M = du.pivot_table(index=k, columns="g", values="votos", aggfunc="sum", fill_value=0)
        p = pres[pres["uf"] == uf].set_index(k)
        M = M.join(p[["lula", "flavio"]], how="inner")
        y = (M["lula"] / (M["lula"] + M["flavio"])).values
        cols = [x for x in M.columns if x not in ("lula", "flavio")]
        X = M[cols].values.astype(float)
        n = X.sum(1, keepdims=True)
        ok = n[:, 0] > 0
        S = X[ok] / n[ok]
        w = np.sqrt(n[ok, 0])
        r = lsq_linear(S * w[:, None], y[ok] * w, bounds=(0, 1))
        est = dict(zip(cols, r.x))
        out[uf] = {a: round(float(est[a]), 4) for a in grandes}
        out[uf]["_pequenos"] = round(float(est.get("_pequenos", np.nan)), 4)
        pesos[uf] = tot_a.to_dict()
    # nacional: media das UFs ponderada pelo voto
    nac = {}
    for a in sorted({a for v in out.values() for a in v if a != "_pequenos"}):
        num = sum(out[uf][a] * pesos[uf].get(a, 0) for uf in UFS if a in out[uf])
        den = sum(pesos[uf].get(a, 0) for uf in UFS if a in out[uf])
        nac[a] = round(num / den, 4)
    for uf in UFS:
        for a, v in pesos[uf].items():
            if a not in out[uf]:
                out[uf][a] = nac.get(a, out[uf]["_pequenos"])
    out["_nacional"] = nac
    (TRAB / "segundo_turno.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
    for a, v in sorted(nac.items(), key=lambda x: -x[1]):
        print(f"{a:18} {v:.2f}  BA {out['BA'].get(a, float('nan')):.2f}  SP {out['SP'].get(a, float('nan')):.2f}")


if __name__ == "__main__":
    main()

"""Exporta os JSON da pagina (docs/dados).

  base.json          agremiacoes, partidos, rateios (k por UF), candidatos e totais por UF, eleitos reais
  dist/{UF}.json     por k: para cada mapa e distrito, entradas [agr, T, X, cand] + metricas
                     (T = voto da agremiacao no distrito; X = voto nominal dos colegas que NAO
                     concorrem ali; cand = indice do candidato emparelhado, -1 se nenhum)
  mapas/{UF}.json    por k: atribuicao tijolo -> distrito de cada mapa (string base-64) + atributos do tijolo
  geo/{UF}.json      TopoJSON dos tijolos
"""
from __future__ import annotations

import json
import pickle
import sys

import geopandas as gpd
import numpy as np
import shapely
import shapely.geometry.polygon
import topojson as tp

from .caminhos import APURACAO, RAIZ, SAIDA_WEB, TRAB, UFS
from .candidatos import CAMPO, COR, FED, SIGLA
from .mapas import ks_da_uf
from .rateio import RATEIOS, populacao, rateios

B64 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
PODA_FRACAO = 0.01        # agremiacao com < 1% do distrito e fora do top 8 vira "outros"
PODA_TOPO = 8
NOME_FED = {"FED-PT/PCdoB/PV": ("PT/PCdoB/PV", "13"), "FED-PSOL/REDE": ("PSOL/REDE", "50"),
            "FED-PSDB/CID": ("PSDB/Cidadania", "45"), "FED-PRD/SOLID": ("PRD/Solidariedade", "25"),
            "FED-UNIAO/PP": ("União/PP", "44")}


def agremiacoes() -> list[dict]:
    campos = json.loads((RAIZ / "config" / "campos.json").read_text("utf-8"))
    out = []
    for nr, sig in sorted(SIGLA.items()):
        if nr in FED:
            continue
        out.append({"id": nr, "sigla": sig, "cor": COR[nr], "campo": campos.get(nr, CAMPO[nr]), "partidos": [nr]})
    for fed, (nome, lider) in NOME_FED.items():
        out.append({"id": fed, "sigla": nome, "cor": COR[lider], "campo": campos.get(fed, CAMPO[lider]),
                    "partidos": [nr for nr, f in FED.items() if f == fed]})
    return out


def exporta_uf(uf: str, idx_agr: dict) -> dict:
    with open(TRAB / "matrizes" / f"{uf}.pkl", "rb") as fh:
        r = pickle.load(fh)
    ins = r["ins"]
    loc_agr = np.array([idx_agr[a] for a in ins["agrs"]])
    cand_local_agr = ins["cand_agr"]
    dist = {}
    for k, pk in r["por_k"].items():
        mapas = []
        for d in pk["dist"]:
            Va, esc, own = d["Va"], d["esc"], d["own"]
            # nominal da agremiacao no distrito = soma dos seus candidatos ali (Va inclui legenda)
            distritos = []
            for j in range(k):
                T = Va[j]
                ordem = np.argsort(-T)
                tot = T.sum()
                linha, outros_T, outros_X = [], 0, 0
                for pos, a in enumerate(ordem):
                    if T[a] <= 0:
                        break
                    X = int(d["nom"][j, a] - own[j, a])
                    if pos < PODA_TOPO or T[a] >= PODA_FRACAO * tot:
                        linha += [int(loc_agr[a]), int(T[a]), X, int(esc[j, a])]
                    else:
                        outros_T += int(T[a])
                        outros_X += X
                if outros_T:
                    linha += [-1, outros_T, outros_X, -1]
                distritos.append(linha)
            mapas.append({"d": distritos, "aptos": [int(x) for x in d["aptos"]],
                          "pop": [int(x) for x in d["pop"]], "lula": [int(x) for x in d["lula"]],
                          "flavio": [int(x) for x in d["flavio"]]})
        dist[k] = mapas
    return {"dist": dist, "mapas": {k: ["".join(B64[x] for x in m) for m in pk["mapas"]] for k, pk in r["por_k"].items()},
            "ins": ins}


def horario(x):
    """d3-geo (esferico) quer anel externo em sentido horario; o shapely entrega anti-horario.
    GeometryCollection (sobra de recorte) vira MultiPolygon so com as partes de area."""
    orient = shapely.geometry.polygon.orient
    if x.geom_type == "Polygon":
        return orient(x, sign=-1.0)
    partes = [q for q in getattr(x, "geoms", []) if q.geom_type in ("Polygon", "MultiPolygon")]
    polys = [pp for q in partes for pp in (q.geoms if q.geom_type == "MultiPolygon" else [q])]
    return shapely.geometry.MultiPolygon([orient(q, sign=-1.0) for q in polys])


def geo_uf(uf: str, ins: dict) -> dict:
    with open(TRAB / "tijolos" / f"{uf}.pkl", "rb") as fh:
        t = pickle.load(fh)
    nomes = {cd: nome for cd, u, nome, _ in json.loads((APURACAO / "docs" / "dados" / "municipios.json").read_text("utf-8")) if u == uf}
    geo = [horario(x) for x in t["geo"]]
    g = gpd.GeoDataFrame({"i": range(len(t["nos"]))}, geometry=geo, crs="EPSG:4326")
    topo = tp.Topology(g, prequantize=2e5, toposimplify=0.0004 if uf not in ("DF",) else 0.0001,
                       topology=True).to_dict()
    tij = {"mun": [nomes.get(n["mun"], str(n["mun"])) for n in t["nos"]],
           "aptos": [int(x) for x in ins["aptos_tij"]]}
    return topo, tij


def main() -> None:
    ufs = sys.argv[1:] or UFS
    ags = agremiacoes()
    idx_agr = {a["id"]: i for i, a in enumerate(ags)}
    rt = rateios()
    base = {"agrs": ags,
            "partidos": {nr: {"sigla": s, "cor": COR[nr]} for nr, s in SIGLA.items()},
            "rateios": rt, "nomes_rateio": RATEIOS, "pop": populacao(), "ks": {}, "uf": {}}
    for d in ("dist", "mapas", "geo"):
        (SAIDA_WEB / d).mkdir(parents=True, exist_ok=True)
    for uf in ufs:
        e = exporta_uf(uf, idx_agr)
        ins = e["ins"]
        c = ins["cands"]
        va = {}
        tot_a = ins["tot_agr"]
        for a, v in zip(ins["agrs"], tot_a):
            va[idx_agr[a]] = int(v)
        base["ks"][uf] = {nome: max(1, rt[nome][uf] // 2) for nome in RATEIOS}
        base["uf"][uf] = {
            "votos_agr": va,
            "cands": [[nr, nome, p, idx_agr[a], int(v), int(er)] for nr, nome, p, a, v, er in
                      zip(c["nr"], c["nome"], c["partido"], c["agr"], c["votos"], c["eleito_real"])],
        }
        (SAIDA_WEB / "dist" / f"{uf}.json").write_text(json.dumps(e["dist"], separators=(",", ":")), "utf-8")
        topo, tij = geo_uf(uf, ins)
        (SAIDA_WEB / "geo" / f"{uf}.json").write_text(json.dumps(topo, separators=(",", ":")), "utf-8")
        (SAIDA_WEB / "mapas" / f"{uf}.json").write_text(json.dumps({"mapas": e["mapas"], "tij": tij},
                                                                   separators=(",", ":"), ensure_ascii=False), "utf-8")
        tam = sum((SAIDA_WEB / d / f"{uf}.json").stat().st_size for d in ("dist", "mapas", "geo")) / 1e6
        print(f"{uf}: ks {list(e['dist'])}, {tam:.1f} MB", flush=True)
    if not sys.argv[1:]:
        (SAIDA_WEB / "base.json").write_text(json.dumps(base, separators=(",", ":"), ensure_ascii=False), "utf-8")
        print(f"base.json {(SAIDA_WEB / 'base.json').stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()

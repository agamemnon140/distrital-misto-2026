"""Exporta os JSON da pagina (docs/dados).

  base.json          agremiacoes, partidos, rateios (k por UF), candidatos e totais por UF, eleitos reais
  dist/{UF}.json     por k: para cada mapa e distrito, entradas [agr, T, X, cand, X_g1..X_g4, P] + metricas
                     (T = voto da agremiacao no distrito; X = voto nominal dos colegas que NAO
                     concorrem ali; cand = indice do candidato emparelhado, -1 se nenhum; X_g = parte
                     de X que o candidato herda com gama = GAMAS, ver matrizes.py; P = voto nominal
                     proprio do candidato ali; a legenda e T - X - P)
  mapas/{UF}.json    por k: atribuicao tijolo -> distrito de cada mapa (string base-64) + atributos do
                     tijolo (municipio, eleitorado e, nos municipios quebrados, os bairros dos locais)
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
from .espectro import NIVEIS, posicoes
from .matrizes import GAMAS
from .tijolos import locais_2026
from .rateio import RATEIOS, populacao, rateios

B64 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
PODA_FRACAO = 0.01        # agremiacao com < 1% do distrito e fora do top 8 vira "outros"
PODA_TOPO = 8
NOME_FED = {"FED-PT/PCdoB/PV": ("PT/PCdoB/PV", "13"), "FED-PSOL/REDE": ("PSOL/REDE", "50"),
            "FED-PSDB/CID": ("PSDB/Cidadania", "45"), "FED-PRD/SOLID": ("PRD/Solidariedade", "25"),
            "FED-UNIAO/PP": ("União/PP", "44")}


def agremiacoes() -> list[dict]:
    campos = json.loads((RAIZ / "config" / "campos.json").read_text("utf-8"))
    pos = posicoes()
    out = []
    for nr, sig in sorted(SIGLA.items()):
        if nr in FED:
            continue
        out.append({"id": nr, "sigla": sig, "cor": COR[nr], "campo": campos.get(nr, CAMPO[nr]), "partidos": [nr],
                    "pos": pos.get(nr)})
    for fed, (nome, lider) in NOME_FED.items():
        out.append({"id": fed, "sigla": nome, "cor": COR[lider], "campo": campos.get(fed, CAMPO[lider]),
                    "partidos": [nr for nr, f in FED.items() if f == fed], "pos": round(pos[fed], 3)})
    return out


def mapas_json(variante: dict, k: int, loc_agr: np.ndarray) -> list[dict]:
    """Distritos de cada mapa de uma variante (sem coordenacao ou com um limiar)."""
    mapas = []
    for d in variante[k]["dist"]:
        Va, esc, own, bloq = d["Va"], d["esc"], d["own"], d["bloq"]
        distritos = []
        for j in range(k):
            T = Va[j]
            ordem = np.argsort(-T)
            tot = T.sum()
            linha, outros = [], np.zeros(3 + len(GAMAS), dtype=np.int64)
            for pos, a in enumerate(ordem):
                if T[a] <= 0:
                    break
                X = int(d["nom"][j, a] - own[j, a])
                Xg = [int(x) for x in d["Xg"][:, j, a]] + [int(own[j, a])]
                if pos < PODA_TOPO or T[a] >= PODA_FRACAO * tot:
                    # cand = -2: retirou o partido do distrito por acordo com um vizinho que concorre ali
                    linha += [int(loc_agr[a]), int(T[a]), X, -2 if bloq[j, a] else int(esc[j, a])] + Xg
                else:
                    outros += [int(T[a]), X] + Xg
            if outros[0]:
                linha += [-1, int(outros[0]), int(outros[1]), -1] + [int(x) for x in outros[2:]]
            distritos.append(linha)
        mapas.append({"d": distritos, "aptos": [int(x) for x in d["aptos"]],
                      "pop": [int(x) for x in d["pop"]], "lula": [int(x) for x in d["lula"]],
                      "flavio": [int(x) for x in d["flavio"]]})
    return mapas


def exporta_uf(uf: str, idx_agr: dict) -> dict:
    with open(TRAB / "matrizes" / f"{uf}.pkl", "rb") as fh:
        r = pickle.load(fh)
    ins = r["ins"]
    loc_agr = np.array([idx_agr[a] for a in ins["agrs"]])
    dist = {k: mapas_json(r["por_k"], k, loc_agr) for k in r["por_k"]}
    coord = {L: {k: mapas_json(v, k, loc_agr) for k in v} for L, v in r["coord"].items()}
    return {"dist": dist, "coord": coord,
            "mapas": {k: ["".join(B64[x] for x in m) for m in pk["mapas"]] for k, pk in r["por_k"].items()},
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
    # bairros (nome do TSE) dos locais de votacao de cada tijolo de municipio quebrado
    L = locais_2026()
    L = L[L["uf"] == uf]
    info = dict(zip(zip(L["mun"], L["zona"], L["local"]), zip(L["bairro"], L["aptos"])))
    nomes_b, idx_b, bai = [], {}, []
    for n in t["nos"]:
        soma: dict[int, int] = {}
        if n["quebrado"]:
            for k in n["membros"]:
                b, ap = info.get(k, (None, 0))
                b = bairro_limpo(b)
                if not b:
                    continue
                if b not in idx_b:
                    idx_b[b] = len(nomes_b)
                    nomes_b.append(b)
                soma[idx_b[b]] = soma.get(idx_b[b], 0) + int(ap)
        bai.append([x for par in sorted(soma.items(), key=lambda p: -p[1]) for x in par])
    tij["bairros"] = nomes_b
    tij["bai"] = bai
    return topo, tij


MINUSCULAS = {"de", "da", "do", "das", "dos", "e"}


def bairro_limpo(b) -> str | None:
    if not isinstance(b, str):
        return None
    b = " ".join(b.split()).strip(" .-")
    if not b or b.upper() in ("", "-", "NAO INFORMADO", "NÃO INFORMADO", "ZONA RURAL", "RURAL", "S/N", "SEM BAIRRO"):
        return None
    ps = b.lower().split(" ")
    return " ".join(p if (i and p in MINUSCULAS) else p.upper() if p.strip("ivx") == "" else p[:1].upper() + p[1:]
                    for i, p in enumerate(ps))


def main() -> None:
    ufs = sys.argv[1:] or UFS
    ags = agremiacoes()
    idx_agr = {a["id"]: i for i, a in enumerate(ags)}
    rt = rateios()
    base = {"agrs": ags,
            "partidos": {nr: {"sigla": s, "cor": COR[nr]} for nr, s in SIGLA.items()},
            "rateios": rt, "nomes_rateio": RATEIOS, "gamas": list(GAMAS), "niveis": NIVEIS, "pop": populacao(), "ks": {}, "uf": {}}
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
        for nome, v in e["coord"].items():
            pasta = SAIDA_WEB / f"dist_{nome}"
            pasta.mkdir(exist_ok=True)
            (pasta / f"{uf}.json").write_text(json.dumps(v, separators=(",", ":")), "utf-8")
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

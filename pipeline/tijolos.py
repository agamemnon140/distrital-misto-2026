"""Tijolos dos distritos e grafo de adjacencia, por UF.

Tijolo = municipio inteiro, ou -- nos municipios com eleitorado maior que FRACAO_QUEBRA do
menor distrito-alvo do estado (entre os tres rateios) -- celula de Voronoi em volta dos locais
de votacao, recortada no poligono do municipio. Locais com o mesmo ponto viram um tijolo;
locais sem coordenada (ou fora do municipio) vao para o tijolo da mesma zona com mais eleitores.

Adjacencia: municipio-municipio pelos arcos compartilhados do TopoJSON; o resto (celulas) por
sobreposicao de buffer de ~1 m. Componentes desconexos (ilhas) sao ligados ao vizinho mais
proximo pelo centroide.

Saidas em TRAB/tijolos/{UF}.pkl  (dict: nos DataFrame, arestas, geometrias)
"""
from __future__ import annotations

import io
import json
import pickle
import sys
import zipfile
from collections import defaultdict

import networkx as nx
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import MultiPoint, Point, Polygon, MultiPolygon
from shapely.strtree import STRtree

from .caminhos import APURACAO, ELEICOES, TRAB, UFS
from .rateio import rateios

FRACAO_QUEBRA = 0.5
SAIDA = TRAB / "tijolos"
SAIDA.mkdir(parents=True, exist_ok=True)
EPS = 1e-5            # ~1 m em graus
AREA_MIN = 2e-9       # buffer-intersecao abaixo disso = toque de quina


# ---------------------------------------------------------------- TopoJSON
def topo_poligonos(uf: str):
    t = json.loads((APURACAO / "docs" / "dados" / "geo" / f"{uf}.json").read_text("utf-8"))
    sx, sy = t["transform"]["scale"]
    tx, ty = t["transform"]["translate"]
    arcos = []
    for a in t["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in a:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcos.append(pts)

    def anel(idx):
        pts = []
        for i in idx:
            seg = arcos[i] if i >= 0 else arcos[~i][::-1]
            pts.extend(seg if not pts else seg[1:])
        return pts

    geoms, arcos_de = {}, defaultdict(set)
    for g in next(iter(t["objects"].values()))["geometries"]:
        cd = int(g["properties"]["id"])
        polys = g["arcs"] if g["type"] == "MultiPolygon" else [g["arcs"]]
        ps = []
        for p in polys:
            aneis = [anel(r) for r in p]
            ps.append(Polygon(aneis[0], aneis[1:]))
            for r in p:
                for i in r:
                    arcos_de[i if i >= 0 else ~i].add(cd)
        geom = ps[0] if len(ps) == 1 else MultiPolygon(ps)
        geoms[cd] = shapely.make_valid(geom) if not geom.is_valid else geom
    viz = set()
    for muns in arcos_de.values():
        muns = sorted(muns)
        for i in range(len(muns)):
            for j in range(i + 1, len(muns)):
                viz.add((muns[i], muns[j]))
    return geoms, viz


# ---------------------------------------------------------------- locais
_LOCAIS = None


def locais_2026() -> pd.DataFrame:
    global _LOCAIS
    if _LOCAIS is None:
        z = zipfile.ZipFile(ELEICOES / "dados-secao" / "raw" / "dadosabertos" / "2026" / "eleitorado_local_votacao_2026.zip")
        partes = []
        for n in z.namelist():
            if not n.endswith(".csv") or n.endswith(("_ZZ.csv", "_BRASIL.csv", "_BR.csv")):
                continue
            d = pd.read_csv(z.open(n), sep=";", encoding="latin-1", decimal=",",
                            usecols=["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO",
                                     "NR_LATITUDE", "NR_LONGITUDE", "QT_ELEITOR_SECAO"])
            partes.append(d[d["NR_TURNO"] == 1])
        d = pd.concat(partes)
        d.columns = ["turno", "uf", "mun", "zona", "local", "lat", "lon", "aptos"]
        _LOCAIS = (d.groupby(["uf", "mun", "zona", "local"], as_index=False)
                   .agg(lat=("lat", "first"), lon=("lon", "first"), aptos=("aptos", "sum")))
    return _LOCAIS


def alvo_minimo(uf: str, aptos_uf: int) -> float:
    ks = [max(1, r[uf] // 2) for r in rateios().values()]
    return aptos_uf / max(ks)


# ---------------------------------------------------------------- quebra
def quebra_municipio(poly, loc: pd.DataFrame):
    """Devolve (lista de (geom, [(zona, local)...]), dict (zona,local)->indice)."""
    ok = loc["lat"].between(-35, 6) & loc["lon"].between(-75, -28) & (loc["lat"] != 0)
    dentro = poly.buffer(0.01)
    ok &= np.array([bool(o) and dentro.contains(Point(x, y)) for x, y, o in zip(loc["lon"], loc["lat"], ok)])
    com = loc[ok].copy()
    sem = loc[~ok]
    if len(com) == 0:
        return [(poly, list(zip(loc["zona"], loc["local"])))]
    com["px"] = com["lon"].round(5)
    com["py"] = com["lat"].round(5)
    pontos = com.groupby(["px", "py"])
    chaves = list(pontos.groups.keys())
    membros = [list(zip(g["zona"], g["local"])) for _, g in pontos]
    if len(chaves) == 1:
        celulas = [poly]
    else:
        mp = MultiPoint([Point(x, y) for x, y in chaves])
        vor = shapely.voronoi_polygons(mp, extend_to=poly.envelope.buffer(0.1), ordered=True)
        celulas = [c.intersection(poly) for c in vor.geoms]
    # celula vazia (ponto colado na borda) -> junta com o ponto mais proximo
    saida = []
    for c, m, (x, y) in zip(celulas, membros, chaves):
        saida.append([c, m, (x, y)])
    vivas = [s for s in saida if not s[0].is_empty and s[0].area > 0]
    for s in saida:
        if s[0].is_empty or s[0].area == 0:
            alvo = min(vivas, key=lambda v: (v[2][0] - s[2][0]) ** 2 + (v[2][1] - s[2][1]) ** 2)
            alvo[1].extend(s[1])
    # sem coordenada -> tijolo da mesma zona com mais eleitores
    ap = dict(zip(zip(loc["zona"], loc["local"]), loc["aptos"]))
    for z, l in zip(sem["zona"], sem["local"]):
        mesma = [v for v in vivas if any(zz == z for zz, _ in v[1])] or vivas
        alvo = max(mesma, key=lambda v: sum(ap.get(k, 0) for k in v[1]))
        alvo[1].append((z, l))
    return [(v[0], v[1]) for v in vivas]


def monta_uf(uf: str) -> dict:
    geoms, viz_mun = topo_poligonos(uf)
    loc = locais_2026()
    loc = loc[loc["uf"] == uf]
    ap_mun = loc.groupby("mun")["aptos"].sum().to_dict()
    alvo = alvo_minimo(uf, int(loc["aptos"].sum()))
    nos, geo = [], []
    no_de_mun: dict[int, list[int]] = {}
    for cd, poly in geoms.items():
        lm = loc[loc["mun"] == cd]
        if ap_mun.get(cd, 0) > FRACAO_QUEBRA * alvo and len(lm) > 1:
            partes = quebra_municipio(poly, lm)
        else:
            partes = [(poly, list(zip(lm["zona"], lm["local"])))]
        no_de_mun[cd] = []
        for g, membros in partes:
            no_de_mun[cd].append(len(nos))
            nos.append({"mun": cd, "membros": [(cd, z, l) for z, l in membros], "quebrado": len(partes) > 1})
            geo.append(g)
    # municipio novo sem poligono na malha (ex.: MT 73709): cada local vai para o tijolo
    # que contem o ponto, ou o mais proximo
    sem_geo = set(ap_mun) - set(geoms)
    if sem_geo:
        arv0 = STRtree(geo)
        for cd in sorted(sem_geo):
            for r in loc[loc["mun"] == cd].itertuples():
                pt = Point(r.lon, r.lat)
                dentro = [int(j) for j in arv0.query(pt, predicate="within")]
                alvo_no = dentro[0] if dentro else int(arv0.nearest(pt))
                nos[alvo_no]["membros"].append((cd, r.zona, r.local))
            print(f"  {uf}: municipio {cd} sem geometria -> locais anexados aos tijolos que os contem")

    # arestas
    arestas = set()
    for a, b in viz_mun:
        if len(no_de_mun[a]) == 1 and len(no_de_mun[b]) == 1:
            arestas.add((no_de_mun[a][0], no_de_mun[b][0]))
    quebrados = [i for i, n in enumerate(nos) if n["quebrado"]]
    if quebrados:
        buf = [g.buffer(EPS) for g in geo]
        arv = STRtree(buf)
        for i in quebrados:
            for j in arv.query(buf[i]):
                j = int(j)
                if j == i:
                    continue
                if nos[j]["mun"] != nos[i]["mun"] and not (
                        (min(nos[i]["mun"], nos[j]["mun"]), max(nos[i]["mun"], nos[j]["mun"])) in viz_mun):
                    continue
                if buf[i].intersection(buf[j]).area > AREA_MIN:
                    arestas.add((min(i, j), max(i, j)))
    G = nx.Graph()
    G.add_nodes_from(range(len(nos)))
    G.add_edges_from(arestas)
    # ilhas
    cent = np.array([[g.representative_point().x, g.representative_point().y] for g in geo])
    comps = sorted(nx.connected_components(G), key=len, reverse=True)
    while len(comps) > 1:
        grande = np.array(sorted(comps[0]))
        for c in comps[1:]:
            c = np.array(sorted(c))
            d = ((cent[c][:, None, :] - cent[grande][None, :, :]) ** 2).sum(-1)
            i, j = np.unravel_index(d.argmin(), d.shape)
            G.add_edge(int(c[i]), int(grande[j]))
        comps = sorted(nx.connected_components(G), key=len, reverse=True)
    ap_loc = dict(zip(zip(loc["mun"], loc["zona"], loc["local"]), loc["aptos"]))
    for i, n in enumerate(nos):
        n["aptos"] = int(sum(ap_loc.get(k, 0) for k in n["membros"]))
    return {"uf": uf, "nos": nos, "geo": geo, "arestas": sorted(G.edges()), "alvo_min": alvo}


def main() -> None:
    for uf in sys.argv[1:] or UFS:
        r = monta_uf(uf)
        with open(SAIDA / f"{uf}.pkl", "wb") as fh:
            pickle.dump(r, fh)
        nq = sum(1 for n in r["nos"] if n["quebrado"])
        print(f"{uf}: {len(r['nos']):>5} tijolos ({nq} de municipio quebrado), {len(r['arestas']):>6} arestas, "
              f"alvo min {r['alvo_min']:,.0f}", flush=True)


if __name__ == "__main__":
    main()

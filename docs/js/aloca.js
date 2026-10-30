/* Alocacao do distrital misto -- roda no navegador e no Node (testes de paridade).
 *
 * Por distrito (entradas [agr, T, X, cand] vindas do Python):
 *   voto(a) = T_a - (1-alfa) X_a           (X = voto nominal dos colegas que nao concorrem ali)
 *   o que sai, (1-alfa) X_a, vai para as outras agremiacoes na proporcao de T
 *   voto util: quem ficou do 3o lugar para baixo e nao lidera o proprio campo passa beta dos
 *   seus votos ao mais bem colocado do campo
 *   vence a maior votacao (maioria simples)
 * Lista (por estado): regra brasileira 2026 (QE/QP, 80%/20%, sobras + 3a fase do STF) ou D'Hondt.
 * Modelos: paralelo (distritos + lista independentes) ou compensatorio (cota total pela lista;
 * excedentes pela regra alema de 2023 ou pela antiga, com nivelamento).
 */
(function (root) {
  "use strict";

  function qeOficial(validos, vagas) {
    const q = validos / vagas;
    const inteiro = Math.floor(q);
    return (q - inteiro) > 0.5 ? inteiro + 1 : Math.max(inteiro, 1);
  }

  // cands: [{i, agr, v, nr}] -- so quem pode assumir; agrId: indice -> id (desempate igual ao Python)
  function porAgr(cands) {
    const por = new Map();
    const ord = cands.slice().sort((a, b) => (b.v - a.v) || (a.nr < b.nr ? -1 : a.nr > b.nr ? 1 : 0));
    for (const c of ord) {
      if (!por.has(c.agr)) por.set(c.agr, []);
      por.get(c.agr).push(c);
    }
    return por;
  }

  function maxMedia(lista, agrId) {
    // lista: [media, agr]; empata pelo id (max de tupla do Python)
    let best = null;
    for (const x of lista) {
      if (!best || x[0] > best[0] || (x[0] === best[0] && agrId[x[1]] > agrId[best[1]])) best = x;
    }
    return best;
  }

  function brasil(votosAgr, cands, vagas, agrId, validos) {
    if (vagas <= 0) return [];
    const agrs = Object.keys(votosAgr).map(Number);
    if (validos === undefined) validos = agrs.reduce((s, a) => s + votosAgr[a], 0);
    const qe = qeOficial(validos, vagas);
    const por = porAgr(cands);
    const eleitos = [];
    const ja = new Set();
    const obtidas = {};
    for (const a of agrs) {
      const qp = Math.floor(votosAgr[a] / qe);
      const leva = (por.get(a) || []).filter(c => c.v >= 0.10 * qe).slice(0, qp);
      for (const c of leva) { eleitos.push(c.i); ja.add(c.i); }
      obtidas[a] = leva.length;
    }
    const melhor = (a, piso) => {
      for (const c of (por.get(a) || [])) if (!ja.has(c.i) && c.v >= piso) return c;
      return null;
    };
    while (eleitos.length < vagas) {
      const comPiso = [];
      for (const a of agrs) if (votosAgr[a] >= 0.80 * qe && melhor(a, 0.20 * qe)) comPiso.push([votosAgr[a] / (obtidas[a] + 1), a]);
      let a, c;
      if (comPiso.length) {
        a = maxMedia(comPiso, agrId)[1];
        c = melhor(a, 0.20 * qe);
      } else {
        const livres = [];
        for (const b of agrs) if (melhor(b, 0)) livres.push([votosAgr[b] / (obtidas[b] + 1), b]);
        if (!livres.length) break;
        a = maxMedia(livres, agrId)[1];
        c = melhor(a, 0);
      }
      eleitos.push(c.i); ja.add(c.i); obtidas[a] += 1;
    }
    return eleitos;
  }

  function dhondt(votosAgr, cands, vagas, agrId) {
    const por = porAgr(cands);
    const agrs = Object.keys(votosAgr).map(Number).filter(a => por.has(a));
    const n = {};
    for (const a of agrs) n[a] = 0;
    const eleitos = [];
    for (let s = 0; s < vagas; s++) {
      const cand = agrs.filter(a => n[a] < por.get(a).length).map(a => [votosAgr[a] / (n[a] + 1), a]);
      if (!cand.length) break;
      const a = maxMedia(cand, agrId)[1];
      eleitos.push(por.get(a)[n[a]].i);
      n[a] += 1;
    }
    return eleitos;
  }

  const REGRAS = { brasil, dhondt };

  // ------------------------------------------------------------------ distrito
  function distrito(flat, alfa, beta, campoDe) {
    const n = flat.length / 4;
    const agr = new Array(n), T = new Array(n), X = new Array(n), cand = new Array(n);
    let Ttot = 0;
    for (let i = 0; i < n; i++) {
      agr[i] = flat[4 * i]; T[i] = flat[4 * i + 1]; X[i] = flat[4 * i + 2]; cand[i] = flat[4 * i + 3];
      Ttot += T[i];
    }
    const V = T.slice();
    if (alfa < 1) {
      const sai = X.map(x => (1 - alfa) * x);
      // recebe_b = sum_{a != b} sai_a * T_b / (Ttot - T_a)
      let somaFator = 0;
      const fator = new Array(n);
      for (let a = 0; a < n; a++) { fator[a] = Ttot - T[a] > 0 ? sai[a] / (Ttot - T[a]) : 0; somaFator += fator[a]; }
      for (let b = 0; b < n; b++) V[b] = T[b] - sai[b] + T[b] * (somaFator - fator[b]);
    }
    if (beta > 0 && n > 2) {
      const ordem = [...V.keys()].sort((a, b) => V[b] - V[a]);
      const lider = {};
      for (const i of ordem) {
        const c = agr[i] >= 0 ? campoDe[agr[i]] : null;
        if (c && !(c in lider)) lider[c] = i;
      }
      const V0 = V.slice();
      for (let pos = 2; pos < ordem.length; pos++) {
        const i = ordem[pos];
        const c = agr[i] >= 0 ? campoDe[agr[i]] : null;
        if (!c || lider[c] === i) continue;
        const m = beta * V0[i];
        V[i] -= m;
        V[lider[c]] += m;
      }
    }
    let venc = 0;
    for (let i = 1; i < n; i++) if (V[i] > V[venc] || (V[i] === V[venc] && agr[venc] < 0)) venc = i;
    let segundo = venc === 0 ? 1 : 0;
    for (let i = 0; i < n; i++) if (i !== venc && V[i] > V[segundo]) segundo = i;
    const tot = V.reduce((s, x) => s + x, 0);
    return { agr, V, cand, venc, segundo, tot };
  }

  // ------------------------------------------------------------------ estado
  /* uf: {votos_agr, cands:[[nr,nome,partido,agr,votos,eleitoReal]]}; mapa: {d:[flat...]};
   * p: {S, modelo, regra, alfa, beta, excedentes, campoDe, agrId} */
  function simulaUF(uf, mapa, p) {
    const regra = REGRAS[p.regra];
    const cands = uf.cands.map((c, i) => ({ i, nr: c[0], agr: c[3], v: c[4] }));
    const votosAgr = {};
    for (const k in uf.votos_agr) votosAgr[+k] = uf.votos_agr[k];
    const validos = Object.values(votosAgr).reduce((s, x) => s + x, 0);
    const porAgrEstado = porAgr(cands);

    const dist = mapa.d.map(flat => distrito(flat, p.alfa, p.beta, p.campoDe));
    // vencedor de cada distrito: candidato emparelhado; sem ninguem com base local, o mais votado
    // da agremiacao no estado que ainda nao concorre em outro distrito (candidato "generico")
    const concorrem = new Set();
    for (const d of dist) for (const c of d.cand) if (c >= 0) concorrem.add(c);
    const vencedores = [];
    dist.forEach((d, j) => {
      let a = d.agr[d.venc], c = d.cand[d.venc];
      if (c < 0 && a >= 0) {
        const lista = porAgrEstado.get(a) || [];
        const g = lista.find(x => !concorrem.has(x.i));
        c = g ? g.i : -1;
        if (g) concorrem.add(g.i);
      }
      const pct = d.tot > 0 ? d.V[d.venc] / d.tot : 0;
      vencedores.push({ j, agr: a, cand: c, pct, margem: d.tot > 0 ? (d.V[d.venc] - d.V[d.segundo]) / d.tot : 0 });
    });

    const k = dist.length;
    let eleitosDistrito = vencedores.filter(v => v.cand >= 0);
    let eleitosLista = [], tamanho = p.S, semEleito = [];
    if (p.modelo === "paralelo") {
      const ja = new Set(eleitosDistrito.map(v => v.cand));
      eleitosLista = regra(votosAgr, cands.filter(c => !ja.has(c.i)), p.S - k, p.agrId, validos);
    } else {
      const cotaDe = (S) => {
        const e = regra(votosAgr, cands, S, p.agrId, validos);
        const n = {};
        for (const i of e) n[cands[i].agr] = (n[cands[i].agr] || 0) + 1;
        return n;
      };
      const W = {};
      for (const v of eleitosDistrito) W[v.agr] = (W[v.agr] || 0) + 1;
      let cota = cotaDe(p.S);
      if (p.excedentes === "2023") {
        const manter = [];
        const porA = {};
        for (const v of eleitosDistrito) (porA[v.agr] = porA[v.agr] || []).push(v);
        for (const a in porA) {
          const ord = porA[a].slice().sort((x, y) => y.pct - x.pct);
          const lim = cota[a] || 0;
          manter.push(...ord.slice(0, lim));
          semEleito.push(...ord.slice(lim).map(v => v.j));
        }
        eleitosDistrito = manter;
      } else {
        let S = p.S;
        const ok = (c) => Object.keys(W).every(a => (c[a] || 0) >= W[a]);
        while (!ok(cota) && S < p.S + 3 * k) { S += 1; cota = cotaDe(S); }
        tamanho = S;
      }
      const ja = new Set(eleitosDistrito.map(v => v.cand));
      const kept = {};
      for (const v of eleitosDistrito) kept[v.agr] = (kept[v.agr] || 0) + 1;
      for (const a of Object.keys(cota).map(Number)) {
        let falta = cota[a] - (kept[a] || 0);
        for (const c of (porAgrEstado.get(a) || [])) {
          if (falta <= 0) break;
          if (!ja.has(c.i)) { eleitosLista.push(c.i); ja.add(c.i); falta -= 1; }
        }
      }
      if (p.excedentes !== "2023") tamanho = eleitosDistrito.length + eleitosLista.length;
    }
    return { dist, vencedores, eleitosDistrito, eleitosLista, semEleito, tamanho };
  }

  // ------------------------------------------------------------------ pais
  /* base: base.json; dist: {UF: {k: [mapa...]}}; p: {rateio, modelo, regra, alfa, beta, excedentes,
   * campoDe}. Devolve, por mapa m, as cadeiras por partido e por agremiacao, e o detalhe do mapa
   * pedido em p.detalhe. */
  function simulaPais(base, dist, p) {
    const agrId = base.agrs.map(a => a.id);
    const nMapas = Math.min(...Object.keys(base.uf).map(uf => dist[uf][base.ks[uf][p.rateio]].length));
    const porMapa = [];
    let detalhe = null;
    for (let m = 0; m < nMapas; m++) {
      const partido = {}, agr = {}, porUF = {};
      let total = 0, distritais = 0, semEleito = 0;
      for (const uf of Object.keys(base.uf)) {
        const k = base.ks[uf][p.rateio];
        const r = simulaUF(base.uf[uf], dist[uf][k][m], {
          S: base.rateios[p.rateio][uf], modelo: p.modelo, regra: p.regra, alfa: p.alfa, beta: p.beta,
          excedentes: p.excedentes, campoDe: p.campoDe, agrId,
        });
        const cs = base.uf[uf].cands;
        const conta = (i, tipo) => {
          const c = cs[i];
          partido[c[2]] = partido[c[2]] || { d: 0, l: 0 };
          partido[c[2]][tipo] += 1;
          agr[c[3]] = (agr[c[3]] || 0) + 1;
          total += 1;
        };
        r.eleitosDistrito.forEach(v => conta(v.cand, "d"));
        r.eleitosLista.forEach(i => conta(i, "l"));
        distritais += r.eleitosDistrito.length;
        semEleito += r.semEleito.length;
        if (p.detalhe === m) porUF[uf] = r;
      }
      porMapa.push({ partido, agr, total, distritais, semEleito });
      if (p.detalhe === m) detalhe = porUF;
    }
    return { porMapa, detalhe };
  }

  function quantil(xs, q) {
    const s = xs.slice().sort((a, b) => a - b);
    const pos = (s.length - 1) * q, lo = Math.floor(pos), hi = Math.ceil(pos);
    return s[lo] + (s[hi] - s[lo]) * (pos - lo);
  }

  root_export({ qeOficial, brasil, dhondt, distrito, simulaUF, simulaPais, quantil });

  function root_export(api) {
    if (typeof module !== "undefined" && module.exports) module.exports = api;
    else root.Aloca = api;
  }
})(typeof window !== "undefined" ? window : globalThis);

/* Alocacao do distrital misto -- roda no navegador e no Node (testes de paridade).
 *
 * Por distrito (entradas [agr, T, X, cand, X_g...] vindas do Python):
 *   voto(a) = T_a - X_a + alfa * X_a(gama)  (X = voto nominal dos colegas que nao concorrem ali;
 *            X(gama) = a parte que segue o candidato, menor quanto mais fraco ele e diante do colega)
 *   o que sai vai para as outras agremiacoes na proporcao de T
 *   voto util (beta): quem ficou do 3o lugar para baixo e nao lidera o proprio campo passa beta
 *   dos seus votos ao mais bem colocado do campo
 *   polarizacao (pi): depois, todo mundo do 3o lugar para baixo passa pi do que restou a um dos
 *   dois primeiros, o de campo mais proximo (esquerda-centro-direita); empate divide na proporcao
 *   vence a maior votacao (maioria simples)
 * Lista (por estado): regra brasileira 2026 (QE/QP, 80%/20%, sobras + 3a fase do STF) ou D'Hondt.
 * Modelos: paralelo (distritos + lista independentes), compensatorio (cota total pela lista;
 * excedentes pela regra alema de 2023 ou pela antiga, com nivelamento) ou so lista fechada.
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

  // semPiso: lista fechada -- sem voto nominal, caem as clausulas de 10% e 20% do candidato
  function brasil(votosAgr, cands, vagas, agrId, validos, semPiso) {
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
      const leva = (por.get(a) || []).filter(c => semPiso || c.v >= 0.10 * qe).slice(0, qp);
      for (const c of leva) { eleitos.push(c.i); ja.add(c.i); }
      obtidas[a] = leva.length;
    }
    const melhor = (a, piso) => {
      for (const c of (por.get(a) || [])) if (!ja.has(c.i) && c.v >= piso) return c;
      return null;
    };
    while (eleitos.length < vagas) {
      const comPiso = [];
      const piso = semPiso ? 0 : 0.20 * qe;
      for (const a of agrs) if (votosAgr[a] >= 0.80 * qe && melhor(a, piso)) comPiso.push([votosAgr[a] / (obtidas[a] + 1), a]);
      let a, c;
      if (comPiso.length) {
        a = maxMedia(comPiso, agrId)[1];
        c = melhor(a, piso);
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
  const POS = { esquerda: 0, centro: 1, direita: 2 };

  // parte de X que segue o candidato com um gama qualquer: interpola na grade [0, ...gamas]
  function herdado(flat, o, gama, gamas) {
    if (!gama) return flat[o + 2];
    const g = [0, ...gamas];
    const x = (q) => q === 0 ? flat[o + 2] : flat[o + 3 + q];
    for (let q = 1; q < g.length; q++) {
      if (gama <= g[q] + 1e-9) return x(q - 1) + (x(q) - x(q - 1)) * (gama - g[q - 1]) / (g[q] - g[q - 1]);
    }
    return x(g.length - 1);
  }

  /* p: {alfa, beta, gama, pi, campoDe, gamas}. Devolve tambem a decomposicao do voto de cada
   * entrada: P (nominal proprio ali), L (legenda), H (herdado dos colegas), R (recebido do que os
   * outros nao herdaram), U (saldo do voto util e da polarizacao); V = P + L + H + R + U */
  function distrito(flat, p) {
    const gamas = p.gamas || [];
    const passo = 5 + gamas.length;
    const n = flat.length / passo;
    if (!Number.isInteger(n)) throw new Error(`distrito: ${flat.length} valores nao fecham com passo ${passo} (faltou p.gamas?)`);
    const agr = new Array(n), T = new Array(n), cand = new Array(n), sai = new Array(n);
    const P = new Array(n), L = new Array(n), H = new Array(n);
    let Ttot = 0;
    for (let i = 0; i < n; i++) {
      const o = passo * i;
      agr[i] = flat[o]; T[i] = flat[o + 1]; cand[i] = flat[o + 3];
      P[i] = flat[o + passo - 1];
      L[i] = T[i] - flat[o + 2] - P[i];
      H[i] = p.alfa * herdado(flat, o, p.gama || 0, gamas);
      sai[i] = flat[o + 2] - H[i];
      Ttot += T[i];
    }
    const V = T.slice();
    if (sai.some(x => x > 0)) {
      // recebe_b = sum_{a != b} sai_a * T_b / (Ttot - T_a)
      let somaFator = 0;
      const fator = new Array(n);
      for (let a = 0; a < n; a++) { fator[a] = Ttot - T[a] > 0 ? sai[a] / (Ttot - T[a]) : 0; somaFator += fator[a]; }
      for (let b = 0; b < n; b++) V[b] = T[b] - sai[b] + T[b] * (somaFator - fator[b]);
    }
    const R = V.map((v, i) => v - (T[i] - sai[i]));
    const Vr = V.slice();
    const campo = agr.map(a => a >= 0 ? p.campoDe[a] : null);
    if (p.beta > 0 && n > 2) {
      const ordem = [...V.keys()].sort((a, b) => V[b] - V[a]);
      const lider = {};
      for (const i of ordem) if (campo[i] && !(campo[i] in lider)) lider[campo[i]] = i;
      const V0 = V.slice();
      for (let pos = 2; pos < ordem.length; pos++) {
        const i = ordem[pos], c = campo[i];
        if (!c || lider[c] === i) continue;
        const m = p.beta * V0[i];
        V[i] -= m;
        V[lider[c]] += m;
      }
    }
    if (p.pi > 0 && n > 2) {
      const ordem = [...V.keys()].sort((a, b) => V[b] - V[a]);
      const a = ordem[0], b = ordem[1];
      const V1 = V.slice();
      const dist = (i, j) => (campo[i] && campo[j]) ? Math.abs(POS[campo[i]] - POS[campo[j]]) : 9;
      for (let pos = 2; pos < ordem.length; pos++) {
        const i = ordem[pos], m = p.pi * V1[i];
        V[i] -= m;
        const da = dist(i, a), db = dist(i, b);
        if (da < db) V[a] += m;
        else if (db < da) V[b] += m;
        else { V[a] += m * V1[a] / (V1[a] + V1[b]); V[b] += m * V1[b] / (V1[a] + V1[b]); }
      }
    }
    let venc = 0;
    for (let i = 1; i < n; i++) if (V[i] > V[venc] || (V[i] === V[venc] && agr[venc] < 0)) venc = i;
    let segundo = venc === 0 ? 1 : 0;
    for (let i = 0; i < n; i++) if (i !== venc && V[i] > V[segundo]) segundo = i;
    const tot = V.reduce((s, x) => s + x, 0);
    const U = V.map((v, i) => v - Vr[i]);
    return { agr, V, cand, venc, segundo, tot, P, L, H, R, U };
  }

  // ------------------------------------------------------------------ estado
  /* uf: {votos_agr, cands:[[nr,nome,partido,agr,votos,eleitoReal]]}; mapa: {d:[flat...]};
   * p: {S, modelo, regra, alfa, beta, gama, pi, excedentes, campoDe, agrId, gamas} */
  function simulaUF(uf, mapa, p) {
    const regra = REGRAS[p.regra];
    const cands = uf.cands.map((c, i) => ({ i, nr: c[0], agr: c[3], v: c[4] }));
    const votosAgr = {};
    for (const k in uf.votos_agr) votosAgr[+k] = uf.votos_agr[k];
    const validos = Object.values(votosAgr).reduce((s, x) => s + x, 0);
    const porAgrEstado = porAgr(cands);

    const dist = mapa.d.map(flat => distrito(flat, p));
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
    if (p.modelo === "lista") {
      // so lista fechada, sem distritos; a ordem da lista e a votacao nominal de 2026
      eleitosDistrito = [];
      eleitosLista = regra(votosAgr, cands, p.S, p.agrId, validos, true);
    } else if (p.modelo === "paralelo") {
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
  /* base: base.json; dist: {UF: {k: [mapa...]}}; p: {rateio, modelo, regra, alfa, beta, gama, pi,
   * excedentes, campoDe}. Devolve, por mapa m, as cadeiras por partido e por agremiacao, e o detalhe do mapa
   * pedido em p.detalhe. */
  function simulaPais(base, dist, p) {
    const agrId = base.agrs.map(a => a.id);
    const nMapas = Math.min(...Object.keys(base.uf).map(uf => dist[uf][base.ks[uf][p.rateio]].length));
    const porMapa = [];
    let detalhe = null;
    for (let m = 0; m < nMapas; m++) {
      const partido = {}, agr = {}, porUF = {};
      let total = 0, distritais = 0, semEleito = 0, top2 = 0, nd = 0;
      for (const uf of Object.keys(base.uf)) {
        const k = base.ks[uf][p.rateio];
        const r = simulaUF(base.uf[uf], dist[uf][k][m], {
          S: base.rateios[p.rateio][uf], modelo: p.modelo, regra: p.regra, alfa: p.alfa, beta: p.beta,
          gama: p.gama, pi: p.pi, excedentes: p.excedentes, campoDe: p.campoDe, agrId, gamas: base.gamas,
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
        for (const d of r.dist) if (d.tot > 0) { top2 += (d.V[d.venc] + d.V[d.segundo]) / d.tot; nd += 1; }
        semEleito += r.semEleito.length;
        if (p.detalhe === m) porUF[uf] = r;
      }
      porMapa.push({ partido, agr, total, distritais, semEleito, top2: nd ? top2 / nd : 0 });
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

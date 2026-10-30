// Paridade JS <-> Python e invariantes do simulador.  Uso:  node tests/paridade.cjs
const fs = require("fs");
const path = require("path");
const A = require("../docs/js/aloca.js");

const D = path.join(__dirname, "..", "docs", "dados");
const base = JSON.parse(fs.readFileSync(path.join(D, "base.json"), "utf8"));
const agrId = base.agrs.map(a => a.id);
let falhas = 0;
const ok = (cond, msg) => { if (!cond) { falhas++; console.log("FALHOU:", msg); } };

// 1) regra brasileira com 100% das cadeiras = eleitos reais de 2026, nos 27 estados
let iguais = 0;
for (const [uf, u] of Object.entries(base.uf)) {
  const cands = u.cands.map((c, i) => ({ i, nr: c[0], agr: c[3], v: c[4] }));
  const va = {};
  for (const k in u.votos_agr) va[+k] = u.votos_agr[k];
  const e = new Set(A.brasil(va, cands, base.rateios.atual[uf], agrId));
  const r = new Set(u.cands.map((c, i) => c[5] ? i : -1).filter(i => i >= 0));
  const igual = e.size === r.size && [...e].every(i => r.has(i));
  ok(igual, `${uf}: regra brasileira nao reproduz os eleitos reais`);
  iguais += igual;
}
console.log(`regra brasileira (JS): ${iguais}/27 UFs reproduzem os eleitos reais`);

// 2) invariantes por cenario
const dist = {};
for (const uf of Object.keys(base.uf)) dist[uf] = JSON.parse(fs.readFileSync(path.join(D, "dist", uf + ".json"), "utf8"));
const campoDe = base.agrs.map(a => a.campo);
for (const rateio of base.nomes_rateio) {
  for (const modelo of ["paralelo", "compensatorio"]) {
    for (const exc of modelo === "paralelo" ? ["2023"] : ["2023", "antiga"]) {
      const r = A.simulaPais(base, dist, { rateio, modelo, regra: "brasil", alfa: 0.7, beta: 0.3, excedentes: exc, campoDe });
      for (const [m, x] of r.porMapa.entries()) {
        if (exc === "2023") ok(x.total === 513, `${rateio}/${modelo}/${exc} mapa ${m}: ${x.total} cadeiras`);
        else ok(x.total >= 513, `${rateio}/${modelo}/${exc} mapa ${m}: Casa menor que 513`);
      }
    }
  }
}

// 3) caso-limite: alfa = 1, beta = 0, compensatorio 2023 -> total por agremiacao = proporcional
const r = A.simulaPais(base, dist, { rateio: "atual", modelo: "compensatorio", regra: "brasil", alfa: 1, beta: 0, excedentes: "2023", campoDe });
const real = {};
for (const u of Object.values(base.uf)) for (const c of u.cands) if (c[5]) real[c[3]] = (real[c[3]] || 0) + 1;
for (const x of r.porMapa) for (const a in real) ok((x.agr[a] || 0) === real[a], `compensatorio != proporcional para ${agrId[a]}`);
console.log(falhas ? `${falhas} falha(s)` : "tudo certo");
process.exit(falhas ? 1 : 0);

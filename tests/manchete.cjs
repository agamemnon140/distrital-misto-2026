// Placar nacional (mediana e p10-p90 dos 50 mapas) num cenario.  Uso (tudo opcional):
//   node tests/manchete.cjs rateio=atual modelo=paralelo regra=brasil excedentes=2023 alfa=0.7 gama=0.5 \
//        afinidade=espectro coord=2.1 [beta=.. pi=.. lambda=.. kappa=..]
// coord=0 desliga a coordenacao. beta/pi/lambda/kappa ausentes = os calibrados para a combinacao.
const fs = require("fs");
const path = require("path");
const A = require("../docs/js/aloca.js");

const D = path.join(__dirname, "..", "docs", "dados");
const base = JSON.parse(fs.readFileSync(path.join(D, "base.json"), "utf8"));
const cal = JSON.parse(fs.readFileSync(path.join(D, "calibra.json"), "utf8"));
const arg = Object.fromEntries(process.argv.slice(2).map(s => s.split("=")));
const coord = +(arg.coord ?? 2.1);
const afinidade = arg.afinidade || "espectro";
const c = (cal[afinidade] || {})[coord ? "com" : "sem"] || {};
const p = {
  rateio: arg.rateio || "atual", modelo: arg.modelo || "paralelo", regra: arg.regra || "brasil",
  excedentes: arg.excedentes || "2023", alfa: +(arg.alfa ?? 0.7), gama: +(arg.gama ?? 0.5),
  afinidade, beta: +(arg.beta ?? c.beta), pi: +(arg.pi ?? c.pi), lambda: +(arg.lambda ?? c.lambda ?? 1),
  kappa: +(arg.kappa ?? c.kappa ?? 1), limiar: coord, campoDe: base.agrs.map(a => a.campo), pos: base.agrs.map(a => a.pos),
};
const pasta = coord ? `dist_c${coord.toFixed(1)}` : "dist";
const dist = {};
for (const uf of Object.keys(base.uf)) dist[uf] = JSON.parse(fs.readFileSync(path.join(D, pasta, uf + ".json"), "utf8"));
const r = A.simulaPais(base, dist, p);

const real = {};
for (const u of Object.values(base.uf)) for (const c of u.cands) if (c[5]) real[c[2]] = (real[c[2]] || 0) + 1;
const partidos = new Set([...Object.keys(real), ...r.porMapa.flatMap(x => Object.keys(x.partido))]);
const linhas = [...partidos].map(nr => {
  const t = r.porMapa.map(x => x.partido[nr] ? x.partido[nr].d + x.partido[nr].l : 0);
  const d = r.porMapa.map(x => x.partido[nr] ? x.partido[nr].d : 0);
  return { sig: base.partidos[nr] ? base.partidos[nr].sigla : nr, med: A.quantil(t, .5), lo: A.quantil(t, .1),
           hi: A.quantil(t, .9), dmed: A.quantil(d, .5), real: real[nr] || 0 };
}).sort((a, b) => b.med - a.med);
console.log(JSON.stringify(p, (k, v) => (k === "campoDe" || k === "pos") ? undefined : v));
console.log("partido        mediana  (p10-p90)  distritos  real   delta");
for (const l of linhas) if (l.med || l.real)
  console.log(`${l.sig.padEnd(14)} ${String(l.med).padStart(6)}  (${l.lo}-${l.hi})`.padEnd(34) +
              `${String(l.dmed).padStart(6)}  ${String(l.real).padStart(5)}  ${(l.med - l.real > 0 ? "+" : "") + (l.med - l.real)}`);
const tot = r.porMapa.map(x => x.total);
console.log(`Casa: ${A.quantil(tot, .5)}  distritais: ${A.quantil(r.porMapa.map(x => x.distritais), .5)}  sem eleito: ${A.quantil(r.porMapa.map(x => x.semEleito), .5)}  ` +
            `dois primeiros no distrito: ${(100 * A.quantil(r.porMapa.map(x => x.top2), .5)).toFixed(1)}%`);

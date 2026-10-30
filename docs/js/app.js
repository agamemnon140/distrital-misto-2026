/* Pagina do distrital misto 2026. Toda a alocacao roda aqui (js/aloca.js); o Python so
 * entrega mapas, votos por distrito e candidatos. */
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const fmt = d3.format(",d");
  const pct = (x, c = 1) => (x * 100).toFixed(c).replace(".", ",") + "%";
  const num = (x) => fmt(Math.round(x)).replace(/,/g, ".");
  const med = (xs) => Aloca.quantil(xs, 0.5);
  const fmtMed = (x) => Number.isInteger(x) ? String(x) : x.toFixed(1).replace(".", ",");

  const NOME = { UNIAO: "União", REPUBLICANOS: "Republicanos", PODE: "Podemos", SOLIDARIEDADE: "Solidariedade",
    MISSAO: "Missão", AVANTE: "Avante", NOVO: "Novo", CIDADANIA: "Cidadania", DEMOCRATA: "Democrata",
    MOBILIZA: "Mobiliza", AGIR: "Agir", REDE: "Rede" };
  const CAMPOS = ["esquerda", "centro", "direita"];
  const ROT_CAMPO = { esquerda: "Esquerda", centro: "Centro", direita: "Direita" };
  const UF_NOME = { AC: "Acre", AL: "Alagoas", AM: "Amazonas", AP: "Amapá", BA: "Bahia", CE: "Ceará", DF: "Distrito Federal",
    ES: "Espírito Santo", GO: "Goiás", MA: "Maranhão", MG: "Minas Gerais", MS: "Mato Grosso do Sul", MT: "Mato Grosso",
    PA: "Pará", PB: "Paraíba", PE: "Pernambuco", PI: "Piauí", PR: "Paraná", RJ: "Rio de Janeiro", RN: "Rio Grande do Norte",
    RO: "Rondônia", RR: "Roraima", RS: "Rio Grande do Sul", SC: "Santa Catarina", SE: "Sergipe", SP: "São Paulo", TO: "Tocantins" };
  const CAPITAL = { AC: "Rio Branco", AL: "Maceió", AM: "Manaus", AP: "Macapá", BA: "Salvador", CE: "Fortaleza", DF: "Brasília",
    ES: "Vitória", GO: "Goiânia", MA: "São Luís", MG: "Belo Horizonte", MS: "Campo Grande", MT: "Cuiabá", PA: "Belém",
    PB: "João Pessoa", PE: "Recife", PI: "Teresina", PR: "Curitiba", RJ: "Rio De Janeiro", RN: "Natal", RO: "Porto Velho",
    RR: "Boa Vista", RS: "Porto Alegre", SC: "Florianópolis", SE: "Aracaju", SP: "São Paulo", TO: "Palmas" };
  const METRO = {
    SP: ["Grande SP", ["São Paulo", "Guarulhos", "Osasco", "Santo André", "São Bernardo Do Campo", "Diadema", "Mauá", "Carapicuíba",
      "Barueri", "Taboão Da Serra", "Cotia", "Itaquaquecetuba", "Mogi Das Cruzes", "São Caetano Do Sul", "Suzano", "Embu Das Artes",
      "Ferraz De Vasconcelos", "Itapevi", "Francisco Morato", "Franco Da Rocha", "Caieiras", "Santana De Parnaíba", "Poá",
      "Ribeirão Pires", "Arujá", "Jandira"]],
    RJ: ["Grande Rio", ["Rio De Janeiro", "Niterói", "São Gonçalo", "Duque De Caxias", "Nova Iguaçu", "Belford Roxo",
      "São João De Meriti", "Nilópolis", "Mesquita", "Queimados", "Itaboraí", "Maricá", "Magé", "Japeri", "Seropédica", "Itaguaí"]],
    MG: ["Grande BH", ["Belo Horizonte", "Contagem", "Betim", "Ribeirão Das Neves", "Santa Luzia", "Ibirité", "Sabará",
      "Vespasiano", "Nova Lima", "Lagoa Santa", "Sarzedo", "Igarapé"]],
    BA: ["Grande Salvador", ["Salvador", "Lauro De Freitas", "Camaçari", "Simões Filho", "Candeias", "Dias D'ávila", "Madre De Deus"]],
  };

  const GAMA_PADRAO = 0.5;
  const MODELOS = ["paralelo", "compensatorio", "lista"];
  const NOME_MODELO = { paralelo: "paralelo", compensatorio: "compensatório", lista: "só lista fechada" };
  const S = {
    base: null, cal: null, dist: {}, geo: {}, mapas: {},
    p: null, padrao: null, campoDe: [], resultado: null, aba: "resultado",
    ufRes: "SP", mapaRes: null, ufMap: "SP", mapa: 0, camada: "vencedor", cacheUF: {},
  };
  const norm = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const css = (v) => getComputedStyle($(".viz-root")).getPropertyValue(v).trim();
  const corCampo = (c) => c ? css("--" + c) : css("--vazio");

  // ------------------------------------------------------------------ dados
  async function carrega() {
    const [base, cal] = await Promise.all([d3.json("dados/base.json"), d3.json("dados/calibra.json")]);
    S.base = base; S.cal = cal;
    S.campoDe = base.agrs.map(a => a.campo);
    S.padrao = { rateio: "atual", modelo: "paralelo", regra: "brasil", alfa: 0.7, gama: GAMA_PADRAO,
                 beta: cal.beta_padrao, pi: cal.pi_padrao, excedentes: "2023" };
    S.p = { ...S.padrao };
    lerHash();
    const ufs = Object.keys(base.uf);
    let feitos = 0;
    await Promise.all(ufs.map(uf => d3.json(`dados/dist/${uf}.json`).then(d => {
      S.dist[uf] = d; feitos++;
      $("#carregando").textContent = `Carregando os 27 estados… ${feitos}/27`;
    })));
    $("#carregando").hidden = true;
  }

  const partidoDe = (nr) => S.base.partidos[nr] || { sigla: nr, cor: "#999" };
  const sigla = (nr) => { const s = partidoDe(nr).sigla; return NOME[s] || s; };
  let agrDoPartido = null;
  function campoDoPartido(nr) {
    if (!agrDoPartido) {
      agrDoPartido = {};
      S.base.agrs.forEach((a, i) => a.partidos.forEach(p => { agrDoPartido[p] = i; }));
    }
    const a = agrDoPartido[nr];
    return a === undefined ? null : S.campoDe[a];
  }
  const siglaAgr = (a) => a < 0 ? "outros" : (NOME[S.base.agrs[a].sigla] || S.base.agrs[a].sigla);

  // ------------------------------------------------------------------ simulacao
  function params(extra) { return { ...S.p, campoDe: S.campoDe, gamas: S.base.gamas, ...extra }; }

  function simula() {
    const modelos = {};
    for (const modelo of MODELOS) modelos[modelo] = Aloca.simulaPais(S.base, S.dist, params({ modelo }));
    const sel = modelos[S.p.modelo];
    // mapa representativo: o mais perto da mediana do modelo escolhido
    const partidos = new Set();
    for (const m of Object.values(modelos)) for (const x of m.porMapa) Object.keys(x.partido).forEach(p => partidos.add(p));
    const tot = (x, p) => x.partido[p] ? x.partido[p].d + x.partido[p].l : 0;
    const mediana = {};
    for (const p of partidos) mediana[p] = med(sel.porMapa.map(x => tot(x, p)));
    let rep = 0, melhor = Infinity;
    sel.porMapa.forEach((x, m) => {
      let d = 0; for (const p of partidos) d += Math.abs(tot(x, p) - mediana[p]);
      if (d < melhor) { melhor = d; rep = m; }
    });
    const detalhe = Aloca.simulaPais(S.base, S.dist, params({ detalhe: rep })).detalhe;
    S.resultado = { modelos, sel, partidos: [...partidos], mediana, rep, detalhe, tot };
    if (S.mapaRes === null || S.mapaRes === undefined) S.mapaRes = rep;
    S.cacheUF = {};
  }

  // ------------------------------------------------------------------ hash (estado compartilhavel)
  function escreveHash() {
    const p = S.p;
    const h = `m=${p.modelo}&r=${p.rateio}&l=${p.regra}&a=${p.alfa}&g=${p.gama}&b=${p.beta}&p=${p.pi}&e=${p.excedentes}&t=${S.aba}&uf=${S.ufMap}&n=${S.mapa}&c=${S.camada}${zoomAtual ? "&z=" + encodeURIComponent(zoomAtual) : ""}`;
    history.replaceState(null, "", "#" + h);
  }
  function lerHash() {
    const q = new URLSearchParams(location.hash.slice(1));
    const g = (k, f) => q.has(k) ? f(q.get(k)) : undefined;
    const set = (campo, v) => { if (v !== undefined && v !== "" && !Number.isNaN(v)) S.p[campo] = v; };
    set("modelo", g("m", String)); set("rateio", g("r", String)); set("regra", g("l", String));
    set("alfa", g("a", Number)); set("beta", g("b", Number)); set("excedentes", g("e", String));
    set("gama", g("g", Number)); set("pi", g("p", Number));
    S.aba = g("t", String) || S.aba; S.ufMap = g("uf", String) || S.ufMap;
    S.mapa = g("n", Number) || 0; S.camada = g("c", String) || S.camada;
    zoomPendente = g("z", String) || null;
    abrirPendente = g("d", Number);
  }

  // ------------------------------------------------------------------ filtros
  function sincronizaFiltros() {
    $("#f-modelo").value = S.p.modelo; $("#f-rateio").value = S.p.rateio; $("#f-regra").value = S.p.regra;
    $("#f-exc").value = S.p.excedentes;
    for (const c of ["alfa", "gama", "beta", "pi"]) {
      $("#f-" + c).value = S.p[c];
      $("#o-" + c).textContent = S.p[c].toFixed(2).replace(".", ",");
    }
    $("#l-exc").classList.toggle("desligado", S.p.modelo !== "compensatorio");
    $("#f-exc").disabled = S.p.modelo !== "compensatorio";
  }
  let timer = null;
  function mudou(campo, valor, imediato) {
    S.p[campo] = valor;
    sincronizaFiltros();
    clearTimeout(timer);
    timer = setTimeout(() => { simula(); desenha(); }, imediato ? 0 : 120);
  }
  function ligaFiltros() {
    $("#f-modelo").onchange = e => mudou("modelo", e.target.value, true);
    $("#f-rateio").onchange = e => { S.mapaRes = null; mudou("rateio", e.target.value, true); };
    $("#f-regra").onchange = e => mudou("regra", e.target.value, true);
    $("#f-exc").onchange = e => mudou("excedentes", e.target.value, true);
    for (const c of ["alfa", "gama", "beta", "pi"]) $("#f-" + c).oninput = e => mudou(c, +e.target.value);
    $("#f-reset").onclick = () => { S.p = { ...S.padrao }; S.campoDe = S.base.agrs.map(a => a.campo); sincronizaFiltros(); simula(); desenha(); };
    document.querySelectorAll(".abas button").forEach(b => b.onclick = () => trocaAba(b.dataset.aba));
  }
  function trocaAba(aba) {
    S.aba = aba;
    document.querySelectorAll(".abas button").forEach(b => b.setAttribute("aria-selected", String(b.dataset.aba === aba)));
    for (const a of ["resultado", "mapas", "metodo"]) $("#aba-" + a).hidden = a !== aba;
    desenha();
  }

  function desenha() {
    escreveHash();
    if (S.aba === "resultado") desenhaResultado();
    else if (S.aba === "mapas") desenhaMapas();
    else desenhaMetodo();
  }

  // ------------------------------------------------------------------ dica
  const dica = $("#dica");
  function mostraDica(ev, html) {
    dica.innerHTML = html; dica.hidden = false;
    const w = dica.offsetWidth, h = dica.offsetHeight;
    let x = ev.clientX + 14, y = ev.clientY + 14;
    if (x + w > innerWidth - 8) x = ev.clientX - w - 14;
    if (y + h > innerHeight - 8) y = ev.clientY - h - 14;
    dica.style.left = x + "px"; dica.style.top = y + "px";
  }
  const escondeDica = () => { dica.hidden = true; };

  // ================================================================== RESULTADO
  function desenhaResultado() {
    const R = S.resultado, sel = R.sel, base = S.base;
    const real = {};
    for (const u of Object.values(base.uf)) for (const c of u.cands) if (c[5]) real[c[2]] = (real[c[2]] || 0) + 1;
    const linhas = R.partidos.concat(Object.keys(real).filter(p => !R.partidos.includes(p)))
      .filter((p, i, a) => a.indexOf(p) === i).map(p => {
        const par = R.modelos.paralelo.porMapa.map(x => R.tot(x, p));
        const comp = R.modelos.compensatorio.porMapa.map(x => R.tot(x, p));
        const lst = R.modelos.lista.porMapa.map(x => R.tot(x, p));
        const s = sel.porMapa.map(x => R.tot(x, p));
        // distritos ganhos: no modelo so de lista, mostra quantos o partido ganharia no paralelo
        const dis = (S.p.modelo === "lista" ? R.modelos.paralelo : sel).porMapa.map(x => x.partido[p] ? x.partido[p].d : 0);
        return { p, par: med(par), comp: med(comp), lst: med(lst), lo: Aloca.quantil(s, .1), hi: Aloca.quantil(s, .9),
                 sel: med(s), real: real[p] || 0, dis: med(dis) };
      }).filter(l => l.par || l.comp || l.lst || l.real).sort((a, b) => (b.sel - a.sel) || (b.real - a.real));

    // tiles
    const casa = med(sel.porMapa.map(x => x.total));
    const top = linhas[0];
    const distritais = med(sel.porMapa.map(x => x.distritais));
    const sem = med(sel.porMapa.map(x => x.semEleito));
    const k = Object.values(base.ks).reduce((s, x) => s + x[S.p.rateio], 0);
    const topDis = linhas.slice().sort((a, b) => b.dis - a.dis)[0];
    const nomeModelo = NOME_MODELO[S.p.modelo];
    const top2 = med(R.modelos.paralelo.porMapa.map(x => x.top2));
    const lista = S.p.modelo === "lista";
    $("#tiles").innerHTML = [
      tile(`Maior bancada (${nomeModelo})`, `${sigla(top.p)} ${fmtMed(top.sel)}`,
        `eleitos de verdade: ${top.real}` + (lista ? "" : ` · faixa ${fmtMed(top.lo)}–${fmtMed(top.hi)}`)),
      lista ? tile("Distritos", "0", `no paralelo seriam ${k}; ${sigla(topDis.p)} venceria ${fmtMed(topDis.dis)}`)
        : tile("Distritos", `${k}`, `${sigla(topDis.p)} vence ${fmtMed(topDis.dis)} (${pct(topDis.dis / k, 0)})`),
      tile("Cadeiras de lista", `${fmtMed(casa - distritais)}`, sem ? `${fmtMed(sem)} distritos ficam sem eleito (regra 2023)` :
        lista ? "lista fechada por estado, na ordem do voto nominal" :
        S.p.modelo === "paralelo" ? "metade proporcional, por estado" : "completam a proporção de cada partido"),
      tile("Votos nos dois primeiros", pct(top2, 0), `média dos distritos · prefeituras de 60 a 170 mil eleitores: ${pct(S.cal.top2_observado, 0)}`),
      tile("Tamanho da Câmara", `${fmtMed(casa)}`, casa > 513 ? "cresce com excedentes e nivelamento" : "513, como hoje"),
    ].join("");

    desenhaHemiciclo();

    // tabela por partido com dot plot
    const maxX = d3.max(linhas, l => Math.max(l.par, l.comp, l.lst, l.real, l.hi)) || 1;
    const W = 320, H = 22;
    const x = d3.scaleLinear().domain([0, maxX]).range([6, W - 6]);
    $("#th-delta").textContent = `Δ ${{ paralelo: "paralelo", compensatorio: "comp.", lista: "lista" }[S.p.modelo]}`;
    const tb = d3.select("#t-partidos tbody").html("");
    for (const l of linhas) {
      const tr = tb.append("tr");
      tr.append("td").text(sigla(l.p));
      const svg = tr.append("td").append("svg").attr("width", W).attr("height", H).attr("viewBox", `0 0 ${W} ${H}`)
        .attr("role", "img").attr("aria-label", `${sigla(l.p)}: paralelo ${fmtMed(l.par)}, compensatório ${fmtMed(l.comp)}, lista fechada ${fmtMed(l.lst)}, real ${l.real}`);
      svg.append("line").attr("class", "m-faixa").attr("x1", x(l.lo)).attr("x2", x(l.hi)).attr("y1", H / 2).attr("y2", H / 2);
      svg.append("line").attr("class", "m-real").attr("x1", x(l.real)).attr("x2", x(l.real)).attr("y1", 2).attr("y2", H - 2);
      svg.append("rect").attr("class", "m-lista").attr("x", x(l.lst) - 4).attr("y", H / 2 - 4).attr("width", 8).attr("height", 8);
      svg.append("circle").attr("class", "m-comp").attr("cx", x(l.comp)).attr("cy", H / 2).attr("r", 4.5);
      svg.append("circle").attr("class", "m-par").attr("cx", x(l.par)).attr("cy", H / 2).attr("r", 4.5);
      const d = l.sel - l.real;
      tr.append("td").attr("class", "n").html(`${fmtMed(l.par)}`);
      tr.append("td").attr("class", "n").text(fmtMed(l.comp));
      tr.append("td").attr("class", "n").text(fmtMed(l.lst));
      tr.append("td").attr("class", "n").text(l.real);
      tr.append("td").attr("class", "n").text((d > 0 ? "+" : d < 0 ? "−" : "") + fmtMed(Math.abs(d)));
      tr.append("td").attr("class", "n").text(fmtMed(l.dis));
    }

    // estado por estado
    const ufs = Object.keys(base.uf).sort((a, b) => base.rateios[S.p.rateio][b] - base.rateios[S.p.rateio][a]);
    const fu = $("#f-uf-res");
    if (!fu.options.length) {
      fu.innerHTML = ufs.map(u => `<option value="${u}">${UF_NOME[u]}</option>`).join("");
      fu.value = S.ufRes;
      fu.onchange = e => { S.ufRes = e.target.value; desenhaUFRes(); };
      const fm = $("#f-mapa-res");
      fm.innerHTML = d3.range(50).map(m => `<option value="${m}">${m + 1}</option>`).join("");
      fm.onchange = e => { S.mapaRes = +e.target.value; desenhaUFRes(); };
    }
    desenhaUFRes();
  }

  function tile(rot, val, det) {
    return `<div class="tile"><div class="rot">${rot}</div><div class="val">${val}</div><div class="det">${det}</div></div>`;
  }

  function cadeirasHemi(detalhe) {
    const assentos = [];
    for (const [uf, r] of Object.entries(detalhe)) {
      const cs = S.base.uf[uf].cands;
      for (const v of r.eleitosDistrito) assentos.push({ i: v.cand, uf, tipo: "d", j: v.j });
      for (const i of r.eleitosLista) assentos.push({ i, uf, tipo: "l" });
      for (const a of assentos) if (a.uf === uf && !a.c) a.c = cs[a.i];
    }
    const nPart = {};
    for (const a of assentos) nPart[a.c[2]] = (nPart[a.c[2]] || 0) + 1;
    const ordCampo = { esquerda: 0, centro: 1, direita: 2 };
    assentos.forEach(a => { a.campo = campoDoPartido(a.c[2]); });
    assentos.sort((a, b) => {
      const ca = ordCampo[a.campo] ?? 1, cb = ordCampo[b.campo] ?? 1;
      if (ca !== cb) return ca - cb;
      // na esquerda o maior fica na ponta esquerda; na direita, na ponta direita
      const sinal = ca === 2 ? 1 : -1;
      if (a.c[2] !== b.c[2]) return sinal * (nPart[a.c[2]] - nPart[b.c[2]]) || (a.c[2] < b.c[2] ? -1 : 1);
      return a.tipo === b.tipo ? 0 : a.tipo === "d" ? -1 : 1;
    });
    return assentos;
  }

  function desenhaHemiciclo() {
    const R = S.resultado;
    const assentos = cadeirasHemi(R.detalhe);
    const n = assentos.length;
    const W = 900, H = 470, cx = W / 2, cy = H - 20, R0 = 430;
    const linhas = Math.max(8, Math.round(Math.sqrt(n / 3.2)));
    const raios = d3.range(linhas).map(i => R0 * (0.36 + 0.64 * i / (linhas - 1)));
    const somaR = d3.sum(raios);
    const porLinha = raios.map(r => Math.round(n * r / somaR));
    let dif = n - d3.sum(porLinha);
    for (let i = linhas - 1; dif !== 0; i = (i - 1 + linhas) % linhas) { porLinha[i] += Math.sign(dif); dif -= Math.sign(dif); }
    const pos = [];
    raios.forEach((r, i) => {
      const m = porLinha[i];
      for (let j = 0; j < m; j++) {
        const t = m === 1 ? Math.PI / 2 : Math.PI - j * Math.PI / (m - 1);
        pos.push({ x: cx + r * Math.cos(t), y: cy - r * Math.sin(t), t, r });
      }
    });
    pos.sort((a, b) => (b.t - a.t) || (a.r - b.r));
    const rs = Math.min(R0 * 0.64 / linhas * 0.42, Math.PI * raios[0] / porLinha[0] * 0.42);
    const svg = d3.select("#hemi").html("").append("svg").attr("viewBox", `-90 -36 ${W + 180} ${H + 36}`)
      .attr("role", "img").attr("aria-label", `Hemiciclo com ${n} cadeiras, mapa ${R.rep + 1}`);
    svg.selectAll("circle").data(assentos).join("circle")
      .attr("cx", (d, i) => pos[i].x).attr("cy", (d, i) => pos[i].y)
      .attr("r", d => d.tipo === "d" ? rs : rs - 1)
      .attr("fill", d => d.tipo === "d" ? corCampo(d.campo) : "none")
      .attr("stroke", d => corCampo(d.campo)).attr("stroke-width", d => d.tipo === "d" ? 0 : 2)
      .on("mousemove", (ev, d) => mostraDica(ev, `<b>${d.c[1]}</b> (${sigla(d.c[2])}, ${d.uf})<br>
          <span class="m">${d.tipo === "d" ? "Distrito " + (d.j + 1) : "Lista"} · ${fmt(d.c[4]).replace(/,/g, ".")} votos em 2026${d.c[5] ? " · eleito de verdade" : ""}</span>`))
      .on("mouseleave", escondeDica);
    // rotulos dos maiores partidos
    const grupos = d3.groups(assentos.map((a, i) => ({ ...a, i })), a => a.c[2]).filter(g => g[1].length >= 18);
    for (const [p, as] of grupos) {
      const meio = pos[as[Math.floor(as.length / 2)].i];
      const t = meio.t, rr = R0 + 16;
      svg.append("text").attr("x", cx + rr * Math.cos(t)).attr("y", cy - rr * Math.sin(t))
        .attr("text-anchor", t > Math.PI * 0.55 ? "end" : t < Math.PI * 0.45 ? "start" : "middle")
        .attr("font-size", 13).attr("fill", "var(--text-primary)").text(`${sigla(p)} ${as.length}`);
    }
    svg.append("text").attr("x", cx).attr("y", cy - 30).attr("text-anchor", "middle").attr("font-size", 34)
      .attr("font-weight", 650).attr("fill", "var(--text-primary)").text(n);
    svg.append("text").attr("x", cx).attr("y", cy - 8).attr("text-anchor", "middle").attr("font-size", 12)
      .attr("fill", "var(--text-secondary)").text("cadeiras");
    $("#h-hemi").textContent = `Câmara simulada — ${{ paralelo: "paralelo 50/50", compensatorio: "compensatório", lista: "só lista fechada" }[S.p.modelo]}`;
    $("#n-hemi").textContent = S.p.modelo === "lista"
      ? "Sem distritos: todo mundo sai de listas estaduais fechadas, na ordem da votação nominal de 2026. Cor: campo político do partido."
      : `Mapa ${R.rep + 1} de 50, o mais próximo da mediana. Bolinha cheia: eleito no distrito; anel: eleito pela lista. Cor: campo político do partido.`;
    $("#leg-hemi").innerHTML = CAMPOS.map(c => `<span><span class="sw" style="background:${corCampo(c)}"></span>${ROT_CAMPO[c]}</span>`).join("") +
      `<span><span class="sw" style="background:var(--text-secondary)"></span>distrito</span><span><span class="sw anel" style="border-color:var(--text-secondary)"></span>lista</span>`;
  }

  function desenhaUFRes() {
    const uf = S.ufRes, base = S.base, m = S.mapaRes;
    $("#f-mapa-res").value = m;
    const k = base.ks[uf][S.p.rateio];
    const r = Aloca.simulaUF(base.uf[uf], S.dist[uf][k][m], { ...params(), S: base.rateios[S.p.rateio][uf], agrId: base.agrs.map(a => a.id) });
    const cs = base.uf[uf].cands;
    const por = {};
    const add = (i, t) => { const p = cs[i][2]; por[p] = por[p] || { d: 0, l: 0, real: 0 }; por[p][t]++; };
    r.eleitosDistrito.forEach(v => add(v.cand, "d"));
    r.eleitosLista.forEach(i => add(i, "l"));
    cs.forEach(c => { if (c[5]) { por[c[2]] = por[c[2]] || { d: 0, l: 0, real: 0 }; por[c[2]].real++; } });
    $("#h-uf-part").textContent = `${UF_NOME[uf]}: ${base.rateios[S.p.rateio][uf]} cadeiras, ${k} distritos (mapa ${m + 1})`;
    const tb = d3.select("#t-uf-partidos tbody").html("");
    Object.entries(por).sort((a, b) => (b[1].d + b[1].l - a[1].d - a[1].l) || b[1].real - a[1].real).forEach(([p, v]) => {
      const tr = tb.append("tr");
      tr.append("td").text(sigla(p));
      [v.d, v.l, v.d + v.l, v.real].forEach(x => tr.append("td").attr("class", "n").text(x));
    });
    const td = d3.select("#t-uf-dist tbody").html("");
    const sem = new Set(r.semEleito);
    $("#h-uf-dist").textContent = S.p.modelo === "lista" ? "Distritos deste mapa (só no distrital; a lista fechada não usa)" : "Distritos deste mapa";
    const regs = S.mapas[uf] ? regioes(uf, k, m) : null;
    if (!regs) carregaUF(uf).then(() => { if (S.ufRes === uf) desenhaUFRes(); });
    const set = abertosDe("res", JSON.stringify([uf, S.p.rateio, m]));
    r.vencedores.forEach((v, j) => {
      const d = r.dist[j];
      const tr = td.append("tr");
      tr.append("td").attr("class", "seta").text(j + 1);
      const c = v.cand >= 0 ? cs[v.cand] : null;
      tr.append("td").html(c ? `${c[1]} <span class="faixa-txt">${sigla(c[2])}</span>${sem.has(j) ? ' <span class="faixa-txt">(sem cobertura: distrito fica vago)</span>' : ""}` : siglaAgr(v.agr));
      tr.append("td").attr("class", "n").text(pct(v.pct));
      tr.append("td").attr("class", "n").text(pct(v.margem));
      tr.append("td").text(siglaAgr(d.agr[d.segundo]));
      tr.append("td").attr("class", "regiao").html(regs ? textoRegiao(regs[j], true) : "…");
      ligaDetalhe(td, tr, 6, set, j, () => htmlCandidatos(uf, r, j));
    });
    const lista = r.eleitosLista.map(i => cs[i]).sort((a, b) => b[4] - a[4]);
    $("#lista-uf").textContent = lista.length ? lista.map(c => `${c[1]} (${sigla(c[2])})`).join(" · ") : "nenhum";
  }

  // ================================================================== MAPAS
  async function carregaUF(uf) {
    if (!S.geo[uf]) {
      const [g, m] = await Promise.all([d3.json(`dados/geo/${uf}.json`), d3.json(`dados/mapas/${uf}.json`)]);
      S.geo[uf] = g; S.mapas[uf] = m;
    }
  }
  // a simplificacao do TopoJSON as vezes inverte um anel minusculo; para o d3-geo isso vira
  // "o globo menos o poligono". Toda feicao com mais de meia esfera e desvirada.
  function desvira(f) {
    if (!f.geometry || d3.geoArea(f) <= 2 * Math.PI) return f;
    const c = f.geometry.coordinates;
    if (f.geometry.type === "Polygon") c.forEach(r => r.reverse());
    else if (f.geometry.type === "MultiPolygon") c.forEach(p => p.forEach(r => r.reverse()));
    return f;
  }
  const B64 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_";
  const dec = (s) => Uint8Array.from(s, ch => B64.indexOf(ch));
  const esc = (s) => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // cidades e bairros de cada distrito de um mapa. Bairro = o do cadastro do local de votacao
  // (TSE), so nos municipios quebrados em celulas
  const cacheReg = {};
  function regioes(uf, k, m) {
    const chave = `${uf}|${k}|${m}`;
    if (cacheReg[chave]) return cacheReg[chave];
    const tij = S.mapas[uf].tij, a = dec(S.mapas[uf].mapas[k][m]);
    if (!tij.munTot) {
      tij.munTot = {};
      tij.mun.forEach((mu, i) => { tij.munTot[mu] = (tij.munTot[mu] || 0) + tij.aptos[i]; });
    }
    const por = Array.from({ length: k }, () => ({ mun: new Map(), bai: new Map() }));
    for (let i = 0; i < a.length; i++) {
      const r = por[a[i]], mu = tij.mun[i], b = tij.bai[i];
      r.mun.set(mu, (r.mun.get(mu) || 0) + tij.aptos[i]);
      if (!r.bai.has(mu)) r.bai.set(mu, new Map());
      const bm = r.bai.get(mu);
      for (let q = 0; q < b.length; q += 2) bm.set(b[q], (bm.get(b[q]) || 0) + b[q + 1]);
    }
    const out = por.map(r => {
      const muns = [...r.mun].sort((x, y) => y[1] - x[1])
        .map(([mu, ap]) => ({ mu, ap, parte: ap < 0.98 * tij.munTot[mu], pctMun: ap / tij.munTot[mu] }));
      const bairros = {};
      for (const x of muns) if (x.parte && r.bai.get(x.mu).size)
        bairros[x.mu] = [...r.bai.get(x.mu)].sort((p, q) => q[1] - p[1]).map(([b]) => tij.bairros[b]);
      return { muns, bairros };
    });
    cacheReg[chave] = out;
    return out;
  }
  function textoRegiao(rg, curto) {
    const nM = curto ? 3 : 6, nB = curto ? 3 : 6;
    const ms = rg.muns.slice(0, nM).map(x => esc(x.mu) + (x.parte ? ` <span class="faixa-txt">(${pct(x.pctMun, 0)} da cidade)</span>` : ""));
    const resto = rg.muns.length - nM;
    let s = ms.join(", ") + (resto > 0 ? ` e mais ${resto} ${resto === 1 ? "município" : "municípios"}` : "");
    const partes = rg.muns.filter(x => rg.bairros[x.mu]).slice(0, curto ? 1 : 2);
    for (const x of partes) {
      const bs = rg.bairros[x.mu];
      s += `<br>${curto ? "" : esc(x.mu) + ": "}${bs.slice(0, nB).map(esc).join(", ")}${bs.length > nB ? "…" : ""}`;
    }
    return s;
  }

  function simulaUFTodos(uf) {
    const chave = JSON.stringify([uf, S.p, S.campoDe]);
    if (S.cacheUF[chave]) return S.cacheUF[chave];
    const base = S.base, k = base.ks[uf][S.p.rateio];
    const pr = { ...params(), S: base.rateios[S.p.rateio][uf], agrId: base.agrs.map(a => a.id) };
    const res = S.dist[uf][k].map(mapa => Aloca.simulaUF(base.uf[uf], mapa, pr));
    S.cacheUF[chave] = { k, res };
    return S.cacheUF[chave];
  }

  let zoomAtual = null, zoomPendente = null;
  async function desenhaMapas() {
    const base = S.base;
    const fu = $("#f-uf-map");
    if (!fu.options.length) {
      const ufs = Object.keys(base.uf).sort((a, b) => UF_NOME[a].localeCompare(UF_NOME[b]));
      fu.innerHTML = ufs.map(u => `<option value="${u}">${UF_NOME[u]}</option>`).join("");
      fu.onchange = e => { S.ufMap = e.target.value; zoomAtual = null; desenhaMapas(); };
      $("#f-mapa").oninput = e => { S.mapa = +e.target.value; desenhaMapas(); };
      $("#b-ant").onclick = () => { S.mapa = (S.mapa + 49) % 50; desenhaMapas(); };
      $("#b-prox").onclick = () => { S.mapa = (S.mapa + 1) % 50; desenhaMapas(); };
      $("#f-camada").onchange = e => { S.camada = e.target.value; desenhaMapas(); };
    }
    fu.value = S.ufMap; $("#f-mapa").value = S.mapa; $("#f-camada").value = S.camada;
    $("#o-mapa").textContent = `${S.mapa + 1} de 50`;
    const uf = S.ufMap;
    await carregaUF(uf);
    if (S.aba !== "mapas" || S.ufMap !== uf) return;
    escreveHash();
    const { k, res } = simulaUFTodos(uf);
    const topo = S.geo[uf], obj = topo.objects.data;
    const tij = S.mapas[uf].tij;
    const atrib = S.mapas[uf].mapas[k].map(dec);
    const a = atrib[S.mapa];
    const r = res[S.mapa];
    const dm = S.dist[uf][k][S.mapa];
    const cs = base.uf[uf].cands;

    // --- geometria
    const svg = d3.select("#mapa");
    const W = svg.node().clientWidth || 760, H = svg.node().clientHeight || 620;
    svg.attr("viewBox", `0 0 ${W} ${H}`);
    const feats = (S.feats && S.feats.uf === uf) ? S.feats.f : topojson.feature(topo, obj).features.map(desvira);
    S.feats = { uf, f: feats };
    const proj = d3.geoMercator().fitExtent([[10, 10], [W - 10, H - 10]], { type: "FeatureCollection", features: feats });
    const path = d3.geoPath(proj);
    let g = svg.select("g.raiz");
    if (g.empty() || svg.attr("data-uf") !== uf) {
      svg.html("").attr("data-uf", uf);
      g = svg.append("g").attr("class", "raiz");
      g.append("g").attr("class", "tijs");
      g.append("path").attr("class", "fronteira");
      g.append("path").attr("class", "contorno");
      g.append("path").attr("class", "realce");
      g.append("g").attr("class", "rotulos");
      const zoom = d3.zoom().scaleExtent([1, 60]).on("zoom", ev => {
        g.attr("transform", ev.transform);
        g.selectAll(".rotulos text").style("font-size", 11 / ev.transform.k + "px").style("stroke-width", 3 / ev.transform.k + "px");
      });
      svg.call(zoom);
      svg.node().__zoom_ref = zoom;
      zoomAtual = null;
    }
    const zoom = svg.node().__zoom_ref;
    const tijs = g.select("g.tijs").selectAll("path.tij").data(feats, f => f.properties.i)
      .join("path").attr("class", "tij").attr("d", path);

    // --- botoes de zoom
    const presets = [["Estado", null], ["Capital", [CAPITAL[uf]]]];
    if (METRO[uf]) presets.push([METRO[uf][0], METRO[uf][1]]);
    const zz = d3.select("#zooms").html("");
    const aplicaZoom = (nome, muns, dur) => {
      zoomAtual = nome;
      zz.selectAll("button").classed("ativo", function () { return this.textContent === nome; });
      escreveHash();
      const alvoT = (() => {
        if (!muns) return d3.zoomIdentity;
        const alvo = new Set(muns.map(norm));
        const sub = feats.filter(f => alvo.has(norm(tij.mun[f.properties.i])));
        if (!sub.length) return d3.zoomIdentity;
        const [[x0, y0], [x1, y1]] = path.bounds({ type: "FeatureCollection", features: sub });
        const s = Math.min(60, 0.9 / Math.max((x1 - x0) / W, (y1 - y0) / H));
        return d3.zoomIdentity.translate(W / 2, H / 2).scale(s).translate(-(x0 + x1) / 2, -(y0 + y1) / 2);
      })();
      if (dur) svg.transition().duration(dur).call(zoom.transform, alvoT);
      else svg.call(zoom.transform, alvoT);
    };
    for (const [nome, muns] of presets) {
      zz.append("button").attr("class", "fantasma" + (zoomAtual === nome ? " ativo" : "")).attr("type", "button").text(nome)
        .on("click", () => aplicaZoom(nome, muns, 600));
    }
    if (zoomPendente) {
      const pr = presets.find(x => x[0] === zoomPendente);
      zoomPendente = null;
      if (pr) aplicaZoom(pr[0], pr[1], 0);
    }

    // --- metricas por distrito
    const media = (arr) => d3.sum(arr) / arr.length;
    const mPop = media(dm.pop), mAp = media(dm.aptos);
    const venc = r.vencedores;
    const campoD = venc.map(v => v.agr >= 0 ? S.campoDe[v.agr] : null);
    const semEl = new Set(r.semEleito);
    // instabilidade: em quantos mapas o vencedor do distrito de cada tijolo difere do mais comum
    let instavel = null;
    if (S.camada === "instavel") {
      const n = a.length;
      instavel = new Float32Array(n);
      const cont = Array.from({ length: n }, () => new Map());
      atrib.forEach((am, m) => {
        const vm = res[m].vencedores;
        for (let i = 0; i < n; i++) { const w = vm[am[i]].agr; cont[i].set(w, (cont[i].get(w) || 0) + 1); }
      });
      for (let i = 0; i < n; i++) instavel[i] = 1 - Math.max(...cont[i].values()) / atrib.length;
    }
    const seq = [css("--seq-0"), css("--seq-1"), css("--seq-2"), css("--seq-3"), css("--seq-4")];
    const div = (t) => d3.interpolateRgbBasis([css("--div-neg"), css("--div-mid"), css("--div-pos")])(t);
    const corTij = (i) => {
      const d = a[i];
      switch (S.camada) {
        case "lula": { const l = dm.lula[d], f = dm.flavio[d]; const s = l / (l + f); return div(Math.max(0, Math.min(1, (s - 0.5) / 0.3 + 0.5))); }
        case "pop": return div(Math.max(0, Math.min(1, (dm.pop[d] / mPop - 1) / 0.5 + 0.5)));
        case "aptos": return div(Math.max(0, Math.min(1, (dm.aptos[d] / mAp - 1) / 0.2 + 0.5)));
        case "instavel": return seq[Math.min(4, Math.floor(instavel[i] / 0.5 * 5))];
        default: return semEl.has(d) ? css("--vazio") : corCampo(campoD[d]);
      }
    };
    tijs.attr("fill", f => corTij(f.properties.i)).attr("stroke", f => corTij(f.properties.i));
    g.select(".fronteira").attr("d", path(topojson.mesh(topo, obj, (x, y) => x !== y && a[x.properties.i] !== a[y.properties.i])));
    g.select(".contorno").attr("d", path(topojson.mesh(topo, obj, (x, y) => x === y)));
    g.select(".realce").attr("d", null);
    // rotulos: numero do distrito no maior tijolo... usa o centroide da uniao
    const geomsPorD = d3.range(k).map(() => []);
    obj.geometries.forEach(gm => geomsPorD[a[gm.properties.i]].push(gm));
    const formas = geomsPorD.map(gs => desvira({ type: "Feature", geometry: topojson.merge(topo, gs) }));
    g.select("g.rotulos").selectAll("text").data(formas).join("text")
      .attr("x", f => path.centroid(f)[0]).attr("y", f => path.centroid(f)[1]).attr("text-anchor", "middle")
      .attr("dy", "0.35em").text((f, j) => j + 1);
    const t = d3.zoomTransform(svg.node());
    g.selectAll(".rotulos text").style("font-size", 11 / t.k + "px").style("stroke-width", 3 / t.k + "px");

    const regs = regioes(uf, k, S.mapa);
    const htmlDist = (d) => {
      const v = venc[d], c = v.cand >= 0 ? cs[v.cand] : null, dd = r.dist[d];
      const l = dm.lula[d], f = dm.flavio[d];
      return `<b>Distrito ${d + 1}</b><br><span class="regiao">${textoRegiao(regs[d], true)}</span><br>` +
        `<span class="m">Eleitorado</span> ${num(dm.aptos[d])} (${dm.aptos[d] >= mAp ? "+" : "−"}${pct(Math.abs(dm.aptos[d] / mAp - 1))})<br>` +
        `<span class="m">População</span> ${num(dm.pop[d])}<br>` +
        `<span class="m">2º turno</span> Lula ${pct(l / (l + f))} · Flávio ${pct(f / (l + f))}<br>` +
        `<span class="m">Eleito</span> ${c ? `${c[1]} (${sigla(c[2])})` : siglaAgr(v.agr)} ${pct(v.pct)}` +
        `${semEl.has(d) ? "<br><span class='m'>sem cobertura de legenda: fica vago</span>" : ""}<br>` +
        `<span class="m">2º lugar</span> ${siglaAgr(dd.agr[dd.segundo])}, margem ${pct(v.margem)}`;
    };
    tijs.on("mousemove", (ev, f) => {
      const d = a[f.properties.i];
      g.select(".realce").attr("d", path(formas[d]));
      const bi = tij.bai[f.properties.i];
      let extra = `<br><span class="m">Aqui: ${esc(tij.mun[f.properties.i])}${bi.length ? " · " + esc(tij.bairros[bi[0]]) : ""}</span>`;
      if (instavel) extra += `<br><span class="m">vencedor diferente do mais comum em ${pct(instavel[f.properties.i], 0)} dos mapas</span>`;
      mostraDica(ev, htmlDist(d) + extra);
    }).on("mouseleave", () => { g.select(".realce").attr("d", null); escondeDica(); })
      .on("click", (ev, f) => abreDistrito(a[f.properties.i]));

    // --- legenda
    const leg = $("#leg-mapa");
    const rampa = (cores, a0, a1) => `${a0}<span class="rampa">${cores.map(c => `<span style="background:${c}"></span>`).join("")}</span>${a1}`;
    if (S.camada === "vencedor") leg.innerHTML = CAMPOS.map(c => `<span><span class="sw" style="background:${corCampo(c)}"></span>${ROT_CAMPO[c]}</span>`).join("") +
      (semEl.size ? `<span><span class="sw" style="background:var(--vazio)"></span>vago (regra 2023)</span>` : "");
    else if (S.camada === "lula") leg.innerHTML = rampa(d3.range(9).map(i => div(i / 8)), "Flávio 65%", "Lula 65%");
    else if (S.camada === "pop") leg.innerHTML = rampa(d3.range(9).map(i => div(i / 8)), "−25%", "+25% da média");
    else if (S.camada === "aptos") leg.innerHTML = rampa(d3.range(9).map(i => div(i / 8)), "−10%", "+10% da média");
    else leg.innerHTML = rampa(seq, "o desenho não muda o vencedor", "muda em metade dos mapas");
    $("#n-mapa").textContent = `${UF_NOME[uf]}: ${k} distritos de ${k > 1 ? "≈" + num(mAp) : num(mAp)} eleitores. ` +
      `Cidades grandes foram quebradas em células em volta dos locais de votação. Role para dar zoom; passe o mouse num distrito e clique para ver os candidatos dele.`;

    desenhaDiferencas(uf, k, res);
    desenhaTabelaDist(uf, r, dm, mAp, regs);
  }

  function desenhaDiferencas(uf, k, res) {
    // distritos ganhos por agremiacao em cada um dos 50 mapas
    const nAgr = S.base.agrs.length;
    const cont = res.map(r => { const c = new Array(nAgr).fill(0); r.vencedores.forEach(v => { if (v.agr >= 0) c[v.agr]++; }); return c; });
    const agrs = d3.range(nAgr).filter(i => d3.max(cont, c => c[i]) > 0).sort((x, y) => d3.sum(cont, c => c[y]) - d3.sum(cont, c => c[x]));
    const W = 420, lh = 34, H = agrs.length * lh + 30, x0 = 110;
    const x = d3.scaleLinear().domain([0, k]).range([x0, W - 14]);
    const svg = d3.select("#dif").html("").append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("role", "img")
      .attr("aria-label", "Distritos ganhos por agremiação em cada mapa");
    svg.append("g").attr("transform", `translate(0,${H - 22})`).call(d3.axisBottom(x).ticks(Math.min(k, 8)).tickFormat(d3.format("d")))
      .call(s => s.select(".domain").attr("stroke", "var(--axis)")).call(s => s.selectAll(".tick line").attr("stroke", "var(--axis)"));
    agrs.forEach((ai, row) => {
      const y = 14 + row * lh;
      const vals = cont.map(c => c[ai]);
      const campo = S.campoDe[ai];
      svg.append("text").attr("class", "rot-agr").attr("x", 0).attr("y", y + 4).text(siglaAgr(ai));
      const contagem = d3.rollup(vals, v => v.length, v => v);
      for (const [v, n] of contagem) {
        svg.append("rect").attr("x", x(v) - 3).attr("width", 6).attr("y", y - n * 0.45).attr("height", Math.max(2, n * 0.9))
          .attr("rx", 2).attr("fill", corCampo(campo)).attr("opacity", 0.9)
          .on("mousemove", ev => mostraDica(ev, `<b>${siglaAgr(ai)}</b>: ${v} distrito${v === 1 ? "" : "s"} em ${n} dos 50 mapas`))
          .on("mouseleave", escondeDica);
      }
      const atual = vals[S.mapa];
      svg.append("line").attr("x1", x(atual)).attr("x2", x(atual)).attr("y1", y - 13).attr("y2", y + 13)
        .attr("stroke", "var(--text-primary)").attr("stroke-width", 2);
      svg.append("text").attr("x", W).attr("y", y + 4).attr("text-anchor", "end").text(`${d3.min(vals)}–${d3.max(vals)}`);
    });
    $("#n-dif").innerHTML = `Cada barrinha é um número de distritos ganhos; a altura é em quantos mapas isso acontece. ` +
      `O traço preto é o mapa ${S.mapa + 1}. À direita, o mínimo e o máximo entre os 50 desenhos.`;
  }

  // ------------------------------------------------------------------ candidatos de um distrito
  // linhas clicaveis: abrem a disputa do distrito, candidato por candidato, com a origem dos votos
  const abertos = { mapas: { chave: null, set: new Set() }, res: { chave: null, set: new Set() } };
  function abertosDe(qual, chave) {
    const a = abertos[qual];
    if (a.chave !== chave) { a.chave = chave; a.set = new Set(); }
    return a.set;
  }
  const sinal = (x) => Math.round(x) === 0 ? "0" : (x > 0 ? "+" : "−") + num(Math.abs(x));

  function htmlCandidatos(uf, r, j) {
    const cs = S.base.uf[uf].cands, d = r.dist[j], v = r.vencedores[j];
    const ordem = [...d.V.keys()].sort((a, b) => d.V[b] - d.V[a]);
    const linhas = ordem.map((i, pos) => {
      let ci = d.cand[i];
      if (ci < 0 && i === d.venc && v.cand >= 0) ci = v.cand;     // vencedor sem base local: o "generico"
      const c = ci >= 0 ? cs[ci] : null;
      const nome = d.agr[i] < 0 ? "<i>outras agremiações</i>"
        : c ? `${esc(c[1])} <span class="faixa-txt">${sigla(c[2])}${S.base.agrs[d.agr[i]].partidos.length > 1 ? " · " + siglaAgr(d.agr[i]) : ""}</span>`
        : `<i>${siglaAgr(d.agr[i])}</i> <span class="faixa-txt">sem candidato com voto aqui</span>`;
      const real = c ? (c[5] ? "eleito" : "não eleito") : "";
      const ali = c && c[4] ? pct(d.P[i] / c[4], 0) : "";
      return `<tr${i === d.venc ? ' class="venc"' : ""}><td>${pos + 1}</td><td>${nome}</td>` +
        `<td class="n">${num(d.P[i])}</td><td class="n">${num(d.L[i])}</td><td class="n">${num(d.H[i])}</td>` +
        `<td class="n">${sinal(d.R[i])}</td><td class="n">${sinal(d.U[i])}</td>` +
        `<td class="n"><b>${num(d.V[i])}</b></td><td class="n">${pct(d.V[i] / d.tot)}</td>` +
        `<td class="n">${c ? num(c[4]) : ""}</td><td class="n">${ali}</td><td>${real}</td></tr>`;
    }).join("");
    return `<table class="tabela sub"><thead><tr><th></th><th>Candidato</th><th class="n">Voto próprio aqui</th><th class="n">Legenda</th>
      <th class="n">Herdado de colegas</th><th class="n">De outros partidos</th><th class="n">Voto útil e polarização</th>
      <th class="n">Simulado</th><th class="n">%</th><th class="n">Total real no estado</th><th class="n">Aqui / total</th><th>Em 2026</th></tr></thead>
      <tbody>${linhas}</tbody></table>
      <p class="nota">Voto próprio, legenda e total real são votos de verdade de 2026. "Herdado de colegas" é o que ele leva dos colegas de partido
      que não concorrem aqui (α = ${String(S.p.alfa).replace(".", ",")}, γ = ${String(S.p.gama).replace(".", ",")}); "De outros partidos" é o que
      chega do voto que os outros não herdaram; a última etapa é o voto útil no campo (β) e a polarização (π).
      "Aqui / total": quanto da votação real do candidato no estado veio deste distrito.</p>`;
  }

  // tr: linha do distrito; ncol: colunas da tabela; set: distritos abertos
  function ligaDetalhe(tb, tr, ncol, set, j, html) {
    const det = tb.append("tr").attr("class", "detalhe");
    const td = det.append("td").attr("colspan", ncol);
    const seta = tr.select("td");
    const mostra = () => {
      const on = set.has(j);
      det.property("hidden", !on);
      seta.text(`${on ? "▾" : "▸"} ${j + 1}`);
      tr.attr("aria-expanded", String(on));
      if (on && !td.html()) td.html(html());
    };
    const alterna = () => { if (set.has(j)) set.delete(j); else set.add(j); mostra(); };
    tr.classed("clicavel", true).attr("tabindex", 0).on("click", alterna)
      .on("keydown", ev => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); alterna(); } });
    mostra();
    return det;
  }

  let ultTabela = null, abrirPendente;
  function abreDistrito(j) {
    if (!ultTabela) return;
    abertosDe("mapas", ultTabela.chave).add(j);
    desenhaTabelaDist(...ultTabela.args);
    const tr = document.querySelector(`#t-dist tbody tr[data-j="${j}"]`);
    if (tr) tr.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function desenhaTabelaDist(uf, r, dm, mAp, regs) {
    const cs = S.base.uf[uf].cands;
    const chave = JSON.stringify([uf, S.p.rateio, S.mapa]);
    ultTabela = { chave, args: [uf, r, dm, mAp, regs] };
    const set = abertosDe("mapas", chave);
    if (abrirPendente >= 1) { set.add(abrirPendente - 1); abrirPendente = undefined; }
    $("#h-tab-dist").textContent = `Distritos do mapa ${S.mapa + 1} — ${UF_NOME[uf]}`;
    const tb = d3.select("#t-dist tbody").html("");
    const sem = new Set(r.semEleito);
    r.vencedores.forEach((v, j) => {
      const c = v.cand >= 0 ? cs[v.cand] : null;
      const l = dm.lula[j], f = dm.flavio[j];
      const tr = tb.append("tr").attr("data-j", j);
      tr.append("td").attr("class", "seta").text(j + 1);
      tr.append("td").attr("class", "n").text(num(dm.aptos[j]));
      const dv = dm.aptos[j] / mAp - 1;
      tr.append("td").attr("class", "n").text((dv >= 0 ? "+" : "−") + pct(Math.abs(dv)));
      tr.append("td").attr("class", "n").text(num(dm.pop[j]));
      tr.append("td").attr("class", "n").text(pct(l / (l + f)));
      tr.append("td").html(c ? `${c[1]} <span class="faixa-txt">${sigla(c[2])}${sem.has(j) ? " · vago" : ""}</span>` : siglaAgr(v.agr));
      tr.append("td").attr("class", "n").text(pct(v.pct));
      tr.append("td").attr("class", "n").text(pct(v.margem));
      tr.append("td").attr("class", "regiao").html(textoRegiao(regs[j], false));
      ligaDetalhe(tb, tr, 9, set, j, () => htmlCandidatos(uf, r, j));
    });
  }

  // ================================================================== METODO
  function desenhaMetodo() {
    const c = S.cal, v = (x) => String(x).replace(".", ",");
    const ks = Object.values(S.base.ks);
    const kAtual = d3.sum(ks, x => x.atual), kSem = d3.sum(ks, x => x.sem_teto), kPuro = d3.sum(ks, x => x.puro);
    const faixas = c.por_faixa.map(f => `<tr><td>${num(f.de)} a ${num(f.ate)}</td><td class="n">${num(f.cidades)}</td>` +
      `<td class="n">${v(f.candidatos)}</td><td class="n">${pct(f.top2, 1)}</td></tr>`).join("");
    const curva = c.curva.filter((x, i) => i % 2 === 0 || x.beta === c.beta_padrao)
      .map(x => `<tr${x.beta === c.beta_padrao ? ' style="font-weight:600"' : ""}><td class="n">${v(x.beta)}</td><td class="n">${v(x.pi)}</td><td class="n">${v(x.erro_campo.toFixed(3))}</td></tr>`).join("");
    $("#metodo").innerHTML = `
<h2>O que foi simulado</h2>
<p>Votos de verdade, regras de mentira. A eleição de deputado federal de 4/10/2026 é recontada como se o eleitor
tivesse votado num sistema distrital misto. Cada estado continua elegendo a sua bancada: metade das cadeiras,
arredondada para baixo, sai de distritos de um eleito só (${kAtual} distritos no rateio atual, ${kSem} sem teto, ${kPuro} no proporcional puro),
e o resto sai de listas estaduais.</p>
<ul>
<li><b>Paralelo 50/50</b>: distritos e listas são contas separadas. A lista reparte as suas cadeiras pelo voto total de cada agremiação no estado.</li>
<li><b>Compensatório (alemão)</b>: o voto de lista define quantas cadeiras cada agremiação tem no estado (é o resultado proporcional de verdade),
e a lista só completa o que os distritos não deram. Na <b>regra alemã de 2023</b>, se um partido ganha mais distritos do que a sua cota,
os distritos que ele venceu com o menor percentual ficam sem eleito, e a Câmara fica em 513. Na <b>regra antiga</b>, o partido fica com
as cadeiras excedentes e os outros ganham cadeiras de nivelamento até a proporção bater, e a Câmara cresce.</li>
<li><b>Só lista fechada</b>: sem distritos. Cada agremiação apresenta uma lista ordenada e o eleitor vota só no partido. A conta de cadeiras é a
mesma de hoje (quociente eleitoral, quociente partidário, 80% do QE nas sobras), menos as duas cláusulas que dependem de voto nominal
(10% e 20% do QE para o candidato), que deixam de existir. A ordem da lista é a votação nominal de 2026, então os nomes mudam pouco;
o que muda é o número de cadeiras dos partidos que dependiam de um puxador.</li>
</ul>
<h2>Os quatro passos</h2>
<p><b>1. Voto de lista.</b> É o total da agremiação no estado (votos nominais + legenda), exatamente a conta que define o quociente
partidário hoje. Federações (PT/PCdoB/PV, PSOL/Rede, PSDB/Cidadania, União/PP, PRD/Solidariedade) disputam como uma só,
como em 2026; o placar é aberto por partido pelo candidato eleito.</p>
<p><b>2. Distritos.</b> Distritos contíguos, com eleitorado a ±10% da média do estado, sorteados pelo algoritmo ReCom
(cadeia de Markov de árvores geradoras) a partir de um grafo de municípios. Município maior que meio distrito é quebrado em células
em volta dos seus locais de votação; os bairros listados em cada distrito são os do cadastro desses locais no TSE.
Cinquenta mapas por estado e por número de distritos; o resultado nacional é a mediana dos 50, e a faixa vai do 10º ao 90º percentil.</p>
<p><b>3. Quem concorre onde.</b> Cada agremiação tem um candidato por distrito, tirado dos seus candidatos reais de 2026 por
emparelhamento guloso: os pares (candidato, distrito) são ordenados pelos votos do candidato naquele distrito, e cada candidato fica
com um distrito só. Onde a agremiação não tem ninguém com base local, entra o mais votado dela no estado que ainda está livre.
Há dupla candidatura: quem perde o distrito continua na lista, na ordem de votação nominal.</p>
<p><b>4. Votos no distrito</b>, em três etapas.</p>
<ul>
<li><b>Herança dos colegas (α e γ).</b> O candidato fica com os votos dele ali e com a legenda. Dos votos que cada colega de agremiação que
não concorre naquele distrito teve lá, ele herda α × min(1, votos dele ÷ votos do colega)<sup>γ</sup>. Com γ = 0, todo colega passa a mesma
fração α. Com γ &gt; 0, o eleitor de um puxador segue menos um candidato muito mais fraco que ele: se o candidato do distrito teve um quarto dos
votos do puxador ali, com γ = 0,5 ele herda metade de α. O que não é herdado vai para as outras agremiações, na proporção do voto delas no distrito.</li>
<li><b>Voto útil no campo (β).</b> Quem ficou do 3º lugar para baixo e não lidera o próprio campo (esquerda, centro, direita) perde β dos votos
para o mais bem colocado do campo.</li>
<li><b>Polarização (π).</b> Depois disso, todo mundo do 3º lugar para baixo, inclusive o líder de um campo que ficou para trás, perde π do que
sobrou para um dos dois primeiros: o de campo mais próximo na linha esquerda–centro–direita. O eleitor de esquerda cujo candidato ficou em 3º
vota no do centro para barrar a direita. Se os dois primeiros estão à mesma distância (o centro diante de esquerda × direita), o voto se
divide na proporção deles.</li>
</ul>
<p>Ganha quem tiver mais votos.</p>
<h2>A calibração com as prefeituras</h2>
<p>Prefeito de cidade com menos de 200 mil eleitores é eleito em turno único, por maioria simples, como seria o deputado distrital.
A concentração nos dois primeiros cai com o tamanho da cidade e com o número de candidatos (prefeito 2024):</p>
<table class="tabela" style="max-width:520px"><thead><tr><th>Eleitores</th><th class="n">Cidades</th><th class="n">Candidatos (média)</th>
<th class="n">Dois primeiros</th></tr></thead><tbody>${faixas}</tbody></table>
<p>Um distrito teria uns 600 mil eleitores, mais que qualquer cidade de turno único. Por isso a calibração usa as ${num(c.amostra.cidades)}
cidades de ${num(c.amostra.de)} a ${num(c.amostra.ate)} eleitores, onde os dois primeiros ficam com <b>${pct(c.top2_observado, 0)}</b>.
O exercício: cada partido vira um "candidato" com o seu voto para vereador (sem coligação, como no simulador) e β e π precisam levar essa
dispersão, em que os dois primeiros têm só ${pct(c.top2_sem_ajuste, 0)}, até a concentração real.</p>
<p>A fatia dos dois primeiros sozinha não separa β de π: há uma curva de pares que a reproduzem (tabela). O desempate vem da votação por campo.
β não muda quanto cada campo tem (só mexe dentro dele), e π muda. Entre os pares da curva, fica o que melhor acerta a votação de prefeito
por campo: <b>β = ${v(c.beta_padrao)} e π = ${v(c.pi_padrao)}</b>. A curva é rasa (intervalo de 90% no bootstrap por cidade: β de
${v(c.ic90_beta[0])} a ${v(c.ic90_beta[1])}, π de ${v(c.ic90_pi[0])} a ${v(c.ic90_pi[1])}), mas o placar quase não muda ao longo dela:
o que pesa é a concentração total, e essa é bem medida.</p>
<table class="tabela" style="max-width:360px"><thead><tr><th class="n">β</th><th class="n">π que dá ${pct(c.top2_observado, 0)}</th>
<th class="n">Erro por campo</th></tr></thead><tbody>${curva}</tbody></table>
<p>Ressalva: prefeitura é cargo executivo, com coligação montada antes, e pode concentrar mais que uma eleição de deputado. Em países com distrito de um eleito só e vários partidos, como o Reino Unido,
a concentração nos dois primeiros costuma ser menor. Os seletores permitem testar o simulador com menos concentração.</p>
<h2>As premissas que não são medidas</h2>
<p><b>α = 0,7</b> e <b>γ = ${v(GAMA_PADRAO)}</b> são escolhas: não existe dado brasileiro de voto em dois níveis para calibrá-las.
A tabela de campos também é uma premissa e pode ser editada abaixo.</p>
<p><b>O voto é o de 2026, dado sob o sistema atual.</b> Num distrital de verdade, partidos fariam alianças, retirariam candidatos e
fariam campanha de outro jeito, e o eleitor também mudaria. A simulação mostra o que <i>estes</i> votos dariam sob outras regras,
não uma previsão de como seria uma eleição distrital.</p>
<h2>Como saber se a conta está certa</h2>
<ul>
<li>A regra brasileira (QE com arredondamento, cláusula de 10% para o quociente partidário, 80%/20% nas sobras e terceira fase aberta a todos,
como decidiu o STF), aplicada com 100% das cadeiras, reproduz exatamente os 513 eleitos reais de 2026 nos 27 estados. Votos "anulados sub judice"
não contam para ninguém, como no TSE.</li>
<li>Todo distrito de todo mapa é contíguo e está dentro de ±10% do eleitorado médio, e nenhum local de votação se perde.</li>
<li>Com o compensatório e a regra de 2023, o total de cada agremiação é igual ao resultado proporcional verdadeiro em todos os mapas.</li>
</ul>
<h2>Cadeiras por estado</h2>
<p>O rateio atual é o da tabela vigente (piso 8, teto 70). As duas alternativas repartem as 513 cadeiras pela população do Censo 2022,
pelo método dos maiores restos: sem teto e com piso 8 (SP iria para ${S.base.rateios.sem_teto.SP}) ou proporcional puro, com piso 1
(SP ${S.base.rateios.puro.SP}; Acre, Amapá e Roraima ficariam com ${S.base.rateios.puro.AC}).</p>`;
    const tb = d3.select("#t-campos tbody").html("");
    S.base.agrs.forEach((a, i) => {
      if (!Object.values(S.base.uf).some(u => u.votos_agr[i])) return;
      const tr = tb.append("tr");
      tr.append("td").text(NOME[a.sigla] || a.sigla);
      const sel = tr.append("td").append("select").on("change", e => { S.campoDe[i] = e.target.value; simula(); escreveHash(); });
      CAMPOS.forEach(c => sel.append("option").attr("value", c).property("selected", S.campoDe[i] === c).text(ROT_CAMPO[c]));
    });
  }

  // ------------------------------------------------------------------ inicio
  carrega().then(() => {
    sincronizaFiltros();
    ligaFiltros();
    simula();
    trocaAba(S.aba);
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", desenha);
  });
})();

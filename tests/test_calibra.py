"""O modelo de voto util/polarizacao da calibracao (Python) e o do simulador (JS) sao o mesmo."""
import json
import pathlib
import shutil
import subprocess

import numpy as np
import pytest

from pipeline.calibra import POS, modelo

RAIZ = pathlib.Path(__file__).resolve().parents[1]
CAMPOS = list(POS)


@pytest.mark.skipif(shutil.which("node") is None, reason="sem node")
def test_beta_pi_iguais_em_python_e_js():
    rng = np.random.default_rng(7)
    casos = []
    for _ in range(300):
        n = int(rng.integers(2, 12))
        s = rng.gamma(0.6, 1.0, n) * 1000
        pc = rng.integers(-1, 3, n)
        beta, pi = float(rng.choice([0, .3, .7, 1])), float(rng.choice([0, .2, .4, .9]))
        esp = bool(rng.integers(0, 2))
        x = np.where((rng.random(n) < 0.1) | (pc < 0), np.nan, rng.uniform(0, 10, n))   # "outros" (pc -1) nao tem posicao
        lam = float(rng.choice([0.5, 1.0, 3.0]))
        casos.append({"s": s.tolist(), "pc": pc.tolist(), "beta": beta, "pi": pi, "esp": esp, "lam": lam,
                      "x": [None if np.isnan(v) else float(v) for v in x],
                      "py": modelo(s, pc, beta, pi, x if esp else None, lam).tolist()})
    js = """
const A = require(%s);
const casos = JSON.parse(require("fs").readFileSync(0, "utf8"));
const campos = %s;
const out = casos.map(c => {
  // uma agremiacao por candidato; campo -1 = agremiacao "outros" (sem campo)
  const flat = [], campoDe = [];
  c.s.forEach((v, i) => { flat.push(c.pc[i] < 0 ? -1 : i, v, 0, -1, 0); campoDe.push(c.pc[i] < 0 ? null : campos[c.pc[i]]); });
  return A.distrito(flat, { alfa: 1, gama: 0, beta: c.beta, pi: c.pi, campoDe, gamas: [],
    afinidade: c.esp ? "espectro" : "campos", pos: c.x, lambda: c.lam }).V;
});
process.stdout.write(JSON.stringify(out));
""" % (json.dumps(str(RAIZ / "docs" / "js" / "aloca.js")), json.dumps(CAMPOS))
    r = subprocess.run(["node", "-e", js], input=json.dumps(casos), capture_output=True, text=True, check=True)
    for c, v in zip(casos, json.loads(r.stdout)):
        assert np.allclose(c["py"], v, rtol=1e-9, atol=1e-6), c

# Distrital misto 2026

E se a Câmara de 2026 tivesse sido eleita pelo sistema distrital misto? Este projeto reconta os votos
reais para deputado federal de 4/10/2026 sob outras regras: paralelo 50/50 ou compensatório (alemão),
três rateios de cadeiras entre os estados, lista pela regra brasileira ou por D'Hondt, e dois parâmetros
de comportamento (α, fidelidade ao partido; γ, peso do candidato; β, voto útil no campo; π, polarização).
Tem também o cenário só de lista fechada, sem distritos.

Página: https://agamemnon140.github.io/distrital-misto-2026/ (aba **Método** explica tudo).

## Pipeline

Python: o venv de `Documents\eleicoes-2026\.venv` (3.13, com gerrychain, geopandas, topojson, scipy, pytest);
nos comandos abaixo, `py` = esse interpretador.

Dados brutos ficam fora do repo, em `ELEICOES_DADOS` (padrão `C:\Users\Henrique\Documents\eleicoes-dados-2t`):
`votacao_secao_2026_{UF,BR}.zip`, `detalhe_votacao_secao_2026.zip`, `consulta_cand_2026_pos.zip`,
`votacao_candidato_munzona_2026.zip` e `votacao_partido_munzona_2024.zip` (CDN do TSE). Geometria, locais
de votação e tabela de partidos vêm dos repos vizinhos `apuracao-2t-2026` e `eleicoes-2026`.

```
py -m pipeline.insumos       # votos por local de votação (deputado federal, 2º turno presidencial)
py -m pipeline.candidatos    # candidatos, destino oficial do voto, totais
py -m pipeline.valida        # regra brasileira com 100% das cadeiras = 513 eleitos reais (27/27)
py -m pipeline.rateio        # 3 rateios das 513 cadeiras (Censo 2022)
py -m pipeline.tijolos       # municípios + células de Voronoi -> grafo de adjacência
py -m pipeline.mapas         # 50 mapas por UF e nº de distritos (ReCom, ±10% de eleitorado)
py -m pipeline.matrizes      # votos por distrito + emparelhamento candidato x distrito
py -m pipeline.calibra       # β e π com prefeito 2024 em turno único (60-170 mil eleitores)
py -m pipeline.exporta       # docs/dados/*.json
```

Testes: `python -m pytest tests` (mapas contíguos, ±10%, eleitorado conservado) e
`node tests/paridade.cjs` (regra em JS = eleitos reais; Casa de 513; compensatório = proporcional).
Placar no terminal: `node tests/manchete.cjs [rateio] [modelo] [regra] [alfa] [beta] [excedentes] [gama] [pi]`.

Servir local: `py -m http.server -d docs 8000`.

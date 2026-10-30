"""Caminhos. Dados pesados ficam fora do repo (ELEICOES_DADOS); o repo apuracao-2t-2026 e
fonte de geometria, locais de votacao e tabela de partidos."""
from __future__ import annotations

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DADOS = Path(os.environ.get("ELEICOES_DADOS", r"C:\Users\Henrique\Documents\eleicoes-dados-2t"))
BRUTO_TSE = DADOS / "raw" / "dadosabertos"
TRAB = DADOS / "distrital"                     # intermediarios desta simulacao
TRAB.mkdir(parents=True, exist_ok=True)
APURACAO = Path(os.environ.get("APURACAO_REPO", r"C:\Users\Henrique\Documents\apuracao-2t-2026"))
ELEICOES = Path(os.environ.get("ELEICOES_REPO", r"C:\Users\Henrique\Documents\eleicoes-2026"))
SAIDA_WEB = RAIZ / "docs" / "dados"

UFS = ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS",
       "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC",
       "SE", "SP", "TO"]

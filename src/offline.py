"""Última previsão baixada, guardada para o app funcionar sem internet.

No celular/navegador (stlite) a pasta /offline fica no armazenamento do navegador
(IndexedDB) e sobrevive ao fechar o app — ver `idbfsMountpoints` no index.html.
Rodando com o Streamlit normal, fica em .cache/offline.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from src.config import ROOT

if sys.platform == "emscripten" and Path("/offline").is_dir():
    PASTA = Path("/offline")
else:
    PASTA = ROOT / ".cache" / "offline"

ARQ_PREVISAO = "previsao.parquet"


def salvar_previsao(fc: pd.DataFrame, baixado_em: pd.Timestamp) -> None:
    """Guarda a previsão horária por célula (substitui as células que vieram de novo)."""
    try:
        PASTA.mkdir(parents=True, exist_ok=True)
        arq = PASTA / ARQ_PREVISAO
        novo = fc.assign(baixado_em=baixado_em)
        if arq.exists():
            antigo = pd.read_parquet(arq)
            novo = pd.concat([antigo[~antigo["celula"].isin(novo["celula"])], novo], ignore_index=True)
        novo.to_parquet(arq, index=False)
        _gravar_no_navegador()
    except Exception:  # noqa: BLE001 — guardar a cópia nunca pode derrubar o app
        pass


def _gravar_no_navegador() -> None:
    """No stlite, copia a pasta para o IndexedDB na hora.

    O stlite deveria fazer isso sozinho ao fim de cada execução, mas na versão em uso o
    gatilho não dispara com o Streamlit atual — sem isto, a previsão some ao fechar o app.
    """
    if sys.platform != "emscripten":
        return
    import pyodide_js  # noqa: PLC0415 — só existe no navegador
    from pyodide.ffi import create_once_callable  # noqa: PLC0415

    pyodide_js.FS.syncfs(False, create_once_callable(lambda erro=None: None))


def carregar_previsao(ids) -> tuple[pd.DataFrame, pd.Timestamp] | None:
    """Previsão guardada das células pedidas e quando foi baixada (a mais antiga), ou None."""
    arq = PASTA / ARQ_PREVISAO
    if not arq.exists():
        return None
    try:
        df = pd.read_parquet(arq)
    except Exception:  # noqa: BLE001
        return None
    df = df[df["celula"].isin(list(ids))]
    if df.empty:
        return None
    return df.drop(columns="baixado_em"), df["baixado_em"].min()

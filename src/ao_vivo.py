"""Alagamentos registrados hoje pelo CGE (ao vivo), com localização no mapa.

Fontes, em ordem:
1. a página do CGE, direto — funciona no app Android (o CacheWeb.java libera o acesso) e
   rodando o Streamlit no computador;
2. uma cópia em JSON atualizada a cada ~15 min por um job do GitHub
   (.github/workflows/cge_ao_vivo.yml) — necessária no navegador, porque o site do CGE
   não permite ser lido por páginas de outros endereços (CORS).
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import requests

from src import cge
from src.config import TZ, USER_AGENT
from src.nomes import normalizar

URL_ESPELHO = "https://raw.githubusercontent.com/augustonvsilva/alagamento-sp/ao-vivo/ao_vivo.json"
COLUNAS = ["data", "zona", "bairro", "inicio", "fim", "local", "sentido", "referencia",
           "intransitavel", "ativo"]


def agora() -> pd.Timestamp:
    return pd.Timestamp.now(tz=TZ).tz_localize(None)


def do_cge(timeout: int = 15) -> dict:
    """Lê a página de hoje direto do CGE."""
    hoje = agora().date()
    r = requests.get(cge.URL, params={"dataBusca": hoje.strftime("%d/%m/%Y"), "enviaBusca": "Buscar"},
                     headers={"User-Agent": USER_AGENT}, timeout=timeout)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return {"atualizado_em": agora().isoformat(timespec="minutes"), "fonte": "CGE",
            "registros": cge.parse_dia(r.text, hoje)}


def do_espelho(timeout: int = 15) -> dict:
    r = requests.get(URL_ESPELHO, timeout=timeout)
    r.raise_for_status()
    d = r.json()
    d["fonte"] = "cópia do CGE (atualizada a cada ~15 min)"
    return d


def buscar() -> dict:
    """{'atualizado_em', 'fonte', 'registros'} — tenta o CGE e, se não der, a cópia."""
    erros = []
    for fonte in (do_cge, do_espelho):
        try:
            d = fonte()
            # A cópia pode ser de ontem (antes da 1ª atualização do dia): só vale a de hoje
            if str(d["atualizado_em"])[:10] == agora().date().isoformat():
                return d
            erros.append(f"{fonte.__name__}: dados de {d['atualizado_em']}")
        except Exception as e:  # noqa: BLE001 — sem internet, CORS no navegador, site fora do ar...
            erros.append(f"{fonte.__name__}: {e.__class__.__name__}")
    raise ConnectionError("; ".join(erros))


def localizar(registros: list[dict], eventos: pd.DataFrame, pontos: pd.DataFrame) -> pd.DataFrame:
    """Coordenadas de cada alagamento de hoje, pelo mesmo endereço no histórico geocodificado.

    Ordem: mesma rua no mesmo bairro -> mesma rua -> centro do bairro. Também indica o ponto
    monitorado correspondente (coluna `ponto`), para comparar previsto x ocorrido.
    """
    df = pd.DataFrame(registros, columns=COLUNAS)
    if df.empty:
        return df.assign(lat=[], lon=[], precisao=[], ponto=[])
    df["local_n"] = df["local"].fillna("").map(normalizar)
    df["bairro_n"] = df["bairro"].fillna("").map(cge.normalizar_bairro)

    ev = eventos.dropna(subset=["lat", "lon"])
    por_rua_bairro = ev.groupby(["local_n", "bairro_n"])[["lat", "lon"]].median()
    rua = ev[ev["precisao"] == "logradouro"].groupby("local_n")[["lat", "lon"]].median()
    bairro = ev.groupby("bairro_n")[["lat", "lon"]].median()

    def achar(r):
        k = (r["local_n"], r["bairro_n"])
        if k in por_rua_bairro.index:
            return (*por_rua_bairro.loc[k], "endereço")
        if r["local_n"] in rua.index:
            return (*rua.loc[r["local_n"]], "endereço")
        if r["bairro_n"] in bairro.index:
            return (*bairro.loc[r["bairro_n"]], "bairro")
        return (float("nan"), float("nan"), "desconhecida")

    df[["lat", "lon", "precisao"]] = pd.DataFrame([achar(r) for _, r in df.iterrows()], index=df.index)
    chave = pontos.reset_index(names="ponto").set_index(["local_n", "bairro_n"])["ponto"]
    chave = chave[~chave.index.duplicated()]
    df["ponto"] = pd.array([chave.get((a, b)) for a, b in zip(df["local_n"], df["bairro_n"])], dtype="Int64")
    return df


def resumo_texto(df: pd.DataFrame) -> str:
    ativos = int(df["ativo"].sum()) if len(df) else 0
    if not len(df):
        return "Nenhum alagamento registrado hoje pelo CGE até agora."
    return (f"{len(df)} alagamento(s) registrado(s) hoje pelo CGE"
            + (f", **{ativos} ainda ativo(s)**" if ativos else ", nenhum ativo agora") + ".")


def hora_atualizacao(d: dict) -> str:
    try:
        return datetime.fromisoformat(str(d["atualizado_em"])).strftime("%Hh%M")
    except ValueError:
        return str(d.get("atualizado_em", ""))

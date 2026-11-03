"""Camada de dados do app: carrega artefatos, consulta APIs (com cache) e roda o modelo."""
from __future__ import annotations

import json
from dataclasses import dataclass

import joblib
import numpy as np
import pandas as pd
import streamlit as st

from src import features, geo, risk, weather
from src.config import MODELS, PROCESSED, TZ
from src.grade import celula_id, id_para_coord

TTL_PREVISAO = 1800  # 30 min — a previsão do Open-Meteo é atualizada de hora em hora


def agora_sp() -> pd.Timestamp:
    return pd.Timestamp.now(tz=TZ).tz_localize(None).floor("h")


# ---------------------------------------------------------------- artefatos
@st.cache_resource
def modelo():
    return joblib.load(MODELS / "modelo.joblib")


@st.cache_data
def metricas() -> dict:
    return json.loads((MODELS / "metricas.json").read_text(encoding="utf-8"))


@st.cache_data
def celulas() -> pd.DataFrame:
    c = pd.read_parquet(PROCESSED / "celulas.parquet")
    c[["lat", "lon"]] = c["celula"].map(id_para_coord).tolist()
    return c


@st.cache_data
def pontos() -> pd.DataFrame:
    return pd.read_parquet(PROCESSED / "pontos.parquet")


@st.cache_data
def eventos() -> pd.DataFrame:
    return pd.read_parquet(PROCESSED / "alagamentos_geo.parquet")


@st.cache_data
def diario() -> pd.DataFrame:
    return pd.read_parquet(PROCESSED / "diario.parquet")


# ---------------------------------------------------------------- APIs externas
@st.cache_data(ttl=TTL_PREVISAO, show_spinner="Consultando a previsão do tempo...")
def _previsao_bruta(ids: tuple[str, ...]) -> pd.DataFrame:
    coords = [id_para_coord(c) for c in ids]
    fc = weather.hourly_forecast([c[0] for c in coords], [c[1] for c in coords])
    fc["celula"] = fc["idx"].map(dict(enumerate(ids)))
    return fc.drop(columns="idx")


@st.cache_data(ttl=600)
def tempo_atual(lat: float, lon: float) -> dict:
    return weather.current_weather(lat, lon)


@st.cache_data(ttl=86400, show_spinner="Localizando endereço...")
def geocode(q: str):
    return geo.geocode(q)


@st.cache_data(ttl=3600, show_spinner="Calculando trajetos...")
def rotas(o: tuple, d: tuple):
    return geo.rotas(o, d)


# ---------------------------------------------------------------- previsão de risco
@dataclass
class Previsao:
    agora: pd.Timestamp
    cel_h: pd.DataFrame      # celula, time, precip, prob, p (prob. de alagamento na célula)
    pts_h: pd.DataFrame      # ponto, time, precip, p (prob. de alagamento no ponto)
    cel: pd.DataFrame        # resumo por célula (próximas 24h)
    pts: pd.DataFrame        # pontos + resumo (próximas 24h)


def _prever_celulas(fc: pd.DataFrame, taxa: pd.Series) -> pd.DataFrame:
    m = modelo()
    X = features.construir(fc[["celula", "time", "precip", "prob"]], taxa)
    X["p"] = features.ajustar_prevalencia(m["modelo"].predict_proba(X[m["features"]])[:, 1],
                                          m.get("delta", 0.0))
    # Sem chuva relevante nas últimas 6h o risco é desprezível (evita ruído do modelo)
    X.loc[X["p6h"] < 0.2, "p"] = X.loc[X["p6h"] < 0.2, "p"].clip(upper=1e-4)
    return X


def previsao(sim: tuple | None = None) -> Previsao:
    """sim = (mm_h, horas) para o modo simulação, ou None."""
    agora = agora_sp()
    cel = celulas()
    fc = _previsao_bruta(tuple(cel["celula"]))
    if sim:
        fc = risk.simular_chuva(fc, agora, *sim)
    cel_h = _prever_celulas(fc, cel.set_index("celula")["taxa"])

    pts = pontos().reset_index(names="ponto")
    pts_h = pts[["ponto", "celula", "participacao"]].merge(
        cel_h[["celula", "time", "precip", "p"]], on="celula")
    pts_h["p"] = pts_h["p"] * pts_h["participacao"]

    r_cel = cel.merge(risk.resumo(cel_h, "celula", agora, escala="regiao"), left_on="celula", right_index=True)
    r_pts = pts.merge(risk.resumo(pts_h, "ponto", agora), left_on="ponto", right_index=True)
    return Previsao(agora, cel_h, pts_h, r_cel, r_pts)


def previsao_local(lat: float, lon: float, sim: tuple | None = None) -> pd.DataFrame:
    """Probabilidade horária de alagamento na célula de um endereço qualquer."""
    cid = celula_id(lat, lon)
    fc = _previsao_bruta((cid,))
    if sim:
        fc = risk.simular_chuva(fc, agora_sp(), *sim)
    taxa = celulas().set_index("celula")["taxa"]
    return _prever_celulas(fc, taxa.reindex([cid]).fillna(0.0))


def historico_proximo(lat: float, lon: float, raio_km: float) -> pd.DataFrame:
    ev = eventos()
    d = geo.haversine_m(lat, lon, ev["lat"].values, ev["lon"].values) / 1000
    return ev[d <= raio_km].assign(dist_km=d[d <= raio_km])


def pontos_no_caminho(path: np.ndarray, pts: pd.DataFrame, buffer_m: float) -> pd.DataFrame:
    d = np.array([geo.dist_ponto_caminho_m(a, b, path) for a, b in zip(pts["lat"], pts["lon"])])
    return pts[d <= buffer_m]

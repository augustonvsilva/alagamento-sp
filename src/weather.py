"""Previsão do tempo via Open-Meteo (gratuita, sem chave)."""
from __future__ import annotations

import pandas as pd
import requests

from src.config import TZ, USER_AGENT

API = "https://api.open-meteo.com/v1/forecast"

WMO = {
    0: "Céu limpo", 1: "Predomínio de sol", 2: "Parcialmente nublado", 3: "Nublado",
    45: "Neblina", 48: "Neblina com geada",
    51: "Garoa fraca", 53: "Garoa", 55: "Garoa forte",
    61: "Chuva fraca", 63: "Chuva moderada", 65: "Chuva forte",
    80: "Pancadas fracas", 81: "Pancadas de chuva", 82: "Pancadas fortes",
    95: "Tempestade", 96: "Tempestade com granizo", 99: "Tempestade forte com granizo",
}


def _get(params: dict, timeout: int = 30):
    r = requests.get(API, params=params, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def hourly_forecast(lats, lons, past_days: int = 3, forecast_days: int = 3) -> pd.DataFrame:
    """Chuva hora a hora para vários pontos (inclui dias passados para as janelas acumuladas).

    Retorna colunas: idx (posição do ponto), time, precip (mm), prob (%),
    umidade (%), vento e rajada (km/h).
    """
    data = _get({
        "latitude": ",".join(f"{x:.4f}" for x in lats),
        "longitude": ",".join(f"{x:.4f}" for x in lons),
        "hourly": "precipitation,precipitation_probability,relative_humidity_2m,wind_speed_10m,wind_gusts_10m",
        "past_days": past_days, "forecast_days": forecast_days, "timezone": TZ,
    })
    if isinstance(data, dict):
        data = [data]
    frames = []
    for i, d in enumerate(data):
        h = d["hourly"]
        frames.append(pd.DataFrame({"idx": i, "time": pd.to_datetime(h["time"]),
                                    "precip": h["precipitation"], "prob": h["precipitation_probability"],
                                    "umidade": h.get("relative_humidity_2m"), "vento": h.get("wind_speed_10m"),
                                    "rajada": h.get("wind_gusts_10m")}))
    df = pd.concat(frames, ignore_index=True)
    df[["precip", "prob"]] = df[["precip", "prob"]].fillna(0).astype(float)
    df[["umidade", "vento", "rajada"]] = df[["umidade", "vento", "rajada"]].astype(float)
    return df


def current_weather(lat: float, lon: float) -> dict:
    c = _get({
        "latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}", "timezone": TZ,
        "current": ("temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,"
                    "wind_speed_10m,wind_direction_10m,wind_gusts_10m"),
    }, timeout=20)["current"]
    c["descricao"] = WMO.get(c.get("weather_code"), "—")
    c["direcao"] = direcao_vento(c.get("wind_direction_10m"))
    return c


PONTOS_CARDEAIS = ["N", "NE", "L", "SE", "S", "SO", "O", "NO"]


def direcao_vento(graus) -> str:
    """Graus (de onde o vento sopra) → ponto cardeal em português."""
    if graus is None:
        return ""
    return PONTOS_CARDEAIS[round(float(graus) / 45) % 8]

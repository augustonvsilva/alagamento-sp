"""Etapa 3b — umidade do ar e vento horários históricos de cada célula da grade.

Mesma fonte da chuva (Historical Forecast API do Open-Meteo). Serve para testar se
umidade e vento ajudam a prever alagamentos além da chuva (ver treinar_modelo).

Saída: data/processed/clima_horario.parquet  (celula, time, umidade, vento, rajada)
Uso:   python -m pipeline.clima_historico
"""
from __future__ import annotations

import argparse
import time
from datetime import date, timedelta

import pandas as pd
import requests

from pipeline import PATHS
from pipeline.chuva_historica import API
from src.config import TZ, USER_AGENT
from src.grade import celula_id, id_para_coord

VARIAVEIS = {"relative_humidity_2m": "umidade", "wind_speed_10m": "vento", "wind_gusts_10m": "rajada"}


def baixar(lat, lon, ini: date, fim: date) -> pd.DataFrame:
    params = {"latitude": lat, "longitude": lon, "start_date": ini.isoformat(), "end_date": fim.isoformat(),
              "hourly": ",".join(VARIAVEIS), "timezone": TZ}
    for t in range(6):
        try:
            r = requests.get(API, params=params, headers={"User-Agent": USER_AGENT}, timeout=120)
            if r.status_code == 429:  # limite da API gratuita: espera e tenta de novo
                time.sleep(120 * (t + 1))
                continue
            r.raise_for_status()
            h = r.json()["hourly"]
            d = pd.DataFrame({"time": pd.to_datetime(h["time"])})
            for api, col in VARIAVEIS.items():
                d[col] = pd.to_numeric(pd.Series(h[api], dtype="object"), errors="coerce").astype(float)
            return d
        except requests.RequestException:
            time.sleep(15 * (t + 1))
    raise RuntimeError(f"falha {lat},{lon} {ini}")


def main(inicio: date, fim: date) -> None:
    ev = pd.read_parquet(PATHS.processed / "alagamentos_geo.parquet")
    celulas = sorted(celula_id(ev["lat"], ev["lon"]).unique())
    print(f"{len(celulas)} células")
    pasta = PATHS.raw / "clima"
    pasta.mkdir(exist_ok=True)
    arquivos = []
    for i, cid in enumerate(celulas):
        lat, lon = id_para_coord(cid)
        ini = inicio
        while ini <= fim:  # um arquivo por (célula, ano): anos completos ficam em cache
            f = min(date(ini.year, 12, 31), fim)
            arq = pasta / f"{cid}_{ini}_{f}.parquet"
            if not arq.exists():
                d = baixar(lat, lon, ini, f)
                d["celula"] = cid
                d.to_parquet(arq, index=False)
                time.sleep(3)
            arquivos.append(arq)
            ini = f + timedelta(days=1)
        print(f"  {i + 1}/{len(celulas)} {cid}", flush=True)
    todas = pd.concat([pd.read_parquet(a) for a in arquivos], ignore_index=True)
    todas.to_parquet(PATHS.processed / "clima_horario.parquet", index=False)
    print(f"OK: {len(todas):,} horas-célula")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--inicio", type=date.fromisoformat, default=date(2019, 1, 1))
    ap.add_argument("--fim", type=date.fromisoformat, default=date.today() - timedelta(days=2))
    a = ap.parse_args()
    main(a.inicio, a.fim)

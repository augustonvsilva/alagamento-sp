"""Etapa 3 — baixa a chuva horária histórica de cada célula da grade.

Usa a Historical Forecast API do Open-Meteo: são as previsões de curto prazo
arquivadas dos mesmos modelos que o app consulta ao vivo. Assim o modelo é
treinado com dados da mesma natureza que vai receber em produção.

Saída: data/processed/chuva_horaria.parquet  (celula, time, precip)
Uso:   python -m pipeline.chuva_historica --inicio 2021-01-01
"""
from __future__ import annotations

import argparse
import time
from datetime import date, timedelta

import pandas as pd
import requests

from pipeline import PATHS
from src.config import TZ, USER_AGENT
from src.grade import celula_id, id_para_coord

API = "https://historical-forecast-api.open-meteo.com/v1/forecast"


def baixar(lat, lon, ini: date, fim: date) -> pd.DataFrame:
    params = {"latitude": lat, "longitude": lon, "start_date": ini.isoformat(),
              "end_date": fim.isoformat(), "hourly": "precipitation", "timezone": TZ}
    for t in range(5):
        try:
            r = requests.get(API, params=params, headers={"User-Agent": USER_AGENT}, timeout=120)
            if r.status_code == 429:
                time.sleep(60 * (t + 1))
                continue
            r.raise_for_status()
            h = r.json()["hourly"]
            return pd.DataFrame({"time": pd.to_datetime(h["time"]), "precip": h["precipitation"]})
        except requests.RequestException:
            time.sleep(10 * (t + 1))
    raise RuntimeError(f"falha {lat},{lon} {ini}")


def main(inicio: date, fim: date) -> None:
    ev = pd.read_parquet(PATHS.processed / "alagamentos_geo.parquet")
    celulas = sorted(celula_id(ev["lat"], ev["lon"]).unique())
    print(f"{len(celulas)} células com histórico de alagamento")
    pasta = PATHS.raw / "chuva"
    pasta.mkdir(exist_ok=True)
    arquivos = []
    for i, cid in enumerate(celulas):
        lat, lon = id_para_coord(cid)
        ini, baixados = inicio, 0
        while ini <= fim:  # um arquivo por (célula, trecho anual): anos completos ficam em cache
            f = min(date(ini.year, 12, 31), fim)
            arq = pasta / f"{cid}_{ini}_{f}.parquet"
            if not arq.exists():
                d = baixar(lat, lon, ini, f)
                d["celula"] = cid
                d.to_parquet(arq, index=False)
                baixados += 1
                time.sleep(3)
            arquivos.append(arq)
            ini = f + timedelta(days=1)
        print(f"  {i + 1}/{len(celulas)} {cid}: {baixados} trecho(s) baixado(s)", flush=True)
    todas = pd.concat([pd.read_parquet(a) for a in arquivos], ignore_index=True)
    todas.to_parquet(PATHS.processed / "chuva_horaria.parquet", index=False)
    print(f"OK: {len(todas):,} horas-célula")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--inicio", type=date.fromisoformat, default=date(2019, 1, 1))
    ap.add_argument("--fim", type=date.fromisoformat, default=date.today() - timedelta(days=2))
    a = ap.parse_args()
    main(a.inicio, a.fim)

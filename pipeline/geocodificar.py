"""Etapa 2 — geocodifica os locais de alagamento do CGE.

Estratégia:
1. Geocodifica o centróide de cada bairro ("Casa Verde, São Paulo").
2. Para cada logradouro (>= MIN_OCORRENCIAS ocorrências), expande abreviações
   ("R" -> "Rua", "AV" -> "Avenida"...) e busca no Nominatim; entre os
   candidatos, escolhe o mais próximo do centróide do bairro (até 4 km).
3. Locais não encontrados ficam com o centróide do bairro/subprefeitura.

Respeita o limite do Nominatim (1 req/s) e guarda cache em data/raw/geocache.json.

Uso:  python -m pipeline.geocodificar
"""
from __future__ import annotations

import json
import time
import unicodedata

import numpy as np
import pandas as pd
import requests

from pipeline import PATHS
from src.config import BBOX, USER_AGENT
from src.geo import haversine_m
from src.nomes import expandir, normalizar

MIN_OCORRENCIAS = 1  # o "bairro" do CGE é a subprefeitura (~31 áreas): fallback grosseiro, vale geocodificar tudo
RAIO_MAX_M = 4000
CACHE = PATHS.raw / "geocache.json"

def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()


class Nominatim:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = USER_AGENT
        self.ultimo = 0.0
        self.cache: dict = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}

    def buscar(self, q: str, limit: int = 8) -> list[tuple[float, float]]:
        if q in self.cache:
            return self.cache[q]
        espera = 1.05 - (time.time() - self.ultimo)
        if espera > 0:
            time.sleep(espera)
        params = {"q": q, "format": "json", "limit": limit, "countrycodes": "br", "bounded": 1,
                  "viewbox": f"{BBOX['lon_min']},{BBOX['lat_max']},{BBOX['lon_max']},{BBOX['lat_min']}"}
        for t in range(3):
            try:
                r = self.s.get("https://nominatim.openstreetmap.org/search", params=params, timeout=30)
                r.raise_for_status()
                res = [(float(x["lat"]), float(x["lon"])) for x in r.json()]
                break
            except requests.RequestException:
                time.sleep(5 * (t + 1))
        else:
            res = []
        self.ultimo = time.time()
        self.cache[q] = res
        if len(self.cache) % 25 == 0:
            self.salvar()
        return res

    def salvar(self):
        CACHE.write_text(json.dumps(self.cache, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    df = pd.read_parquet(PATHS.raw / "cge_alagamentos.parquet")
    df = df.dropna(subset=["local", "bairro"])
    df["bairro_n"] = df["bairro"].map(_norm)
    df["local_n"] = df["local"].map(normalizar)
    geo = Nominatim()

    # 1) centróides de bairro
    bairros = df.groupby("bairro_n")["bairro"].first()
    cent = {}
    for i, (bn, nome) in enumerate(bairros.items()):
        res = geo.buscar(f"{nome}, São Paulo, SP")
        if res:
            cent[bn] = res[0]
        if i % 20 == 0:
            print(f"bairros {i}/{len(bairros)}", flush=True)
    geo.salvar()

    # 2) logradouros recorrentes
    contagem = df.groupby(["local_n", "bairro_n"]).size().rename("n").reset_index()
    alvo = contagem[(contagem["n"] >= MIN_OCORRENCIAS) & contagem["bairro_n"].isin(cent)]
    print(f"{len(alvo)} logradouros recorrentes para geocodificar")
    linhas = []
    for i, r in enumerate(alvo.itertuples()):
        c = cent[r.bairro_n]
        cand = geo.buscar(f"{expandir(r.local_n)}, São Paulo, SP")
        ponto, precisao = None, "bairro"
        if cand:
            arr = np.array(cand)
            d = haversine_m(c[0], c[1], arr[:, 0], arr[:, 1])
            j = int(np.argmin(d))
            if d[j] <= RAIO_MAX_M:
                ponto, precisao = tuple(arr[j]), "logradouro"
        linhas.append({"local_n": r.local_n, "bairro_n": r.bairro_n,
                       "lat": (ponto or c)[0], "lon": (ponto or c)[1], "precisao": precisao})
        if i % 50 == 0:
            print(f"logradouros {i}/{len(alvo)}", flush=True)
    geo.salvar()
    locais = pd.DataFrame(linhas, columns=["local_n", "bairro_n", "lat", "lon", "precisao"])

    # 3) junta e aplica fallback de bairro
    out = df.merge(locais, on=["local_n", "bairro_n"], how="left")
    sem = out["lat"].isna() & out["bairro_n"].isin(cent)
    if sem.any():
        out.loc[sem, "lat"] = out.loc[sem, "bairro_n"].map(lambda b: cent[b][0]).astype(float)
        out.loc[sem, "lon"] = out.loc[sem, "bairro_n"].map(lambda b: cent[b][1]).astype(float)
        out.loc[sem, "precisao"] = "bairro"
    out = out.dropna(subset=["lat"])
    out.to_parquet(PATHS.processed / "alagamentos_geo.parquet", index=False)
    print(out["precisao"].value_counts().to_string())
    print(f"OK: {len(out)} eventos geocodificados ({len(df) - len(out)} descartados)")


if __name__ == "__main__":
    main()

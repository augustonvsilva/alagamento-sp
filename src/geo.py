"""Geocodificação (Nominatim/OSM), rotas (OSRM) e distâncias."""
import numpy as np
import requests

HEADERS = {"User-Agent": "alagamento-sp/0.1 (projeto academico)"}
# Caixa aproximada da Grande SP para priorizar resultados locais
VIEWBOX = "-47.05,-23.35,-46.30,-23.95"


def geocode(endereco: str):
    """Retorna (lat, lon, nome_completo) ou None."""
    params = {
        "q": endereco, "format": "json", "limit": 1,
        "countrycodes": "br", "viewbox": VIEWBOX, "bounded": 1,
    }
    r = requests.get("https://nominatim.openstreetmap.org/search",
                     params=params, headers=HEADERS, timeout=20)
    r.raise_for_status()
    res = r.json()
    if not res:
        return None
    return float(res[0]["lat"]), float(res[0]["lon"]), res[0]["display_name"]


def rotas(origem, destino, alternativas=True):
    """Lista de rotas de carro. Cada rota: dict(dist_km, dur_min, path=[[lat, lon], ...])."""
    (la1, lo1), (la2, lo2) = origem, destino
    url = f"https://router.project-osrm.org/route/v1/driving/{lo1},{la1};{lo2},{la2}"
    params = {"overview": "full", "geometries": "geojson",
              "alternatives": "true" if alternativas else "false"}
    r = requests.get(url, params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    out = []
    for rt in r.json().get("routes", []):
        coords = np.array(rt["geometry"]["coordinates"])[:, ::-1]  # -> [lat, lon]
        out.append({"dist_km": rt["distance"] / 1000, "dur_min": rt["duration"] / 60,
                    "path": coords})
    return out


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6_371_000 * 2 * np.arcsin(np.sqrt(a))


def dist_ponto_caminho_m(lat, lon, path: np.ndarray) -> float:
    """Distância mínima (m) de um ponto aos vértices de um caminho (OSRM 'full' é denso)."""
    return float(haversine_m(lat, lon, path[:, 0], path[:, 1]).min())

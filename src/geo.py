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


def endereco_de(lat: float, lon: float) -> str | None:
    """Geocodificação reversa: coordenadas -> endereço legível (ou None)."""
    params = {"lat": lat, "lon": lon, "format": "json", "zoom": 17}
    r = requests.get("https://nominatim.openstreetmap.org/reverse",
                     params=params, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json().get("display_name")


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


def rota_via(origem, via, destino):
    """Rota de carro passando por um ponto intermediário (usada para desviar de alagamentos)."""
    pts = ";".join(f"{lo},{la}" for la, lo in (origem, via, destino))
    r = requests.get(f"https://router.project-osrm.org/route/v1/driving/{pts}",
                     params={"overview": "full", "geometries": "geojson"}, headers=HEADERS, timeout=30)
    r.raise_for_status()
    rts = r.json().get("routes", [])
    if not rts:
        return None
    rt = rts[0]
    return {"dist_km": rt["distance"] / 1000, "dur_min": rt["duration"] / 60,
            "path": np.array(rt["geometry"]["coordinates"])[:, ::-1]}


def pontos_de_desvio(path: np.ndarray, lat: float, lon: float, dist_m: float = 900):
    """Dois pontos ao lado do caminho (um de cada lado), na altura do ponto a evitar."""
    k = 111_320.0
    cos = np.cos(np.radians(lat))
    xy = np.c_[(path[:, 1] - lon) * k * cos, (path[:, 0] - lat) * k]
    i = int(np.argmin((xy ** 2).sum(1)))
    a, b = xy[max(i - 5, 0)], xy[min(i + 5, len(xy) - 1)]
    d = b - a
    if not np.any(d):
        return []
    n = np.array([-d[1], d[0]]) / np.hypot(*d)  # perpendicular ao trecho
    return [(lat + s * n[1] * dist_m / k, lon + s * n[0] * dist_m / (k * cos)) for s in (1, -1)]


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6_371_000 * 2 * np.arcsin(np.sqrt(a))


def dist_ponto_caminho_m(lat, lon, path: np.ndarray) -> float:
    """Distância mínima (m) de um ponto aos vértices de um caminho (OSRM 'full' é denso)."""
    return float(haversine_m(lat, lon, path[:, 0], path[:, 1]).min())

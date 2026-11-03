"""Grade regular de chuva sobre São Paulo (células de PASSO_GRADE graus)."""
import numpy as np
import pandas as pd

from src.config import PASSO_GRADE


def centro(v):
    """Arredonda coordenada(s) para o centro da célula."""
    return np.round(np.round(np.asarray(v, dtype=float) / PASSO_GRADE) * PASSO_GRADE, 4)


def celula_id(lat, lon):
    la, lo = centro(lat), centro(lon)
    if np.ndim(la) == 0:
        return f"{float(la):.1f}_{float(lo):.1f}"
    return pd.Series([f"{a:.1f}_{b:.1f}" for a, b in zip(la, lo)])


def id_para_coord(cid: str) -> tuple[float, float]:
    a, b = cid.split("_")
    return float(a), float(b)

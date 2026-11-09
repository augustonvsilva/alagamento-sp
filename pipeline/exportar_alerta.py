"""Gera models/alerta.json: tudo que o alerta em segundo plano do app Android precisa.

O Android recalcula o risco sozinho a cada hora (sem abrir o app e sem Python), com o mesmo
modelo: coeficientes da regressão logística, taxa histórica de cada região e os pontos
monitorados. Roda no fim do treino (treinar_modelo) e pode ser chamado à parte.

Uso:  python -m pipeline.exportar_alerta
"""
from __future__ import annotations

import json

import pandas as pd

from pipeline import PATHS
from src.config import LIMIARES_REGIAO, NIVEIS
from src.features import FEATURES


def main() -> None:
    modelo = json.loads((PATHS.model / "modelo.json").read_text(encoding="utf-8"))
    assert modelo["features"] == FEATURES
    cel = pd.read_parquet(PATHS.processed / "celulas.parquet")
    pts = pd.read_parquet(PATHS.processed / "pontos.parquet")
    alerta = {
        "features": modelo["features"], "media": modelo["media"], "escala": modelo["escala"],
        "coef": modelo["coef"], "intercepto": modelo["intercepto"], "delta": modelo.get("delta", 0.0),
        "niveis": [n for _, n, _ in NIVEIS],
        "limiares_ponto": [lim for lim, _, _ in NIVEIS[:-1]],
        "limiares_regiao": LIMIARES_REGIAO[:-1],
        "raio_km": 2.0,
        "celulas": {c: round(float(t), 4) for c, t in zip(cel["celula"], cel["taxa"])},
        "pontos": [[round(float(a), 5), round(float(b), 5), c, round(float(p), 5), n]
                   for a, b, c, p, n in zip(pts["lat"], pts["lon"], pts["celula"], pts["participacao"], pts["nome"])],
    }
    (PATHS.model / "alerta.json").write_text(json.dumps(alerta, ensure_ascii=False), encoding="utf-8")
    print(f"alerta.json: {len(alerta['celulas'])} regiões, {len(alerta['pontos'])} pontos")


if __name__ == "__main__":
    main()

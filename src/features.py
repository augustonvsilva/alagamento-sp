"""Engenharia de features — compartilhada entre treino (pipeline) e app (inferência)."""
import numpy as np
import pandas as pd

JANELAS = {"p1h": 1, "p3h": 3, "p6h": 6, "p24h": 24, "p72h": 72}
FEATURES = ["log_p1h", "log_p3h", "log_p6h", "log_p24h", "log_p72h",
            "hora_sin", "hora_cos", "log_taxa_celula"]
NOMES = {
    "log_p1h": "Chuva na hora", "log_p3h": "Chuva em 3h", "log_p6h": "Chuva em 6h",
    "log_p24h": "Chuva em 24h", "log_p72h": "Chuva em 72h",
    "hora_sin": "Hora do dia (sen)", "hora_cos": "Hora do dia (cos)",
    "log_taxa_celula": "Histórico de alagamentos da região",
}


def ajustar_prevalencia(p, delta: float):
    """Desloca as probabilidades na escala logit (correção de mudança de prevalência)."""
    p = np.clip(np.asarray(p, dtype=float), 1e-9, 1 - 1e-9)
    return 1 / (1 + np.exp(-(np.log(p / (1 - p)) + delta)))


def prever_json(modelo: dict, df: pd.DataFrame) -> np.ndarray:
    """Regressão logística exportada em JSON: p = sigmoid((x - média)/escala · coef + intercepto + delta)."""
    X = (df[modelo["features"]].to_numpy(float) - np.array(modelo["media"])) / np.array(modelo["escala"])
    z = X @ np.array(modelo["coef"]) + modelo["intercepto"] + modelo.get("delta", 0.0)
    return 1 / (1 + np.exp(-z))


def estimar_delta(p, taxa_alvo: float) -> float:
    """Encontra delta tal que a média das probabilidades ajustadas = taxa_alvo."""
    lo, hi = -10.0, 10.0
    for _ in range(80):  # bisseção
        mid = (lo + hi) / 2
        if ajustar_prevalencia(p, mid).mean() > taxa_alvo:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def construir(chuva: pd.DataFrame, taxa_celula: dict | pd.Series) -> pd.DataFrame:
    """chuva: colunas celula, time, precip (horária, contínua por célula).

    Retorna o mesmo DataFrame com as janelas acumuladas e as FEATURES.
    """
    df = chuva.sort_values(["celula", "time"]).reset_index(drop=True).copy()
    df["precip"] = df["precip"].clip(lower=0)
    g = df.groupby("celula", sort=False)["precip"]
    for nome, h in JANELAS.items():
        df[nome] = g.transform(lambda s, h=h: s.rolling(h, min_periods=1).sum())
        df[f"log_{nome}"] = np.log1p(df[nome])
    hora = df["time"].dt.hour
    df["hora_sin"] = np.sin(2 * np.pi * hora / 24)
    df["hora_cos"] = np.cos(2 * np.pi * hora / 24)
    df["log_taxa_celula"] = np.log1p(df["celula"].map(pd.Series(taxa_celula)).fillna(0.0))
    return df

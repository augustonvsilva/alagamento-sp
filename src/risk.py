"""Conversão de probabilidades do modelo em níveis de risco e agregações."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import LIMIARES_REGIAO, NIVEIS

NIVEIS_CFG = NIVEIS
ORDEM = {n: i for i, (_, n, _) in enumerate(NIVEIS)}
CORES = {n: c for _, n, c in NIVEIS}
EMOJI = {"Baixo": "🟢", "Moderado": "🟡", "Alto": "🟠", "Muito alto": "🔴"}
LIMIARES = {"ponto": [lim for lim, _, _ in NIVEIS], "regiao": LIMIARES_REGIAO}


def classificar(prob: float, escala: str = "ponto") -> str:
    """Nível de risco a partir da probabilidade de alagar na janela considerada."""
    for lim, (_, nome, _) in zip(LIMIARES[escala], NIVEIS):
        if prob < lim:
            return nome
    return NIVEIS[-1][1]


def pior(niveis) -> str:
    niveis = list(niveis)
    return max(niveis, key=ORDEM.get) if niveis else NIVEIS[0][1]


def prob_alguma(probs) -> float:
    """P(pelo menos um evento) assumindo independência: 1 - Π(1 - p)."""
    p = np.clip(np.asarray(probs, dtype=float), 0, 1)
    return float(1 - np.prod(1 - p)) if p.size else 0.0


def simular_chuva(fc: pd.DataFrame, agora: pd.Timestamp, mm_h: float, horas: int) -> pd.DataFrame:
    """Substitui a previsão por uma chuva fixa nas próximas N horas (para demonstração)."""
    fc = fc.copy()
    janela = (fc["time"] >= agora) & (fc["time"] < agora + pd.Timedelta(hours=horas))
    fc.loc[janela, "precip"] = float(mm_h)
    fc.loc[janela, "prob"] = 100.0
    return fc


def janela(df: pd.DataFrame, agora: pd.Timestamp, horas: int) -> pd.DataFrame:
    return df[(df["time"] >= agora) & (df["time"] < agora + pd.Timedelta(hours=horas))]


def resumo(df_horario: pd.DataFrame, chave: str, agora: pd.Timestamp, horas: int = 24,
           escala: str = "ponto") -> pd.DataFrame:
    """Por `chave`: prob. de alagar nas próximas `horas`, prob. agora, hora de pico, chuva."""
    fut = janela(df_horario, agora, horas)
    g = fut.groupby(chave)
    pico = fut.loc[g["p"].idxmax(), [chave, "time"]].set_index(chave)["time"]
    agora_p = fut[fut["time"] == agora].set_index(chave)["p"]
    out = pd.DataFrame({
        "p_janela": g["p"].apply(prob_alguma),
        "p_agora": agora_p,
        "hora_pico": pico,
        "chuva_total_mm": g["precip"].sum(),
        "chuva_pico_mm_h": g["precip"].max(),
    })
    out["nivel"] = out["p_janela"].map(lambda p: classificar(p, escala))
    return out

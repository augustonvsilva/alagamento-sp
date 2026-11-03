"""Etapa 4 — monta o dataset, treina e avalia o modelo de alagamento.

Unidade de análise: (célula da grade, hora).
Alvo: 1 se o CGE registrou o início de pelo menos um alagamento na célula naquela hora.
Validação: temporal (treino antes de DATA_CORTE, teste depois) — evita vazamento
e simula o uso real (prever o futuro com o passado).

Saídas:
    models/modelo.json             modelo final em coeficientes (re-treinado com todos os dados)
    models/metricas.json           métricas no teste, calibração, importância
    data/processed/celulas.parquet taxa histórica por célula
    data/processed/pontos.parquet  pontos de alagamento recorrentes e sua participação
    data/processed/diario.parquet  série diária chuva x alagamentos (para a análise)

Uso:  python -m pipeline.treinar_modelo
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from pipeline import PATHS
from src.nomes import expandir
from src.features import FEATURES, NOMES, ajustar_prevalencia, construir, estimar_delta
from src.grade import celula_id

DATA_CORTE = pd.Timestamp("2025-07-01")
MIN_EVENTOS_PONTO = 3
SEED = 42
# A cidade alaga menos com a mesma chuva ao longo dos anos (drenagem, mudança de registro...).
# Anos recentes pesam mais no treino, e o intercepto é recalibrado para os últimos 12 meses.
MEIA_VIDA_ANOS = 2.0
JANELA_AJUSTE = pd.Timedelta(days=365)


def pesos_temporais(t: pd.Series) -> np.ndarray:
    anos = (t.max() - t).dt.days.to_numpy() / 365.25
    return 0.5 ** (anos / MEIA_VIDA_ANOS)


def treinar(m, d: pd.DataFrame):
    w = pesos_temporais(d["time"])
    if hasattr(m, "steps"):
        m.fit(d[FEATURES], d["y"], **{f"{m.steps[-1][0]}__sample_weight": w})
    else:
        m.fit(d[FEATURES], d["y"], sample_weight=w)
    recente = d[d["time"] >= d["time"].max() - JANELA_AJUSTE]
    delta = estimar_delta(m.predict_proba(recente[FEATURES])[:, 1], recente["y"].mean())
    return m, delta


def prever(m, delta, X) -> np.ndarray:
    return ajustar_prevalencia(m.predict_proba(X[FEATURES])[:, 1], delta)


def exportar_json(m, nome: str, delta: float, d: pd.DataFrame) -> None:
    """Exporta a regressão logística como coeficientes (JSON).

    O app usa este arquivo: não precisa de scikit-learn, o que o torna leve o bastante
    para rodar no navegador (GitHub Pages + stlite).
    """
    if not hasattr(m, "steps"):
        print("AVISO: o modelo escolhido não é a regressão logística; o app (JSON) "
              "usará uma regressão logística treinada à parte.")
        m, delta = treinar(make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000)), d)
        nome = "Regressão logística"
    scaler, lr = m.steps[0][1], m.steps[-1][1]
    modelo = {"nome": nome, "features": FEATURES, "media": scaler.mean_.tolist(),
              "escala": scaler.scale_.tolist(), "coef": lr.coef_[0].tolist(),
              "intercepto": float(lr.intercept_[0]), "delta": float(delta),
              "treinado_em": pd.Timestamp.now().isoformat()}
    # Garante que a fórmula manual reproduz o scikit-learn
    amostra = d.sample(5000, random_state=SEED)
    from src.features import prever_json
    assert np.allclose(prever_json(modelo, amostra), prever(m, delta, amostra), atol=1e-7)
    (PATHS.model / "modelo.json").write_text(json.dumps(modelo, indent=2, ensure_ascii=False),
                                             encoding="utf-8")


def carregar_eventos() -> pd.DataFrame:
    ev = pd.read_parquet(PATHS.processed / "alagamentos_geo.parquet").dropna(subset=["inicio"])
    ev["inicio_ts"] = pd.to_datetime(ev["data"] + " " + ev["inicio"], errors="coerce")
    ev["fim_ts"] = pd.to_datetime(ev["data"] + " " + ev["fim"].fillna(""), errors="coerce")
    ev = ev.dropna(subset=["inicio_ts"])
    ev["hora"] = ev["inicio_ts"].dt.floor("h")
    ev["duracao_min"] = (ev["fim_ts"] - ev["inicio_ts"]).dt.total_seconds() / 60
    ev.loc[ev["duracao_min"] < 0, "duracao_min"] = np.nan
    ev["celula"] = celula_id(ev["lat"], ev["lon"]).values
    return ev


def taxa_por_celula(ev: pd.DataFrame, ini: pd.Timestamp, fim: pd.Timestamp) -> pd.Series:
    """Horas com alagamento por ano em cada célula, no período dado."""
    anos = (fim - ini).days / 365.25
    e = ev[(ev["hora"] >= ini) & (ev["hora"] < fim)]
    return e.groupby("celula")["hora"].nunique() / anos


def metricas(y, p) -> dict:
    return {"roc_auc": float(roc_auc_score(y, p)), "pr_auc": float(average_precision_score(y, p)),
            "brier": float(brier_score_loss(y, p)), "taxa_base": float(np.mean(y))}


def calibracao(y, p, n=10) -> list[dict]:
    """Agrupa por quantis da probabilidade prevista (só onde há chuva relevante)."""
    d = pd.DataFrame({"y": y, "p": p})
    d = d[d["p"] > d["p"].quantile(0.5)]
    d["bin"] = pd.qcut(d["p"], n, duplicates="drop")
    g = d.groupby("bin", observed=True).agg(prevista=("p", "mean"), observada=("y", "mean"), n=("y", "size"))
    return g.reset_index(drop=True).to_dict("records")


def heuristica(df) -> np.ndarray:
    """Regra inicial do protótipo (limiares fixos) — usada como baseline."""
    s = np.maximum(df["p1h"] / 30, df["p3h"] / 45) * (1 + 0.3 * np.clip(df["p24h"] / 60, 0, 1))
    return np.clip(s, 0, 1)


def main(corte: pd.Timestamp = DATA_CORTE) -> None:
    global DATA_CORTE
    DATA_CORTE = corte
    ev = carregar_eventos()
    chuva = pd.read_parquet(PATHS.processed / "chuva_horaria.parquet").dropna(subset=["precip"])
    chuva = chuva[chuva["time"] <= ev["hora"].max().ceil("D")]  # só o período coberto pelo CGE
    ini, fim = chuva["time"].min(), chuva["time"].max()
    print(f"Chuva: {ini:%Y-%m-%d} a {fim:%Y-%m-%d}, {chuva['celula'].nunique()} células")

    taxa_treino = taxa_por_celula(ev, ini, DATA_CORTE)
    df = construir(chuva, taxa_treino)
    alvo = set(zip(ev["celula"], ev["hora"]))
    df["y"] = [int(k in alvo) for k in zip(df["celula"], df["time"])]
    print(f"Dataset: {len(df):,} horas-célula, {df['y'].sum():,} com alagamento ({df['y'].mean():.3%})")

    tr, te = df[df["time"] < DATA_CORTE], df[df["time"] >= DATA_CORTE]
    candidatos = {
        "Regressão logística": make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000)),
        "Gradient boosting": HistGradientBoostingClassifier(
            max_iter=400, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=200,
            l2_regularization=1.0, early_stopping=True, validation_fraction=0.15, random_state=SEED),
    }
    resultados = {"Heurística (protótipo)": metricas(te["y"], heuristica(te))}
    previsoes = {}
    # Referência sem os ajustes temporais, para mostrar o efeito deles
    sem_ajuste = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000))
    sem_ajuste.fit(tr[FEATURES], tr["y"])
    resultados["Regressão logística sem ajuste temporal"] = metricas(
        te["y"], sem_ajuste.predict_proba(te[FEATURES])[:, 1])
    for nome, m in candidatos.items():
        m, delta = treinar(m, tr)
        previsoes[nome] = prever(m, delta, te)
        resultados[nome] = metricas(te["y"], previsoes[nome])
        print(f"{nome}: {resultados[nome]} (delta={delta:.3f})")
    for k in ("Heurística (protótipo)", "Regressão logística sem ajuste temporal"):
        print(f"{k}: {resultados[k]}")

    # Parcimônia: o modelo complexo só vence se for >= 5% melhor em PR-AUC que o simples
    simples, complexo = "Regressão logística", "Gradient boosting"
    ganho = resultados[complexo]["pr_auc"] / resultados[simples]["pr_auc"] - 1
    melhor = complexo if ganho >= 0.05 else simples
    print(f"Modelo escolhido: {melhor} (ganho do gradient boosting: {ganho:+.1%})")

    amostra = te.sample(min(len(te), 150_000), random_state=SEED)
    imp = permutation_importance(candidatos[melhor], amostra[FEATURES], amostra["y"],
                                 scoring="average_precision", n_repeats=5, random_state=SEED)
    importancia = sorted(({"feature": NOMES[f], "importancia": float(v)}
                          for f, v in zip(FEATURES, imp.importances_mean)),
                         key=lambda d: -d["importancia"])

    # Modelo final: mesmos hiperparâmetros, todos os dados, taxa da célula do período completo
    taxa_total = taxa_por_celula(ev, ini, fim)
    df_full = construir(chuva, taxa_total)
    df_full["y"] = df["y"].values
    final, delta_final = treinar(candidatos[melhor], df_full)
    print(f"Modelo final: delta de prevalência = {delta_final:.3f}")
    exportar_json(final, melhor, delta_final, df_full)

    # Probabilidade x chuva (curva de resposta), para explicar o modelo
    grade = pd.DataFrame({"p1h": np.r_[0:61:2.0]})
    for k in ("p3h", "p6h"):
        grade[k] = grade["p1h"]
    grade["p24h"] = grade["p72h"] = grade["p1h"] + 5
    for k in ("p1h", "p3h", "p6h", "p24h", "p72h"):
        grade[f"log_{k}"] = np.log1p(grade[k])
    grade["hora_sin"], grade["hora_cos"] = np.sin(2 * np.pi * 17 / 24), np.cos(2 * np.pi * 17 / 24)
    grade["log_taxa_celula"] = np.log1p(taxa_total.median())
    resposta = [{"chuva_mm_h": float(a), "prob": float(b)}
                for a, b in zip(grade["p1h"], prever(final, delta_final, grade))]

    json.dump({
        "modelo_escolhido": melhor, "ganho_complexo": float(ganho), "data_corte": str(DATA_CORTE.date()),
        "periodo": [str(ini.date()), str(fim.date())],
        "n_treino": int(len(tr)), "n_teste": int(len(te)),
        "positivos_treino": int(tr["y"].sum()), "positivos_teste": int(te["y"].sum()),
        "resultados": resultados, "calibracao": calibracao(te["y"].values, previsoes[melhor]),
        "importancia": importancia, "resposta_chuva": resposta,
    }, open(PATHS.model / "metricas.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # Células (taxa histórica usada na inferência)
    cel = taxa_total.rename("taxa").reset_index()
    cel.to_parquet(PATHS.processed / "celulas.parquet", index=False)

    # Pontos recorrentes: participação do ponto nas horas de alagamento da sua célula
    horas_cel = ev.groupby("celula")["hora"].nunique()
    loc = ev[ev["precisao"] == "logradouro"]
    pontos = (loc.groupby(["local_n", "bairro_n"])
              .agg(bairro=("bairro", "first"), zona=("zona", "first"), lat=("lat", "median"),
                   lon=("lon", "median"), celula=("celula", "first"), n_eventos=("hora", "nunique"),
                   frac_intransitavel=("intransitavel", "mean"), duracao_media_min=("duracao_min", "mean"),
                   primeiro=("data", "min"), ultimo=("data", "max"))
              .reset_index())
    pontos = pontos[pontos["n_eventos"] >= MIN_EVENTOS_PONTO].copy()
    pontos["nome"] = pontos["local_n"].map(expandir)
    pontos["participacao"] = pontos["n_eventos"] / (pontos["celula"].map(horas_cel) + 5)
    pontos = pontos.sort_values("n_eventos", ascending=False).reset_index(drop=True)
    pontos.to_parquet(PATHS.processed / "pontos.parquet", index=False)
    print(f"{len(pontos)} pontos recorrentes (>= {MIN_EVENTOS_PONTO} eventos)")

    # Série diária para análise exploratória (todo o histórico do CGE)
    ev_dia = pd.read_parquet(PATHS.raw / "cge_alagamentos.parquet").groupby("data").size()
    ch_dia = chuva.assign(data=chuva["time"].dt.strftime("%Y-%m-%d")).groupby(["data", "celula"])["precip"] \
        .sum().groupby("data").agg(["mean", "max"]).rename(columns={"mean": "chuva_media_mm",
                                                                    "max": "chuva_max_celula_mm"})
    todos_dias = pd.Index(pd.date_range(ev["data"].min(), fim).strftime("%Y-%m-%d"), name="data")
    diario = ch_dia.reindex(todos_dias).assign(alagamentos=ev_dia.reindex(todos_dias).fillna(0).astype(int))
    diario.reset_index().to_parquet(PATHS.processed / "diario.parquet", index=False)
    print("OK")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--corte", type=pd.Timestamp, default=DATA_CORTE,
                    help="início do período de teste (validação temporal)")
    main(ap.parse_args().corte)

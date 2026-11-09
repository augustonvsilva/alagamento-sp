"""Etapa 1 — coleta o histórico diário de alagamentos publicado pelo CGE/SP.

Fonte: https://www.cgesp.org/v3/alagamentos.jsp?dataBusca=DD/MM/AAAA
Saída: data/raw/cge_alagamentos.parquet (um registro por ponto de alagamento)

Uso:
    python -m pipeline.coletar_cge --inicio 2023-01-01 --fim 2026-11-02

É incremental: dias já coletados (data/raw/cge_dias/*.json) não são baixados de novo.
"""
from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

import pandas as pd
import requests

from pipeline import PATHS
from src.cge import URL, parse_dia  # noqa: F401 — parse_dia é reexportado para os testes

HEADERS = {"User-Agent": "alagamento-sp/1.0 (projeto academico de analise de dados)"}


def baixar_dia(dia: date, tentativas: int = 5) -> list[dict]:
    params = {"dataBusca": dia.strftime("%d/%m/%Y"), "enviaBusca": "Buscar"}
    for t in range(tentativas):
        try:
            r = requests.get(URL, params=params, headers=HEADERS, timeout=30)
            if r.status_code in (403, 429):  # limite de requisições: espera bastante
                print(f"  servidor pediu pausa ({r.status_code}), aguardando...", flush=True)
                time.sleep(180 * (t + 1))
                continue
            r.raise_for_status()
            r.encoding = r.apparent_encoding or "utf-8"
            return parse_dia(r.text, dia)
        except requests.RequestException:
            time.sleep(2 ** t)
    raise RuntimeError(f"falha ao baixar {dia}")


def main(inicio: date, fim: date, workers: int = 1, pausa: float = 1.5) -> None:
    pasta = PATHS.raw / "cge_dias"
    pasta.mkdir(parents=True, exist_ok=True)
    dias = [inicio + timedelta(d) for d in range((fim - inicio).days + 1)]
    # Mais recentes primeiro: são os mais importantes para o treino
    pendentes = [d for d in reversed(dias) if not (pasta / f"{d}.json").exists()]
    # Sem o cache por dia (ex.: no GitHub Actions), os dias já consolidados no parquet do
    # repositório não são baixados de novo — só os últimos dias, que podem ter mudado.
    consolidado = PATHS.raw / "cge_alagamentos.parquet"
    anteriores = pd.read_parquet(consolidado) if consolidado.exists() else pd.DataFrame(columns=["data"])
    if len(anteriores):
        ultimo = date.fromisoformat(str(anteriores["data"].max()))
        pendentes = [d for d in pendentes if d > ultimo - timedelta(days=3)]
    print(f"{len(dias)} dias no período, {len(pendentes)} a baixar")

    def tarefa(d):
        regs = baixar_dia(d)
        (pasta / f"{d}.json").write_text(json.dumps(regs, ensure_ascii=False), encoding="utf-8")
        time.sleep(pausa)  # gentileza com o servidor da prefeitura
        return d, len(regs)

    feitos = 0
    if workers > 0 and pendentes:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for fut in as_completed([ex.submit(tarefa, d) for d in pendentes]):
                try:
                    fut.result()
                except RuntimeError as e:
                    print("  !", e, flush=True)
                feitos += 1
                if feitos % 50 == 0:
                    print(f"  {feitos}/{len(pendentes)}", flush=True)

    regs, dias_json = [], set()
    for d in dias:
        arq = pasta / f"{d}.json"
        if arq.exists():
            regs.extend(json.loads(arq.read_text(encoding="utf-8")))
            dias_json.add(d.isoformat())
    # Dias sem arquivo próprio vêm do consolidado anterior
    periodo = {d.isoformat() for d in dias}
    antigos = anteriores[anteriores["data"].isin(periodo - dias_json)]
    df = pd.concat([antigos, pd.DataFrame(regs)], ignore_index=True).sort_values("data", kind="stable")
    df = df.drop(columns="ativo", errors="ignore")  # "ativo" só faz sentido ao vivo
    df.to_parquet(PATHS.raw / "cge_alagamentos.parquet", index=False)
    print(f"OK: {len(df)} registros de alagamento em {df['data'].nunique() if len(df) else 0} dias")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--inicio", type=date.fromisoformat, default=date(2023, 1, 1))
    ap.add_argument("--fim", type=date.fromisoformat, default=date.today() - timedelta(days=1))
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--pausa", type=float, default=1.5, help="segundos entre requisições")
    ap.add_argument("--apenas-consolidar", action="store_true",
                    help="não baixa nada, só junta os dias já coletados")
    a = ap.parse_args()
    main(a.inicio, a.fim, 0 if a.apenas_consolidar else a.workers, a.pausa)

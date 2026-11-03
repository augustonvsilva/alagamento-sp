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
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

import pandas as pd
import requests
from bs4 import BeautifulSoup

from pipeline import PATHS

URL = "https://www.cgesp.org/v3/alagamentos.jsp"
HEADERS = {"User-Agent": "alagamento-sp/1.0 (projeto academico de analise de dados)"}
RE_HORARIO = re.compile(r"De\s*(\d{1,2}:\d{2})\s*a\s*(\d{1,2}:\d{2})?")


def parse_dia(html: str, dia: date) -> list[dict]:
    """Extrai os pontos de alagamento de uma página diária do CGE."""
    soup = BeautifulSoup(html, "html.parser")
    registros = []
    zona = None
    # Percorre em ordem do documento: títulos de zona e tabelas de bairro
    for el in soup.find_all(["h1", "table"]):
        if el.name == "h1" and "tit-bairros" in (el.get("class") or []):
            zona = el.get_text(strip=True)
            continue
        if el.name != "table" or "tb-pontos-de-alagamentos" not in (el.get("class") or []):
            continue
        td_bairro = el.find("td", class_="bairro")
        bairro = td_bairro.get_text(" ", strip=True) if td_bairro else None
        for ponto in el.find_all("div", class_="ponto-de-alagamento"):
            lis = ponto.find_all("li")
            status = next((" ".join(li.get("class")) for li in lis
                           if li.get("class") and "transitavel" in " ".join(li.get("class"))), "")
            descr = [li for li in lis if "arial-descr-alag" in (li.get("class") or [])]
            if not descr:
                continue
            partes_local = descr[0].get_text("\n", strip=True).split("\n")
            m = RE_HORARIO.search(partes_local[0]) if partes_local else None
            local = partes_local[-1].strip() if len(partes_local) > 1 else None
            sentido = referencia = None
            if len(descr) > 1:
                for linha in descr[1].get_text("\n", strip=True).split("\n"):
                    if linha.startswith("Sentido:"):
                        sentido = linha.split(":", 1)[1].strip()
                    elif linha.startswith("Refer"):
                        referencia = linha.split(":", 1)[1].strip()
            registros.append({
                "data": dia.isoformat(),
                "zona": zona,
                "bairro": bairro,
                "inicio": m.group(1) if m else None,
                "fim": m.group(2) if m and m.group(2) else None,
                "local": local,
                "sentido": sentido,
                "referencia": referencia,
                "intransitavel": "intransitavel" in status,
            })
    return registros


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

    regs = []
    for d in dias:
        arq = pasta / f"{d}.json"
        if arq.exists():
            regs.extend(json.loads(arq.read_text(encoding="utf-8")))
    df = pd.DataFrame(regs)
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

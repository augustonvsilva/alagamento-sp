"""Leitura das páginas de alagamentos do CGE (histórico e o dia de hoje, ao vivo).

Usado pelo pipeline (coleta do histórico) e pelo app (alagamentos registrados hoje).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date

from bs4 import BeautifulSoup

URL = "https://www.cgesp.org/v3/alagamentos.jsp"
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
                # "ativo-..." = alagamento ainda em andamento (só no dia corrente)
                "ativo": status.startswith("ativo"),
            })
    return registros


def normalizar_bairro(s: str) -> str:
    """Chave do bairro: sem acentos, minúsculas (igual à usada na geocodificação)."""
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().strip()

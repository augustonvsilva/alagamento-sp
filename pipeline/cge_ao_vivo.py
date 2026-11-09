"""Cópia ao vivo dos alagamentos de hoje do CGE, em JSON.

O site do CGE não permite ser lido por páginas de outros endereços (CORS), então a versão
do app no navegador não consegue buscá-lo direto. Este script roda a cada ~15 min no
GitHub Actions (.github/workflows/cge_ao_vivo.yml) e publica o JSON no ramo `ao-vivo`,
que o app lê (src/ao_vivo.py).

Uso:  python -m pipeline.cge_ao_vivo saida/ao_vivo.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from src.cge import URL, parse_dia
from src.config import TZ, USER_AGENT


def main(saida: Path) -> None:
    agora = datetime.now(ZoneInfo(TZ))
    r = requests.get(URL, params={"dataBusca": agora.strftime("%d/%m/%Y"), "enviaBusca": "Buscar"},
                     headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    regs = parse_dia(r.text, agora.date())
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps({"atualizado_em": agora.replace(tzinfo=None).isoformat(timespec="minutes"),
                                 "registros": regs}, ensure_ascii=False), encoding="utf-8")
    print(f"{len(regs)} alagamento(s) hoje, {sum(x['ativo'] for x in regs)} ativo(s)")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "ao_vivo.json"))

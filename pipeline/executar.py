"""Roda o pipeline completo: coleta -> geocodificação -> chuva histórica -> treino.

Uso:
    python -m pipeline.executar                  # tudo, desde 2019
    python -m pipeline.executar --pular-coleta   # reaproveita a coleta do CGE já feita

Tempo aproximado na primeira execução: 1-3 h (limitado pela gentileza com as APIs
públicas). As execuções seguintes são incrementais e usam cache.
"""
import argparse
from datetime import date, timedelta

from pipeline import chuva_historica, coletar_cge, geocodificar, treinar_modelo

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--inicio", type=date.fromisoformat, default=date(2019, 1, 1))
    ap.add_argument("--pular-coleta", action="store_true")
    a = ap.parse_args()
    fim = date.today() - timedelta(days=2)

    print("== 1/4 Coleta CGE ==")
    coletar_cge.main(a.inicio, fim, workers=0 if a.pular_coleta else 1)
    print("== 2/4 Geocodificação ==")
    geocodificar.main()
    print("== 3/4 Chuva histórica ==")
    chuva_historica.main(a.inicio, fim)
    print("== 4/4 Treino ==")
    treinar_modelo.main()

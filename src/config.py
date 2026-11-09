"""Configurações centrais do projeto."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PROCESSED = DATA / "processed"
MODELS = ROOT / "models"

TZ = "America/Sao_Paulo"
CENTRO_SP = (-23.5505, -46.6333)

# Caixa do município de São Paulo
BBOX = {"lat_min": -23.99, "lat_max": -23.35, "lon_min": -46.83, "lon_max": -46.36}

# Grade de chuva. Os modelos de previsão usados pelo Open-Meteo na região têm
# resolução de ~10-25 km; uma grade de 0,1° (~11 km) não perde informação.
PASSO_GRADE = 0.1

USER_AGENT = "alagamento-sp/1.0 (projeto academico de analise de dados)"

# Chance de alagar na janela (ex.: próximas 24h) -> nível de risco.
# Escala "ponto": um local específico. Escala "regiao": algum alagamento numa célula de ~11 km,
# naturalmente mais provável. Limiares definidos a partir da distribuição das previsões
# do modelo em cenários de chuva fraca, moderada e forte.
NIVEIS = [
    (0.02, "Baixo", "#2E9E5B"),
    (0.05, "Moderado", "#E0A100"),
    (0.15, "Alto", "#E8710A"),
    (float("inf"), "Muito alto", "#D93025"),
]
LIMIARES_REGIAO = [0.10, 0.30, 0.60, float("inf")]

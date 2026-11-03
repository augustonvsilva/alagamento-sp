"""Pipeline de dados: coleta -> geocodificação -> chuva histórica -> treino do modelo."""
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class _Paths:
    data: Path = ROOT / "data"
    raw: Path = ROOT / "data" / "raw"
    processed: Path = ROOT / "data" / "processed"
    model: Path = ROOT / "models"


PATHS = _Paths()
for _p in (PATHS.raw, PATHS.processed, PATHS.model):
    _p.mkdir(parents=True, exist_ok=True)

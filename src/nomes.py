"""Normalização e expansão de nomes de logradouros do CGE ("AV. PROF X" -> "Avenida Professor X")."""
import re

ABREV = {
    "R": "Rua", "AV": "Avenida", "AL": "Alameda", "PCA": "Praça", "PÇA": "Praça", "PC": "Praça",
    "PTE": "Ponte", "VD": "Viaduto", "VIAD": "Viaduto", "TUN": "Túnel", "EST": "Estrada",
    "TRAV": "Travessa", "TV": "Travessa", "LGO": "Largo", "LG": "Largo", "ROD": "Rodovia",
    "MARG": "Marginal", "PQ": "Parque", "CEL": "Coronel", "DR": "Doutor", "PROF": "Professor",
    "PROFA": "Professora", "ENG": "Engenheiro", "GAL": "General", "GEN": "General",
    "SEN": "Senador", "PRES": "Presidente", "MAL": "Marechal", "BRIG": "Brigadeiro",
    "STO": "Santo", "STA": "Santa", "DEP": "Deputado", "VER": "Vereador", "GOV": "Governador",
    "CDE": "Conde", "BR": "Barão", "VISC": "Visconde", "MARQ": "Marquês", "CAP": "Capitão",
    "TEN": "Tenente", "JD": "Jardim", "VL": "Vila", "PE": "Padre", "ALM": "Almirante",
    "COM": "Comendador", "DQ": "Duque", "PRINC": "Princesa", "CONS": "Conselheiro",
    "DES": "Desembargador", "MIN": "Ministro", "SGT": "Sargento", "CB": "Cabo",
    "MONS": "Monsenhor", "FREI": "Frei", "IRM": "Irmã", "CMTE": "Comandante",
}
CONECTIVOS = {"DE", "DA", "DO", "DAS", "DOS", "E"}


def normalizar(local: str) -> str:
    """Chave canônica: maiúsculas, sem pontos, espaços simples ("AV. X" == "AV X")."""
    return re.sub(r"\s+", " ", local.upper().replace(".", " ")).strip()


def expandir(local: str) -> str:
    palavras = normalizar(local).split(" ")
    out = []
    for i, p in enumerate(palavras):
        if i > 0 and p in CONECTIVOS:
            out.append(p.lower())
        else:
            out.append(ABREV.get(p, p.title()))
    return " ".join(out)

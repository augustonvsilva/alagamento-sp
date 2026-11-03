from datetime import date

import numpy as np
import pandas as pd
import pytest

from pipeline.coletar_cge import parse_dia
from src.nomes import expandir, normalizar
from src import features, geo, risk
from src.grade import celula_id, id_para_coord

HTML_CGE = """
<h1 class="tit-bairros">Zona Norte</h1>
<table class="tb-pontos-de-alagamentos">
  <tr><td class="bairro arial-bairros-alag linha-pontilhada">Casa Verde <hr/></td>
      <td class="total-pts arial-bairros-alag">1 pts.</td></tr>
  <tr><td colspan="3"><div class="ponto-de-alagamento"><ul>
    <li class="inativo-intransitavel" title="Inativo Intransitável"></li>
    <li class="espaco"></li>
    <li class="arial-descr-alag col-local">De 15:52 a 16:10<br/>R REIMS</li>
    <li class="ln-vert"></li>
    <li class="arial-descr-alag">Sentido: UNICO<br/>Referência: AV CASA VERDE</li>
  </ul></div></td></tr>
</table>
<h1 class="tit-bairros">Zona Sul</h1>
<table class="tb-pontos-de-alagamentos">
  <tr><td class="bairro arial-bairros-alag linha-pontilhada">Santo Amaro <hr/></td></tr>
  <tr><td colspan="3"><div class="ponto-de-alagamento"><ul>
    <li class="ativo-transitavel"></li>
    <li class="arial-descr-alag col-local">De 17:05 a <br/>AV JOAO DIAS</li>
    <li class="arial-descr-alag">Sentido: AMBOS<br/>Referência: ALTURA DO N. 10</li>
  </ul></div></td></tr>
</table>
"""


def test_parse_dia_extrai_campos():
    regs = parse_dia(HTML_CGE, date(2026, 1, 15))
    assert len(regs) == 2
    r = regs[0]
    assert (r["zona"], r["bairro"], r["inicio"], r["fim"], r["local"]) == \
        ("Zona Norte", "Casa Verde", "15:52", "16:10", "R REIMS")
    assert r["referencia"] == "AV CASA VERDE" and r["intransitavel"] is True
    assert regs[1]["zona"] == "Zona Sul" and regs[1]["fim"] is None and regs[1]["intransitavel"] is False


def test_parse_dia_vazio():
    assert parse_dia("<html><body>Nenhum alagamento</body></html>", date(2026, 1, 1)) == []


@pytest.mark.parametrize("entrada,esperado", [
    ("R REIMS", "Rua Reims"),
    ("AV PROF LUIZ IGNACIO ANHAIA MELLO", "Avenida Professor Luiz Ignacio Anhaia Mello"),
    ("PTE DAS BANDEIRAS", "Ponte das Bandeiras"),
    ("AV DOS BANDEIRANTES", "Avenida dos Bandeirantes"),
])
def test_expandir_abreviacoes(entrada, esperado):
    assert expandir(entrada) == esperado


def test_normalizar_unifica_variantes():
    assert normalizar("AV. MERCURIO") == normalizar("AV MERCURIO") == normalizar(" av  mercurio ")


def test_grade_ida_e_volta():
    cid = celula_id(-23.5489, -46.6388)
    assert cid == "-23.5_-46.6"
    assert id_para_coord(cid) == (-23.5, -46.6)


def test_haversine_conhecido():
    # Praça da Sé -> Av. Paulista (MASP): ~2,5 km em linha reta
    d = geo.haversine_m(-23.5503, -46.6339, -23.5614, -46.6559)
    assert 2400 < d < 2700


def test_features_janelas_acumuladas():
    t = pd.date_range("2026-01-01", periods=5, freq="h")
    chuva = pd.DataFrame({"celula": "c", "time": t, "precip": [0, 10, 5, 0, 1]})
    f = features.construir(chuva, {"c": 2.0})
    assert f["p3h"].tolist() == [0, 10, 15, 15, 6]
    assert np.isclose(f["log_taxa_celula"].iloc[0], np.log1p(2.0))
    assert set(features.FEATURES) <= set(f.columns)


def test_prob_alguma_e_niveis():
    assert risk.prob_alguma([]) == 0
    assert np.isclose(risk.prob_alguma([0.5, 0.5]), 0.75)
    assert risk.classificar(0.0) == "Baixo"
    assert risk.classificar(0.99) == "Muito alto"
    assert risk.pior(["Baixo", "Alto", "Moderado"]) == "Alto"


def test_404_html_igual_ao_index():
    """O GitHub Pages serve o 404.html nas sub-URLs (ex.: /trajeto): precisa ser cópia do index.html."""
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent
    assert (raiz / "404.html").read_bytes() == (raiz / "index.html").read_bytes(), \
        "Rode: Copy-Item index.html 404.html"


def test_index_html_lista_arquivos_do_app():
    """Todo .py usado pelo app precisa estar na lista `arquivos` do index.html (stlite)."""
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent
    html = (raiz / "index.html").read_text(encoding="utf-8")
    for arq in ["app.py", *[f"src/{p.name}" for p in (raiz / "src").glob("*.py")],
                *[f"paginas/{p.name}" for p in (raiz / "paginas").glob("*.py")]]:
        assert f'"{arq}"' in html, f"{arq} não está no index.html"


def test_simulacao_so_altera_janela():
    t = pd.date_range("2026-01-01", periods=6, freq="h")
    fc = pd.DataFrame({"time": t, "precip": 0.0, "prob": 0.0})
    s = risk.simular_chuva(fc, t[2], 30, 2)
    assert s["precip"].tolist() == [0, 0, 30, 30, 0, 0]

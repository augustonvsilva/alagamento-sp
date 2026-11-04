"""Teste de fumaça: todas as páginas renderizam sem exceção (usa APIs reais — requer internet)."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
PAGINAS = ["paginas/visao_geral.py", "paginas/minha_regiao.py", "paginas/trajeto.py",
           "paginas/analise.py", "paginas/modelo.py"]

pytestmark = pytest.mark.skipif(not (ROOT / "models" / "modelo.json").exists(),
                                reason="modelo não treinado")


@pytest.mark.parametrize("simulacao", [False, True])
@pytest.mark.parametrize("pagina", PAGINAS)
def test_pagina_renderiza(pagina, simulacao):
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.session_state["sim_on"] = simulacao
    at.run()
    at.switch_page(pagina).run()
    assert not at.exception, at.exception
    if pagina.endswith("trajeto.py"):
        next(b for b in at.button if b.label == "Calcular trajeto").click().run()
        assert not at.exception, at.exception
        assert not at.error, [e.value for e in at.error]


@pytest.mark.parametrize("lat,lon,usa_gps", [(-23.5614, -46.6559, True),   # Av. Paulista
                                             (-22.9068, -43.1729, False)])  # Rio: fora de SP
def test_minha_regiao_com_localizacao(lat, lon, usa_gps):
    """Localização vinda do aparelho (?lat&lon) abre "Minha região" já com a área da pessoa."""
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.query_params["lat"], at.query_params["lon"] = str(lat), str(lon)
    at.run()
    assert at.session_state["minha_loc"] == (lat, lon)
    at.switch_page("paginas/minha_regiao.py").run()
    assert not at.exception, at.exception
    assert (len(at.radio) == 1) == usa_gps
    if usa_gps:
        assert at.radio[0].value == "📍 Minha localização"
        assert not at.text_input  # não pede endereço: usa a posição

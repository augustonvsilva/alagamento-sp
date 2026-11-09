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


@pytest.mark.parametrize("pagina", ["paginas/visao_geral.py", "paginas/minha_regiao.py"])
def test_sem_internet_usa_previsao_salva(pagina, tmp_path, monkeypatch):
    """Sem internet, as páginas usam a última previsão salva e avisam; sem cópia, mostram erro amigável."""
    import requests
    import streamlit as st

    from src import offline, weather

    monkeypatch.setattr(offline, "PASTA", tmp_path)

    def rodar():
        st.cache_data.clear()
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
        at.session_state["minha_loc"] = (-23.5614, -46.6559)
        at.run()
        return at.switch_page(pagina).run()

    rodar()  # com internet: guarda a previsão
    assert (tmp_path / offline.ARQ_PREVISAO).exists()

    monkeypatch.setattr(weather.requests, "get", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError()))
    at = rodar()
    assert not at.exception, at.exception
    assert any("Sem internet" in w.value for w in at.warning)

    (tmp_path / offline.ARQ_PREVISAO).unlink()
    at = rodar()
    assert not at.exception, at.exception
    assert any("verifique sua conexão" in e.value for e in at.error)
    if pagina.endswith("minha_regiao.py"):  # mesmo sem previsão, mostra pontos e histórico
        assert any(h.value.startswith("Pontos de alagamento") for h in at.subheader)
        assert any(h.value == "Histórico da região" for h in at.subheader)

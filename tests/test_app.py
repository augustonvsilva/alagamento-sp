"""Teste de fumaça: todas as páginas renderizam sem exceção (usa APIs reais — requer internet)."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
PAGINAS = ["paginas/visao_geral.py", "paginas/minha_regiao.py", "paginas/trajeto.py",
           "paginas/analise.py", "paginas/modelo.py"]

pytestmark = pytest.mark.skipif(not (ROOT / "models" / "modelo.joblib").exists(),
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

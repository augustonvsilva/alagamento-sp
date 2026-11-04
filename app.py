"""Alerta Alagamento SP — previsão de alagamentos a partir da previsão do tempo.

Rodar:  streamlit run app.py
"""
import streamlit as st

from src import servico, ui
from src.config import MODELS, PROCESSED

st.set_page_config(page_title="Alerta Alagamento SP", page_icon="🌧️", layout="wide",
                   menu_items={"About": "Projeto acadêmico de análise de dados — previsão de "
                                        "alagamentos em São Paulo com dados do CGE e Open-Meteo."})
ui.css()

faltando = [p.name for p in (MODELS / "modelo.json", PROCESSED / "pontos.parquet",
                             PROCESSED / "celulas.parquet") if not p.exists()]
if faltando:
    st.error(f"Artefatos do modelo não encontrados ({', '.join(faltando)}). "
             "Rode o pipeline de dados: `python -m pipeline.executar` (veja o README).")
    st.stop()

PAGINAS = {
    "Previsão": [
        st.Page("paginas/visao_geral.py", title="Visão geral", icon="🗺️", default=True),
        st.Page("paginas/minha_regiao.py", title="Minha região", icon="📍"),
        st.Page("paginas/trajeto.py", title="Trajeto seguro", icon="🚗"),
    ],
    "Dados e modelo": [
        st.Page("paginas/analise.py", title="Análise histórica", icon="📊"),
        st.Page("paginas/modelo.py", title="Como o modelo funciona", icon="🧠"),
    ],
}
paginas = st.navigation(PAGINAS)

# Localização do aparelho (?lat=..&lon=..), enviada pelo index.html quando a pessoa permite
# o acesso à localização (no navegador ou no app Android). Usada em "Minha região".
if "lat" in st.query_params and "lon" in st.query_params:
    try:
        st.session_state["minha_loc"] = (float(st.query_params["lat"]), float(st.query_params["lon"]))
    except ValueError:
        pass
    del st.query_params["lat"]
    del st.query_params["lon"]

# Link direto para uma página (?pagina=trajeto). Usado pelo GitHub Pages ao recarregar
# uma sub-URL como /alagamento-sp/trajeto (veja index.html / 404.html).
alvo = st.query_params.get("pagina")
if alvo:
    del st.query_params["pagina"]
    destino = {p.url_path: p for grupo in PAGINAS.values() for p in grupo}.get(alvo)
    if destino is not None and destino.url_path != paginas.url_path:
        st.switch_page(destino)

with st.sidebar:
    st.markdown("### 🌧️ Alerta Alagamento SP")
    st.caption("Previsão de alagamentos baseada no histórico do CGE e na previsão do tempo.")
    with st.expander("🧪 Modo simulação", expanded=False):
        st.caption("Força uma chuva em toda a cidade — útil para demonstrar o app em dia seco.")
        ativo = st.toggle("Ativar simulação", key="sim_on")
        mm = st.slider("Intensidade (mm/h)", 1, 80, 20, key="sim_mm", disabled=not ativo)
        h = st.slider("Duração (horas)", 1, 6, 2, key="sim_h", disabled=not ativo)
        st.session_state["sim"] = (mm, h) if ativo else None
    st.caption(f"Previsão das {servico.agora_sp():%Hh} · atualiza a cada 30 min")
    if st.button("🔄 Atualizar agora", width="stretch"):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    st.caption("Fontes: CGE/Prefeitura de SP · Open-Meteo · OpenStreetMap · OSRM")

paginas.run()

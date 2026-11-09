"""Componentes visuais reutilizados pelas páginas."""
from __future__ import annotations

import altair as alt
import folium
import pandas as pd
import streamlit as st

from src import risk
from src.config import CENTRO_SP, PASSO_GRADE

AZUL = "#1f4e79"


def css():
    st.markdown("""
    <style>
      .block-container {padding-top: 1.6rem; padding-bottom: 2rem;}
      [data-testid="stMetricValue"] {font-size: 1.6rem;}
      .badge {display:inline-block; padding:.15rem .6rem; border-radius:999px; color:#fff;
              font-weight:600; font-size:.85rem;}
      .alerta {border-left:6px solid; padding:.7rem 1rem; border-radius:.4rem;
               background:rgba(127,127,127,.08); margin-bottom:.6rem;}
      .alerta b {font-size:1.05rem;}
      .muted {opacity:.7; font-size:.85rem;}
    </style>""", unsafe_allow_html=True)


def pct(p: float) -> str:
    if pd.isna(p):
        return "—"
    if p < 0.01:
        return "< 1%"
    return f"{p:.0%}"


def badge(nivel: str) -> str:
    return f'<span class="badge" style="background:{risk.CORES[nivel]}">{nivel}</span>'


def alerta(titulo: str, texto: str, nivel: str):
    st.markdown(f'<div class="alerta" style="border-color:{risk.CORES[nivel]}">'
                f'<b>{risk.EMOJI[nivel]} {titulo}</b><br><span>{texto}</span></div>',
                unsafe_allow_html=True)


def aviso_simulacao():
    sim = st.session_state.get("sim")
    if sim:
        st.warning(f"**Modo simulação ativo:** chuva de {sim[0]} mm/h nas próximas {sim[1]}h em toda a "
                   "cidade. Os números abaixo **não** são a previsão real.", icon="🧪")


SEM_INTERNET = ("Não foi possível consultar a previsão do tempo — verifique sua conexão com a internet. "
                "Depois que o app abrir uma vez com internet, ele guarda a previsão para usar sem conexão.")


def aviso_offline(salva_em: pd.Timestamp | None, agora: pd.Timestamp, fim_previsao: pd.Timestamp) -> None:
    """Sem internet: avisa que a previsão é a última guardada (e para a página se ela já expirou)."""
    if salva_em is None:
        return
    msg = f"**Sem internet** — usando a última previsão salva no aparelho, de {salva_em:%d/%m às %Hh%M}."
    if fim_previsao < agora:
        st.error(msg + " Ela já expirou: conecte-se à internet para ver o risco atual.", icon="📴")
        st.stop()
    st.warning(msg + " A chuva prevista pode ter mudado desde então.", icon="📴")


def mapa(center=CENTRO_SP, zoom=11) -> folium.Map:
    return folium.Map(location=center, zoom_start=zoom, tiles="OpenStreetMap", control_scale=True)


def mostrar_mapa(m: folium.Map, altura: int = 500):
    """Renderiza o mapa como HTML estático (funciona no Streamlit normal e no navegador via stlite)."""
    m.get_root().height = f"{altura}px"
    # HTML gerado pelo próprio app (folium), não por usuários: seguro para iframe
    st.iframe(m.get_root().render(), height=altura + 10)


def camada_celulas(m: folium.Map, cel: pd.DataFrame, col_p="p_janela"):
    meio = PASSO_GRADE / 2
    for _, c in cel.iterrows():
        nivel = risk.classificar(c[col_p], "regiao")
        folium.Rectangle(
            bounds=[(c["lat"] - meio, c["lon"] - meio), (c["lat"] + meio, c["lon"] + meio)],
            color=risk.CORES[nivel], weight=0.5, fill=True,
            fill_opacity=0.08 + 0.12 * risk.ORDEM[nivel],
            tooltip=f"Região {c['celula']}<br>Chance de alagamento: {pct(c[col_p])}<br>"
                    f"Chuva prevista: {c['chuva_total_mm']:.1f} mm",
        ).add_to(m)


def camada_pontos(m: folium.Map, pts: pd.DataFrame, col_p="p_janela"):
    if col_p not in pts.columns:  # sem previsão (offline): só o histórico de cada ponto
        for _, p in pts.iterrows():
            folium.CircleMarker(
                location=(p["lat"], p["lon"]), radius=5, color="#333", weight=0.6, fill=True,
                fill_color="#8a8f98", fill_opacity=0.9,
                tooltip=(f"<b>{p['nome']}</b> — {p['bairro']}<br>"
                         f"Histórico: {p['n_eventos']} alagamentos desde {p['primeiro'][:4]}"),
            ).add_to(m)
        return
    for _, p in pts.sort_values(col_p).iterrows():
        nivel = risk.classificar(p[col_p])
        folium.CircleMarker(
            location=(p["lat"], p["lon"]), radius=4 + 3 * risk.ORDEM[nivel],
            color="#333", weight=0.6, fill=True, fill_color=risk.CORES[nivel], fill_opacity=0.9,
            tooltip=(f"<b>{p['nome']}</b> — {p['bairro']}<br>"
                     f"Chance de alagar: <b>{pct(p[col_p])}</b>"
                     + (f" ({risk.vezes_normal(p[col_p], p['p_normal'])})" if "p_normal" in p else "") + "<br>"
                     f"Pico previsto: {p['hora_pico']:%d/%m %Hh}<br>"
                     f"Histórico: {p['n_eventos']} alagamentos desde {p['primeiro'][:4]}"),
        ).add_to(m)


def camada_ao_vivo(m: folium.Map, hoje: pd.DataFrame):
    """Alagamentos registrados hoje pelo CGE: vermelho = ainda ativo, cinza = já terminou."""
    for _, a in hoje.dropna(subset=["lat", "lon"]).iterrows():
        status = "🔴 <b>Ativo agora</b>" if a["ativo"] else "Encerrado"
        horario = f"desde {a['inicio']}" if a["ativo"] else f"{a['inicio'] or '?'}–{a['fim'] or '?'}"
        folium.Marker(
            location=(a["lat"], a["lon"]),
            icon=folium.Icon(color="red" if a["ativo"] else "lightgray", icon="tint"),
            tooltip=(f"{status} ({horario}) — CGE hoje<br><b>{a['local']}</b> — {a['bairro']}"
                     + ("<br>Intransitável" if a["intransitavel"] else "")
                     + ("<br><i>local aproximado (centro do bairro)</i>" if a["precisao"] == "bairro" else "")),
        ).add_to(m)


def legenda(horas: int = 24):
    def faixas(escala):
        itens, ant = [], 0.0
        for lim, (_, n, c) in zip(risk.LIMIARES[escala], risk.NIVEIS_CFG):
            faixa = f"≥ {ant:.0%}" if lim == float("inf") else f"{ant:.0%}–{lim:.0%}"
            itens.append(f'<span class="badge" style="background:{c}">{faixa}</span>')
            ant = lim
        return " ".join(itens)

    st.markdown(f'<div class="muted">Chance de alagar nas próximas {horas}h · '
                f'<b>Pontos</b> (círculos): {faixas("ponto")}<br>'
                f'<b>Regiões</b> (~11 km, quadrados — chance de algum alagamento na área): {faixas("regiao")}</div>',
                unsafe_allow_html=True)


def grafico_chuva_risco(df: pd.DataFrame, agora: pd.Timestamp, altura=260):
    """Barras de chuva (mm/h) + linha de probabilidade de alagamento, com marcador de 'agora'."""
    base = alt.Chart(df).encode(x=alt.X("time:T", title=None, axis=alt.Axis(format="%d/%m %Hh")))
    dica = [alt.Tooltip("time:T", format="%d/%m %Hh", title="Hora"),
            alt.Tooltip("precip:Q", format=".1f", title="Chuva (mm/h)"),
            alt.Tooltip("p:Q", format=".1%", title="Prob. alagamento")]
    extras = [("umidade", ".0f", "Umidade (%)"), ("vento", ".0f", "Vento (km/h)"), ("rajada", ".0f", "Rajadas (km/h)")]
    dica += [alt.Tooltip(f"{c}:Q", format=f, title=t) for c, f, t in extras if c in df.columns]
    barras = base.mark_bar(color="#5b9bd5", opacity=0.8).encode(
        y=alt.Y("precip:Q", title="Chuva (mm/h)"), tooltip=dica)
    linha = base.mark_line(color="#c62828", strokeWidth=2.5).encode(
        y=alt.Y("p:Q", title="Prob. de alagamento (por hora)", axis=alt.Axis(format="%")))
    regra = alt.Chart(pd.DataFrame({"t": [agora]})).mark_rule(strokeDash=[4, 4], color="gray") \
        .encode(x="t:T")
    return alt.layer(barras, linha, regra).resolve_scale(y="independent").properties(height=altura)

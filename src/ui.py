"""Componentes visuais reutilizados pelas páginas."""
from __future__ import annotations

import altair as alt
import folium
import pandas as pd
import streamlit as st

from src import risk
from src.config import CENTRO_SP, PASSO_GRADE

AZUL = "#0E5FA8"      # cor principal (mesma do tema)
AGUA = "#5AA9E6"      # chuva nos gráficos
VERMELHO = "#D93025"  # probabilidade / destaque


def css():
    """Estilo dos componentes próprios. Usa cores com transparência para funcionar
    tanto no tema claro quanto no escuro (o Streamlit escolhe pelo aparelho)."""
    st.markdown("""
    <style>
      /* Fonte Inter. No Streamlit local ela vem do tema (config.toml); no stlite (web/APK) a fonte
         por URL no tema quebra a página, então é carregada aqui. Ícones (Material) ficam de fora. */
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
      .stApp :where(p, li, a, label, input, textarea, button, h1, h2, h3, h4, h5, h6, td, th, div, span):not([data-testid="stIconMaterial"]) {
        font-family: Inter, "Segoe UI", system-ui, sans-serif;}
      .block-container {padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1180px;}
      h2, h3 {letter-spacing: -.01em;}
      [data-testid="stMetricValue"] {font-size: 1.5rem; font-weight: 700;}
      .badge {display:inline-block; padding:.12rem .6rem; border-radius:999px; color:#fff;
              font-weight:600; font-size:.8rem;}
      .muted {opacity:.65; font-size:.85rem;}

      /* Cabeçalho da página */
      .ap-cab {margin: .2rem 0 1rem;}
      .ap-cab .ap-sobre {font-size:.78rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase;
                         color:#0E5FA8; opacity:.9;}
      .ap-cab .ap-t {font-size: clamp(1.55rem, 4.2vw, 2.25rem); font-weight:800; letter-spacing:-.025em;
                     line-height:1.15; margin:.15rem 0 0;}
      .ap-cab .ap-s {opacity:.65; font-size:.95rem; margin-top:.35rem; line-height:1.4;}

      /* Cartão principal de risco */
      .ap-hero {border-radius: 1.1rem; padding: 1.05rem 1.2rem; display:flex; gap:.95rem;
                align-items:flex-start; border:1px solid; margin:.2rem 0 1rem;}
      .ap-hero .ap-ic {font-size:2rem; line-height:1; margin-top:.15rem;}
      .ap-hero .ap-n {font-size:.75rem; font-weight:800; text-transform:uppercase; letter-spacing:.08em;}
      .ap-hero .ap-tt {font-size:1.22rem; font-weight:700; margin:.1rem 0 .3rem; line-height:1.3;}
      .ap-hero .ap-x {opacity:.85; font-size:.93rem; line-height:1.45;}

      /* Grade de indicadores */
      .ap-grade {display:grid; grid-template-columns: repeat(auto-fit, minmax(148px, 1fr)); gap:.65rem;
                 margin:.2rem 0 1.1rem;}
      .ap-bloco {border-radius:.95rem; padding:.8rem .95rem; background:rgba(127,127,127,.07);
                 border:1px solid rgba(127,127,127,.16);}
      .ap-bloco .ap-r {font-size:.78rem; opacity:.7; font-weight:500;}
      .ap-bloco .ap-v {font-size:1.4rem; font-weight:700; margin-top:.15rem; line-height:1.2;
                       letter-spacing:-.01em;}
      .ap-bloco .ap-d {font-size:.78rem; opacity:.65; margin-top:.2rem; line-height:1.3;}

      /* Alertas em lista (pontos de risco) */
      .alerta {border-left:5px solid; padding:.75rem 1rem; border-radius:.8rem;
               background:rgba(127,127,127,.07); margin-bottom:.55rem; line-height:1.45;}
      .alerta b {font-size:1rem;}
      .alerta span {font-size:.92rem; opacity:.9;}

      /* Mapas e tabelas com cantos arredondados */
      iframe {border-radius: 1rem;}
      [data-testid="stDataFrame"] {border-radius: .8rem; overflow: hidden;}
    </style>""", unsafe_allow_html=True)


def cabecalho(titulo: str, subtitulo: str = "", sobre: str = ""):
    """Título da página (substitui o st.title, grande demais no celular)."""
    st.markdown(f'<div class="ap-cab">{f"<div class=ap-sobre>{sobre}</div>" if sobre else ""}'
                f'<div class="ap-t">{titulo}</div>'
                f'{f"<div class=ap-s>{subtitulo}</div>" if subtitulo else ""}</div>',
                unsafe_allow_html=True)


def cartao_risco(nivel: str, titulo: str, texto: str, rotulo: str = "Risco de alagamento"):
    """Cartão grande no topo: nível de risco com a cor do nível."""
    cor = risk.CORES[nivel]
    st.markdown(f'<div class="ap-hero" style="background:{cor}17;border-color:{cor}55">'
                f'<div class="ap-ic">{risk.EMOJI[nivel]}</div><div>'
                f'<div class="ap-n" style="color:{cor}">{rotulo} · {nivel}</div>'
                f'<div class="ap-tt">{titulo}</div><div class="ap-x">{texto}</div></div></div>',
                unsafe_allow_html=True)


def blocos(itens: list[tuple]):
    """Grade de indicadores: [(rótulo, valor, detalhe), ...]. Vira 2 colunas no celular."""
    html = "".join(f'<div class="ap-bloco"><div class="ap-r">{r}</div><div class="ap-v">{v}</div>'
                   f'{f"<div class=ap-d>{d}</div>" if d else ""}</div>' for r, v, *resto in itens
                   for d in [resto[0] if resto else ""])
    st.markdown(f'<div class="ap-grade">{html}</div>', unsafe_allow_html=True)


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
    m = folium.Map(location=center, zoom_start=zoom, tiles="OpenStreetMap", control_scale=True)
    # Fundo claro e discreto (OpenStreetMap em tons de cinza): os pontos de risco se destacam.
    # Os pedaços de mapa continuam os do OSM, que o app guarda para usar sem internet.
    m.get_root().header.add_child(folium.Element(
        "<style>.leaflet-tile-pane{filter:grayscale(.9) brightness(1.04) contrast(.92)}"
        ".leaflet-container{background:#eef1f5;font-family:Inter,'Segoe UI',sans-serif}</style>"))
    return m


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
                location=(p["lat"], p["lon"]), radius=6, color="#ffffff", weight=1.5, fill=True,
                fill_color="#7b8794", fill_opacity=0.95,
                tooltip=(f"<b>{p['nome']}</b> — {p['bairro']}<br>"
                         f"Histórico: {p['n_eventos']} alagamentos desde {p['primeiro'][:4]}"),
            ).add_to(m)
        return
    for _, p in pts.sort_values(col_p).iterrows():
        nivel = risk.classificar(p[col_p])
        folium.CircleMarker(
            location=(p["lat"], p["lon"]), radius=5 + 3 * risk.ORDEM[nivel],
            color="#ffffff", weight=1.5, fill=True, fill_color=risk.CORES[nivel], fill_opacity=0.95,
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
    barras = base.mark_bar(color=AGUA, opacity=0.85, cornerRadiusTopLeft=2, cornerRadiusTopRight=2).encode(
        y=alt.Y("precip:Q", title="Chuva (mm/h)"), tooltip=dica)
    linha = base.mark_line(color=VERMELHO, strokeWidth=2.5, interpolate="monotone").encode(
        y=alt.Y("p:Q", title="Prob. de alagamento (por hora)", axis=alt.Axis(format="%")))
    regra = alt.Chart(pd.DataFrame({"t": [agora]})).mark_rule(strokeDash=[4, 4], color="#8a94a6") \
        .encode(x="t:T")
    return alt.layer(barras, linha, regra).resolve_scale(y="independent").properties(height=altura)

import base64
import sys

import altair as alt
import pandas as pd
import streamlit as st
from folium.plugins import HeatMap

from src import servico, ui
from src.nomes import expandir

ui.cabecalho("Análise histórica dos alagamentos", "O que os registros do CGE mostram: quando, onde e "
             "com quanta chuva a cidade alaga.", sobre="Dados")
ev = servico.eventos().copy()
ev["dt"] = pd.to_datetime(ev["data"])
ev["ano"] = ev["dt"].dt.year
ev["mes"] = ev["dt"].dt.month
ev["hora"] = pd.to_numeric(ev["inicio"].str[:2], errors="coerce")
dia = servico.diario()
ini, fim = ev["dt"].min(), ev["dt"].max()
st.caption(f"Registros oficiais do CGE de {ini:%d/%m/%Y} a {fim:%d/%m/%Y}.")

anos = sorted(ev["ano"].unique())
sel = st.select_slider("Período", anos, value=(anos[0], anos[-1]))
ev = ev[ev["ano"].between(*sel)]

a, b, c, d = st.columns(4)
a.metric("Alagamentos registrados", f"{len(ev):,}".replace(",", "."))
b.metric("Dias com alagamento", f"{ev['data'].nunique():,}".replace(",", "."))
c.metric("Ficaram intransitáveis", ui.pct(ev["intransitavel"].mean()))
dur = (pd.to_datetime(ev["data"] + " " + ev["fim"].fillna(""), errors="coerce")
       - pd.to_datetime(ev["data"] + " " + ev["inicio"], errors="coerce")).dt.total_seconds() / 60
d.metric("Duração mediana", f"{dur[dur >= 0].median():.0f} min")

MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

# ------------------------------------------------ quando acontece
st.subheader("Quando os alagamentos acontecem")
c1, c2 = st.columns(2)
with c1:
    st.markdown("**Sazonalidade:** concentração no verão")
    n_anos = ev.groupby("mes")["ano"].nunique().clip(lower=1)
    m = (ev.groupby("mes").size() / n_anos).reindex(range(1, 13), fill_value=0).reset_index(name="n")
    m["Mês"] = m["mes"].map(lambda x: MESES[x - 1])
    st.altair_chart(alt.Chart(m).mark_bar(color=ui.AZUL).encode(
        x=alt.X("Mês:N", sort=MESES, title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("n:Q", title="Média por mês", axis=alt.Axis(format="d")),
        tooltip=["Mês", alt.Tooltip("n:Q", format=".1f", title="Média")]
    ).properties(height=260), width="stretch")
with c2:
    st.markdown("**Hora do dia:** pico no fim da tarde (chuvas convectivas)")
    h = ev.dropna(subset=["hora"]).groupby("hora").size().reindex(range(24), fill_value=0).reset_index(name="n")
    st.altair_chart(alt.Chart(h).mark_bar(color=ui.VERMELHO).encode(
        x=alt.X("hora:O", title="Hora de início", axis=alt.Axis(labelAngle=0)),
        y=alt.Y("n:Q", title="Alagamentos", axis=alt.Axis(format="d")),
        tooltip=["hora", "n"]
    ).properties(height=260), width="stretch")

c1, c2 = st.columns(2)
with c1:
    st.markdown("**Alagamentos por ano**")
    y = ev.groupby("ano").size().reset_index(name="n")
    st.altair_chart(alt.Chart(y).mark_bar(color=ui.AZUL).encode(
        x=alt.X("ano:O", title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("n:Q", title="Alagamentos", axis=alt.Axis(format="d")), tooltip=["ano", "n"]
    ).properties(height=240), width="stretch")
with c2:
    st.markdown("**Por zona da cidade**")
    z = ev.groupby("zona").size().reset_index(name="n").sort_values("n", ascending=False)
    st.altair_chart(alt.Chart(z).mark_bar(color=ui.AZUL).encode(
        y=alt.Y("zona:N", sort="-x", title=None),
        x=alt.X("n:Q", title="Alagamentos", axis=alt.Axis(format="d")), tooltip=["zona", "n"]
    ).properties(height=240), width="stretch")

# ------------------------------------------------ chuva x alagamento
st.subheader("Quanto de chuva causa alagamento?")
dd = dia[pd.to_datetime(dia["data"]).dt.year.between(*sel)].dropna(subset=["chuva_max_celula_mm"])
if len(dd):
    faixas = [0, 1, 5, 10, 20, 30, 50, 80, 1000]
    rot = ["< 1", "1–5", "5–10", "10–20", "20–30", "30–50", "50–80", "> 80"]
    dd = dd.assign(faixa=pd.cut(dd["chuva_max_celula_mm"], faixas, labels=rot, right=False))
    g = dd.groupby("faixa", observed=False).agg(
        dias=("alagamentos", "size"), com_alag=("alagamentos", lambda s: (s > 0).mean()),
        media=("alagamentos", "mean")).reset_index()
    c1, c2 = st.columns([3, 2])
    with c1:
        st.altair_chart(alt.Chart(g).mark_bar(color=ui.VERMELHO).encode(
            x=alt.X("faixa:N", sort=rot, title="Chuva no dia, na região mais chuvosa da cidade (mm)",
                    axis=alt.Axis(labelAngle=0)),
            y=alt.Y("com_alag:Q", title="Dias com pelo menos 1 alagamento", axis=alt.Axis(format="%")),
            tooltip=[alt.Tooltip("faixa:N", title="Chuva (mm)"), alt.Tooltip("dias:Q", title="Nº de dias"),
                     alt.Tooltip("com_alag:Q", format=".0%", title="Com alagamento"),
                     alt.Tooltip("media:Q", format=".1f", title="Média de alagamentos")]
        ).properties(height=300), width="stretch")
    with c2:
        st.markdown("""
**Como ler:** cada barra agrupa os dias pela chuva acumulada na região mais chuvosa da cidade.
A chance de haver alagamento cresce rapidamente com a chuva. É essa relação que o
modelo aprende, só que hora a hora e região por região.

A chuva vem das **previsões arquivadas** do Open-Meteo, a mesma fonte que o app usa ao vivo.
""")
        st.dataframe(g.rename(columns={"faixa": "Chuva (mm)", "dias": "Dias", "com_alag": "% com alag.",
                                       "media": "Média alag."}), hide_index=True, width="stretch",
                     column_config={"% com alag.": st.column_config.NumberColumn(format="percent"),
                                    "Média alag.": st.column_config.NumberColumn(format="%.1f")})

# ------------------------------------------------ tendência
st.subheader("A cidade está alagando menos com a mesma chuva?")
tend = dia.assign(ano=dia["data"].str[:4]).groupby("ano").agg(
    alag=("alagamentos", "sum"), chuva=("chuva_media_mm", "sum")).reset_index()
tend["por_100mm"] = tend["alag"] / tend["chuva"] * 100
c1, c2 = st.columns([3, 2])
with c1:
    st.altair_chart(alt.Chart(tend).mark_bar(color=ui.AZUL).encode(
        x=alt.X("ano:O", title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("por_100mm:Q", title="Alagamentos por 100 mm de chuva"),
        tooltip=[alt.Tooltip("ano:O", title="Ano"), alt.Tooltip("alag:Q", title="Alagamentos"),
                 alt.Tooltip("chuva:Q", format=".0f", title="Chuva média (mm)"),
                 alt.Tooltip("por_100mm:Q", format=".1f", title="Por 100 mm")]
    ).properties(height=260), width="stretch")
with c2:
    a0, a1 = tend.iloc[0], tend.iloc[-1]
    st.markdown(f"""
Em **{a0['ano']}** foram **{a0['por_100mm']:.0f}** alagamentos registrados para cada 100 mm de chuva.
Em **{a1['ano']}** foram **{a1['por_100mm']:.0f}**.

Possíveis explicações: obras de drenagem (piscinões, galerias), mudanças na forma de o CGE
registrar ou na distribuição da chuva entre os bairros. Os dados não permitem separar essas causas.

**Consequência para o modelo:** anos recentes têm mais peso no treino, e as probabilidades são
recalibradas para a taxa dos últimos 12 meses (veja *Como o modelo funciona*).
""")

# ------------------------------------------------ onde
st.subheader("Onde mais alaga")
c1, c2 = st.columns([3, 2])
with c1:
    m = ui.mapa(zoom=11)
    HeatMap(ev[["lat", "lon"]].values.tolist(), radius=12, blur=15, min_opacity=0.3).add_to(m)
    ui.mostrar_mapa(m, 460)
    st.caption("Mapa de calor dos alagamentos registrados. Eventos sem endereço preciso ficam no centro do bairro.")
with c2:
    top = (ev.assign(nome=ev["local_n"].map(expandir)).groupby(["nome", "bairro"]).size()
           .sort_values(ascending=False).head(15).reset_index(name="Alagamentos"))
    st.dataframe(top.rename(columns={"nome": "Local", "bairro": "Bairro"}), hide_index=True,
                 width="stretch", height=460)

csv = ev.drop(columns=["dt"]).to_csv(index=False).encode("utf-8-sig")
if sys.platform == "emscripten":
    # No navegador (GitHub Pages/stlite) o st.download_button não funciona: usa link com os dados embutidos
    b64 = base64.b64encode(csv).decode()
    st.markdown(f'<a href="data:text/csv;base64,{b64}" download="alagamentos_sp_cge.csv">'
                "⬇️ Baixar dados (CSV)</a>", unsafe_allow_html=True)
else:
    st.download_button("⬇️ Baixar dados (CSV)", csv, "alagamentos_sp_cge.csv", "text/csv")

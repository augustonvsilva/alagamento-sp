import pandas as pd
import streamlit as st

from src import risk, servico, ui

ui.aviso_simulacao()
try:
    prev = servico.previsao(st.session_state.get("sim"))
except Exception:  # noqa: BLE001
    st.error(ui.SEM_INTERNET, icon="📶")
    st.stop()
ui.aviso_offline(servico.previsao_salva_em(), prev.agora, prev.cel_h["time"].max())

pts, cel = prev.pts, prev.cel
st.title("Previsão de alagamentos — São Paulo")
st.caption(f"Próximas 24 horas a partir de {prev.agora:%d/%m/%Y %Hh}. "
           f"{len(pts)} pontos com histórico recorrente de alagamento monitorados.")

# ------------------------------------------------ indicadores
p_cidade = risk.prob_alguma(cel["p_janela"])
fut = risk.janela(prev.cel_h, prev.agora, 24)
n_alto = int((pts["nivel"].map(risk.ORDEM) >= risk.ORDEM["Alto"]).sum())
c1, c2, c3, c4 = st.columns(4)
c1.metric("Chance de alagar em SP", ui.pct(p_cidade),
          help="Chance de pelo menos um alagamento em algum lugar da cidade nas próximas 24h")
c2.metric("Pontos em risco alto ou muito alto", n_alto)
c3.metric("Maior chuva prevista em 1h", f"{fut['precip'].max():.1f} mm")
c4.metric("Chuva média prevista em 24h", f"{fut.groupby('celula')['precip'].sum().mean():.1f} mm")

# ------------------------------------------------ alertas
top = pts.sort_values("p_janela", ascending=False)
criticos = top[top["nivel"].map(risk.ORDEM) >= risk.ORDEM["Moderado"]].head(5)
if criticos.empty:
    ui.alerta("Sem alertas relevantes", "Nenhum ponto monitorado com risco moderado ou maior nas "
              "próximas 24 horas.", "Baixo")
else:
    for _, p in criticos.iterrows():
        ui.alerta(f"{p['nome']} — {p['bairro']}",
                  f"Chance de alagar: <b>{ui.pct(p['p_janela'])}</b> · pico previsto às "
                  f"{p['hora_pico']:%Hh} de {p['hora_pico']:%d/%m} · "
                  f"{p['n_eventos']} alagamentos registrados desde {p['primeiro'][:4]}", p["nivel"])

# ------------------------------------------------ mapa + ranking
st.subheader("Mapa de risco")
horas = st.segmented_control("Janela", [3, 6, 12, 24], default=24,
                             format_func=lambda h: f"Próximas {h}h") or 24
pts_mapa = pts.drop(columns=["p_janela", "hora_pico"]).merge(
    risk.resumo(prev.pts_h, "ponto", prev.agora, horas)[["p_janela", "hora_pico"]],
    left_on="ponto", right_index=True)
cel_mapa = cel.drop(columns=["p_janela"]).merge(
    risk.resumo(prev.cel_h, "celula", prev.agora, horas)[["p_janela"]],
    left_on="celula", right_index=True)
m = ui.mapa()
ui.camada_celulas(m, cel_mapa)
ui.camada_pontos(m, pts_mapa)
ui.mostrar_mapa(m, 560)
ui.legenda(horas)

st.subheader("Ranking de risco")
filtro = st.multiselect("Zona", sorted(pts["zona"].dropna().unique()), placeholder="Todas as zonas")
t = top[top["zona"].isin(filtro)] if filtro else top
st.dataframe(
    t[["nome", "bairro", "zona", "p_janela", "hora_pico", "n_eventos", "frac_intransitavel"]],
    hide_index=True, height=420, width="stretch",
    column_config={
        "nome": "Local", "bairro": "Bairro", "zona": "Zona",
        "p_janela": st.column_config.ProgressColumn("Chance 24h", format="percent", min_value=0, max_value=1),
        "hora_pico": st.column_config.DatetimeColumn("Pico", format="DD/MM HH[h]"),
        "n_eventos": st.column_config.NumberColumn("Histórico", help="Alagamentos registrados pelo CGE"),
        "frac_intransitavel": st.column_config.NumberColumn("Já ficou intransitável", format="percent"),
    })

# ------------------------------------------------ detalhe de um ponto
st.subheader("Previsão hora a hora")
escolha = st.selectbox("Escolha um local", top["nome"] + " — " + top["bairro"])
ponto = top.iloc[(top["nome"] + " — " + top["bairro"]).tolist().index(escolha)]
serie = prev.pts_h[(prev.pts_h["ponto"] == ponto["ponto"])
                   & (prev.pts_h["time"] >= prev.agora - pd.Timedelta(hours=12))
                   & (prev.pts_h["time"] < prev.agora + pd.Timedelta(hours=48))]
st.altair_chart(ui.grafico_chuva_risco(serie, prev.agora), width="stretch")
a, b, c, d = st.columns(4)
a.metric("Chance de alagar (24h)", ui.pct(ponto["p_janela"]))
b.metric("Alagamentos registrados", int(ponto["n_eventos"]))
c.metric("Já ficou intransitável", ui.pct(ponto["frac_intransitavel"]), help="Fração dos eventos")
d.metric("Duração média", f"{ponto['duracao_media_min']:.0f} min" if pd.notna(ponto["duracao_media_min"]) else "—")

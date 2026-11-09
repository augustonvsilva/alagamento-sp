import pandas as pd
import streamlit as st

from src import ao_vivo, risk, servico, ui

ui.cabecalho("Alagamentos em São Paulo", "Previsão para as próximas 24 horas, a partir da chuva prevista e "
             "do histórico do CGE.", sobre="Visão geral")
ui.aviso_simulacao()
try:
    prev = servico.previsao(st.session_state.get("sim"))
except Exception:  # noqa: BLE001
    st.error(ui.SEM_INTERNET, icon="📶")
    st.stop()
ui.aviso_offline(servico.previsao_salva_em(), prev.agora, prev.cel_h["time"].max())

pts, cel = prev.pts, prev.cel
hoje = servico.alagamentos_hoje()

# ------------------------------------------------ situação da cidade
p_cidade = risk.prob_alguma(cel["p_janela"])
fut = risk.janela(prev.cel_h, prev.agora, 24)
n_alto = int((pts["nivel"].map(risk.ORDEM) >= risk.ORDEM["Alto"]).sum())
n_mod = int((pts["nivel"] == "Moderado").sum())
nivel_cidade = risk.pior(pts["nivel"])
if n_alto:
    titulo = f"{n_alto} ponto(s) com risco alto de alagar nas próximas 24h"
elif n_mod:
    titulo = f"{n_mod} ponto(s) com risco moderado nas próximas 24h"
else:
    titulo = "Nenhum ponto com risco relevante nas próximas 24h"
ui.cartao_risco(nivel_cidade, titulo,
                f"Chance de algum alagamento em algum lugar da cidade: <b>{ui.pct(p_cidade)}</b>. "
                f"{len(pts)} pontos com histórico de alagamento monitorados · previsão a partir de "
                f"{prev.agora:%d/%m %Hh}.", rotulo="Cidade")

n_hoje = "—" if hoje is None else str(len(hoje[0]))
ativos_hoje = 0 if hoje is None else int(hoje[0]["ativo"].sum()) if len(hoje[0]) else 0
ui.blocos([
    ("Chance de alagar em SP", ui.pct(p_cidade), "próximas 24h"),
    ("Pontos em risco alto", str(n_alto), f"{n_mod} em risco moderado"),
    ("Maior chuva em 1h", f"{fut['precip'].max():.1f} mm", "prevista nas próximas 24h"),
    ("Chuva média em 24h", f"{fut.groupby('celula')['precip'].sum().mean():.1f} mm", "média das regiões"),
    ("Alagamentos hoje", n_hoje, (f"{ativos_hoje} ativo(s) agora" if ativos_hoje else "nenhum ativo agora")
     if hoje is not None else "CGE indisponível"),
])

# ------------------------------------------------ alertas
top = pts.sort_values("p_janela", ascending=False)
criticos = top[top["nivel"].map(risk.ORDEM) >= risk.ORDEM["Moderado"]].head(5)
if len(criticos):
    st.subheader("Pontos com mais risco")
    for _, p in criticos.iterrows():
        ui.alerta(f"{p['nome']} — {p['bairro']}",
                  f"Chance de alagar: <b>{ui.pct(p['p_janela'])}</b> "
                  f"({risk.vezes_normal(p['p_janela'], p['p_normal'])}) · pico previsto às "
                  f"{p['hora_pico']:%Hh} de {p['hora_pico']:%d/%m} · "
                  f"{p['n_eventos']} alagamentos registrados desde {p['primeiro'][:4]}", p["nivel"])

# ------------------------------------------------ alagamentos de hoje (CGE, ao vivo)
st.subheader("Alagamentos hoje (CGE, ao vivo)")
if hoje is None:
    st.caption("Não foi possível consultar os alagamentos de hoje no CGE agora.")
else:
    hoje, info = hoje
    st.markdown(ao_vivo.resumo_texto(hoje) + f" Atualizado às {ao_vivo.hora_atualizacao(info)} · fonte: {info['fonte']}.")
    if len(hoje):
        # Previsto x ocorrido: o que o modelo dizia para os pontos que alagaram hoje
        comp = hoje.merge(pts[["ponto", "p_janela", "nivel", "p_normal"]], on="ponto", how="left")
        comp["Risco previsto"] = [f"{risk.EMOJI[n]} {n} ({ui.pct(p)})" if isinstance(n, str) else "ponto novo / fora da lista"
                                  for n, p in zip(comp["nivel"], comp["p_janela"])]
        comp["Status"] = comp["ativo"].map({True: "🔴 Ativo", False: "Encerrado"})
        comp["Horário"] = comp["inicio"].fillna("?") + "–" + comp["fim"].fillna("")
        st.dataframe(comp[["Status", "local", "bairro", "Horário", "Risco previsto"]].rename(
            columns={"local": "Local", "bairro": "Bairro"}), hide_index=True, width="stretch")
        st.caption("\"Risco previsto\" é a chance que o app calcula agora para o ponto monitorado no "
                   "mesmo endereço — serve para comparar o que o modelo indica com o que de fato aconteceu.")

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
if hoje is not None and len(hoje):
    ui.camada_ao_vivo(m, hoje)
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
st.subheader("Previsão hora a hora de um local")
escolha = st.selectbox("Escolha um local", top["nome"] + " — " + top["bairro"])
ponto = top.iloc[(top["nome"] + " — " + top["bairro"]).tolist().index(escolha)]
serie = prev.pts_h[(prev.pts_h["ponto"] == ponto["ponto"])
                   & (prev.pts_h["time"] >= prev.agora - pd.Timedelta(hours=12))
                   & (prev.pts_h["time"] < prev.agora + pd.Timedelta(hours=48))]
st.altair_chart(ui.grafico_chuva_risco(serie, prev.agora), width="stretch")
ui.blocos([
    ("Chance de alagar (24h)", ui.pct(ponto["p_janela"]), risk.vezes_normal(ponto["p_janela"], ponto["p_normal"])),
    ("Alagamentos registrados", str(int(ponto["n_eventos"])), f"desde {ponto['primeiro'][:4]}"),
    ("Já ficou intransitável", ui.pct(ponto["frac_intransitavel"]), "dos alagamentos"),
    ("Duração média", f"{ponto['duracao_media_min']:.0f} min" if pd.notna(ponto["duracao_media_min"]) else "—", ""),
])

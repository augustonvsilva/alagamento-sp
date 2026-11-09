import altair as alt
import folium
import pandas as pd
import streamlit as st

from src import risk, servico, ui

ui.aviso_simulacao()
st.title("Trajeto seguro")
st.caption("Compara as rotas possíveis e mostra a chance de passar por um ponto alagado — "
           "e qual o melhor horário para sair.")

with st.form("form_rota"):
    c1, c2 = st.columns(2)
    origem_txt = c1.text_input("Origem", "Avenida Paulista, 1000, São Paulo")
    destino_txt = c2.text_input("Destino", "Shopping Aricanduva, São Paulo")
    buffer_m = st.slider("Considerar pontos de alagamento a até (metros) do trajeto", 50, 500, 150, 25)
    enviar = st.form_submit_button("Calcular trajeto", type="primary", width="stretch")

if enviar:
    try:
        o, d = servico.geocode(origem_txt), servico.geocode(destino_txt)
    except Exception:  # noqa: BLE001
        st.error("Sem internet não dá para buscar endereços nem calcular rotas. Tente de novo com conexão.",
                 icon="📴")
        st.stop()
    if not o or not d:
        st.session_state.pop("rota", None)
        st.error("Não encontrei a " + ("origem." if not o else "o destino."))
    else:
        try:
            st.session_state["rota"] = (o, d, servico.rotas(o[:2], d[:2]))
        except Exception as e:  # noqa: BLE001
            st.error(f"Não foi possível calcular a rota agora. ({e})")

if "rota" not in st.session_state:
    st.stop()

o, d, rts = st.session_state["rota"]
if not rts:
    st.error("Nenhuma rota encontrada entre esses pontos.")
    st.stop()

try:
    prev = servico.previsao(st.session_state.get("sim"))
except Exception:  # noqa: BLE001
    st.error(ui.SEM_INTERNET, icon="📶")
    st.stop()
ui.aviso_offline(servico.previsao_salva_em(), prev.agora, prev.cel_h["time"].max())


def risco_saida(ids, dur_min, horas=12):
    """Para cada horário de saída nas próximas `horas`, chance de encontrar algum ponto alagado."""
    ph = prev.pts_h[prev.pts_h["ponto"].isin(ids)]
    n = max(1, int(round(dur_min / 60)))  # horas que a viagem ocupa
    linhas = []
    for k in range(horas):
        t0 = prev.agora + pd.Timedelta(hours=k)
        w = ph[(ph["time"] >= t0) & (ph["time"] < t0 + pd.Timedelta(hours=n))]
        linhas.append({"saida": t0, "p": risk.prob_alguma(w.groupby("ponto")["p"].max())})
    return pd.DataFrame(linhas)


linhas = []
for k, rt in enumerate(rts):
    no_cam = servico.pontos_no_caminho(rt["path"], prev.pts, buffer_m)
    saida = risco_saida(no_cam["ponto"], rt["dur_min"])
    linhas.append({"k": k, "Rota": f"Opção {k + 1}", "dist": rt["dist_km"], "dur": rt["dur_min"],
                   "n_pontos": len(no_cam), "p_agora": saida["p"].iloc[0], "saida": saida,
                   "ids": list(no_cam["ponto"])})
tab = pd.DataFrame(linhas)
# Recomenda a de menor risco; empate (diferença < 2 p.p.) -> a mais rápida
tab["_ordem"] = (tab["p_agora"] / 0.02).round()
melhor = tab.sort_values(["_ordem", "dur"]).iloc[0]
nivel = risk.classificar(melhor["p_agora"])

ui.alerta(f"Recomendado: {melhor['Rota']} — {melhor['dist']:.1f} km, ~{melhor['dur']:.0f} min",
          f"Chance de encontrar um ponto alagado saindo agora: <b>{ui.pct(melhor['p_agora'])}</b> · "
          f"{melhor['n_pontos']} ponto(s) de alagamento recorrente(s) no caminho.", nivel)

st.dataframe(tab[["Rota", "dist", "dur", "n_pontos", "p_agora"]], hide_index=True, width="stretch",
             column_config={"dist": st.column_config.NumberColumn("Distância", format="%.1f km"),
                            "dur": st.column_config.NumberColumn("Tempo", format="%.0f min"),
                            "n_pontos": "Pontos de alagamento no caminho",
                            "p_agora": st.column_config.ProgressColumn("Risco saindo agora", format="percent",
                                                                       min_value=0, max_value=1)})

col_m, col_s = st.columns([3, 2], gap="medium")
with col_m:
    m = ui.mapa(o[:2], 12)
    cores = ["#1565c0", "#6a1b9a", "#00838f"]
    for _, r in tab.sort_values("k", ascending=False).iterrows():
        e_melhor = r["k"] == melhor["k"]
        folium.PolyLine(rts[r["k"]]["path"].tolist(), color=cores[r["k"] % 3],
                        weight=7 if e_melhor else 4, opacity=0.9 if e_melhor else 0.45,
                        tooltip=f"{r['Rota']}: {r['dist']:.1f} km, {r['dur']:.0f} min").add_to(m)
    folium.Marker(o[:2], tooltip="Origem", icon=folium.Icon(color="green", icon="play")).add_to(m)
    folium.Marker(d[:2], tooltip="Destino", icon=folium.Icon(color="red", icon="flag")).add_to(m)
    ids = sorted({i for l in tab["ids"] for i in l})
    ui.camada_pontos(m, prev.pts[prev.pts["ponto"].isin(ids)])
    m.fit_bounds([o[:2], d[:2]], padding=(30, 30))
    ui.mostrar_mapa(m, 480)

with col_s:
    st.markdown(f"**Melhor horário para sair — {melhor['Rota']}**")
    s = melhor["saida"]
    if s["p"].max() < 0.005:
        st.success("Risco desprezível em qualquer horário das próximas 12 horas.")
    else:
        h = s.loc[s["p"].idxmin()]
        graf = alt.Chart(s).mark_bar(color=ui.AZUL).encode(
            x=alt.X("saida:T", title="Horário de saída", axis=alt.Axis(format="%Hh")),
            y=alt.Y("p:Q", title="Chance de pegar alagamento", axis=alt.Axis(format="%")),
            tooltip=[alt.Tooltip("saida:T", format="%d/%m %Hh", title="Saída"),
                     alt.Tooltip("p:Q", format=".1%", title="Risco")]).properties(height=260)
        st.altair_chart(graf, width="stretch")
        if h["saida"] == prev.agora:
            st.info("Agora é o melhor momento para sair nas próximas 12 horas.")
        else:
            st.info(f"Saindo às **{h['saida']:%Hh}** o risco cai para **{ui.pct(h['p'])}** "
                    f"(agora: {ui.pct(s['p'].iloc[0])}).")

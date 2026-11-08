import folium
import pandas as pd
import streamlit as st

from src import geo, risk, servico, ui
from src.config import BBOX

ui.aviso_simulacao()
st.title("Como está a sua região")

USAR_GPS, USAR_END = "📍 Minha localização", "🔎 Buscar endereço"
minha = st.session_state.get("minha_loc")
dentro_sp = minha is not None and (BBOX["lat_min"] <= minha[0] <= BBOX["lat_max"]
                                   and BBOX["lon_min"] <= minha[1] <= BBOX["lon_max"])
if minha is not None and not dentro_sp:
    st.info("Sua localização parece estar fora da cidade de São Paulo — a previsão cobre só a "
            "capital. Busque um endereço em SP abaixo.")

c1, c2 = st.columns([3, 1])
modo = USAR_END
if dentro_sp:
    modo = c1.radio("Local", [USAR_GPS, USAR_END], horizontal=True, label_visibility="collapsed")
raio = c2.select_slider("Raio", [0.5, 1, 2, 3, 5], value=2, format_func=lambda r: f"{r} km")

if modo == USAR_GPS:
    lat, lon = minha
    nome_end = servico.endereco_de(lat, lon)
else:
    end = c1.text_input("Endereço, bairro ou ponto de referência", "Praça da Sé, São Paulo",
                        placeholder="Ex.: Rua Augusta, 500")
    loc = servico.geocode(end) if end.strip() else None
    if not loc:
        st.info("Não encontrei esse endereço. Tente incluir o bairro ou o número.")
        st.stop()
    lat, lon, nome_end = loc
st.caption(f"📍 {nome_end}")

sim = st.session_state.get("sim")
try:
    prev = servico.previsao(sim)
    atual = servico.tempo_atual(lat, lon)
    local = servico.previsao_local(lat, lon, sim)
except Exception as e:  # noqa: BLE001
    st.error(f"Não foi possível consultar o tempo agora. ({e})")
    st.stop()

prox24 = risk.janela(local, prev.agora, 24)
p_regiao = risk.prob_alguma(prox24["p"])

pts = prev.pts.copy()
pts["dist_km"] = geo.haversine_m(lat, lon, pts["lat"].values, pts["lon"].values) / 1000
perto = pts[pts["dist_km"] <= raio].sort_values("p_janela", ascending=False)
p_perto = risk.prob_alguma(perto["p_janela"])
nivel = risk.pior([risk.classificar(p_perto), risk.classificar(p_regiao, "regiao")])

# ------------------------------------------------ situação
ui.alerta(
    f"Risco {nivel.lower()} de alagamento perto de você nas próximas 24h",
    (f"{len(perto)} ponto(s) recorrente(s) de alagamento a até {raio} km · chance de algum alagar: "
     f"<b>{ui.pct(p_perto)}</b>") if len(perto) else
    f"Nenhum ponto recorrente de alagamento a até {raio} km.", nivel)

a, b, c = st.columns(3)
a.metric("Agora", atual["descricao"], f"{atual['temperature_2m']:.0f} °C · sensação de "
         f"{atual.get('apparent_temperature', atual['temperature_2m']):.0f} °C",
         delta_color="off", delta_arrow="off")
b.metric("Umidade do ar", f"{atual['relative_humidity_2m']:.0f}%",
         "ar muito seco" if atual["relative_humidity_2m"] < 30 else None, delta_color="off", delta_arrow="off")
rajada = atual.get("wind_gusts_10m") or 0
c.metric("Vento", f"{atual['wind_speed_10m']:.0f} km/h {atual.get('direcao', '')}".strip(),
         f"rajadas de {rajada:.0f} km/h", delta_color="off", delta_arrow="off")

rajada_max = prox24["rajada"].max() if "rajada" in prox24 else float("nan")
if rajada_max >= 60:
    st.warning(f"💨 Rajadas de até **{rajada_max:.0f} km/h** previstas nas próximas 24h — risco de queda de "
               "árvores e de falta de energia. Evite ficar sob árvores e perto de fiação durante a chuva.")

b, c, d = st.columns(3)
b.metric("Chuva agora", f"{atual['precipitation']:.1f} mm")
c.metric("Chuva prevista (24h)", f"{prox24['precip'].sum():.1f} mm",
         f"pico de {prox24['precip'].max():.1f} mm/h", delta_color="off", delta_arrow="off")
pico = prox24.loc[prox24["precip"].idxmax(), "time"] if prox24["precip"].max() > 0 else None
d.metric("Horário de mais chuva", f"{pico:%Hh} ({pico:%d/%m})" if pico is not None else "Sem chuva")

# ------------------------------------------------ mapa e previsão
col_m, col_g = st.columns([3, 2], gap="medium")
with col_m:
    m = ui.mapa((lat, lon), 14 if raio <= 1 else 13)
    folium.Marker((lat, lon), tooltip="Você está aqui", icon=folium.Icon(color="blue", icon="home")).add_to(m)
    folium.Circle((lat, lon), radius=raio * 1000, color=ui.AZUL, fill=False, weight=1.5).add_to(m)
    ui.camada_pontos(m, perto)
    ui.mostrar_mapa(m, 460)
with col_g:
    st.markdown("**Previsão para a sua região**")
    serie = local[(local["time"] >= prev.agora - pd.Timedelta(hours=6))
                  & (local["time"] < prev.agora + pd.Timedelta(hours=36))]
    st.altair_chart(ui.grafico_chuva_risco(serie, prev.agora, 300), width="stretch")
    st.caption("Barras: chuva prevista. Linha: probabilidade de alagamento na região (~11 km) a cada hora.")

# ------------------------------------------------ pontos próximos e histórico
st.subheader(f"Pontos de alagamento a até {raio} km")
if perto.empty:
    st.write("Nenhum ponto recorrente registrado pelo CGE nesse raio.")
else:
    st.dataframe(perto[["nome", "bairro", "dist_km", "p_janela", "hora_pico", "n_eventos", "ultimo"]],
                 hide_index=True, width="stretch",
                 column_config={
                     "nome": "Local", "bairro": "Bairro",
                     "dist_km": st.column_config.NumberColumn("Distância", format="%.1f km"),
                     "p_janela": st.column_config.ProgressColumn("Chance 24h", format="percent",
                                                                 min_value=0, max_value=1),
                     "hora_pico": st.column_config.DatetimeColumn("Pico", format="DD/MM HH[h]"),
                     "n_eventos": "Alagamentos (histórico)", "ultimo": "Último registro"})

hist = servico.historico_proximo(lat, lon, raio)
st.subheader("Histórico da região")
if hist.empty:
    st.write("O CGE não registrou alagamentos nesse raio no período coletado.")
else:
    h1, h2, h3 = st.columns(3)
    h1.metric("Alagamentos registrados", len(hist), help="Desde o início da série coletada")
    h2.metric("Último registro", pd.to_datetime(hist["data"]).max().strftime("%d/%m/%Y"))
    h3.metric("Ficaram intransitáveis", ui.pct(hist["intransitavel"].mean()))
    por_ano = hist.assign(ano=hist["data"].str[:4]).groupby("ano").size().rename("Alagamentos")
    st.bar_chart(por_ano, height=200, color="#1f4e79")

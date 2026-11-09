import folium
import pandas as pd
import streamlit as st

from src import geo, risk, servico, ui, weather
from src.config import BBOX

ui.cabecalho("Como está a sua região", "Risco de alagamento, tempo agora e pontos críticos perto de você.",
             sobre="Minha região")
ui.aviso_simulacao()

USAR_GPS, USAR_END = "📍 Minha localização", "🔎 Buscar endereço"
minha = st.session_state.get("minha_loc")
dentro_sp = minha is not None and (BBOX["lat_min"] <= minha[0] <= BBOX["lat_max"]
                                   and BBOX["lon_min"] <= minha[1] <= BBOX["lon_max"])
if minha is not None and not dentro_sp:
    st.info("Sua localização parece estar fora da cidade de São Paulo — a previsão cobre só a "
            "capital. Busque um endereço em SP abaixo.")

c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
modo = USAR_END
if dentro_sp:
    modo = c1.segmented_control("Local", [USAR_GPS, USAR_END], default=USAR_GPS,
                                label_visibility="collapsed") or USAR_GPS
raio = c2.select_slider("Raio", [0.5, 1, 2, 3, 5], value=2, format_func=lambda r: f"{r} km")

if modo == USAR_GPS:
    lat, lon = minha
    nome_end = servico.endereco_de(lat, lon)
else:
    end = st.text_input("Endereço, bairro ou ponto de referência", "Praça da Sé, São Paulo",
                        placeholder="Ex.: Rua Augusta, 500")
    try:
        loc = servico.geocode(end) if end.strip() else None
    except Exception:  # noqa: BLE001
        st.warning("Sem internet, a busca de endereço não funciona. "
                   + ("Use 📍 Minha localização: o GPS funciona sem internet." if dentro_sp else ""), icon="📴")
        st.stop()
    if not loc:
        st.info("Não encontrei esse endereço. Tente incluir o bairro ou o número.")
        st.stop()
    lat, lon, nome_end = loc
st.caption(f"📍 {nome_end}")

sim = st.session_state.get("sim")
try:
    prev = servico.previsao(sim)
    local = servico.previsao_local(lat, lon, sim)
except Exception:  # noqa: BLE001 — sem internet e sem previsão guardada
    prev = local = None
    st.error(ui.SEM_INTERNET + " Abaixo, os pontos de alagamento e o histórico da sua região "
             "(não dependem de internet).", icon="📶")

# Alagamentos registrados hoje pelo CGE perto da pessoa (ao vivo)
hoje = servico.alagamentos_hoje()
hoje_perto = None
if hoje is not None:
    hoje = hoje[0]
    if len(hoje):
        hoje = hoje.assign(dist_km=geo.haversine_m(lat, lon, hoje["lat"].values, hoje["lon"].values) / 1000)
        hoje_perto = hoje[hoje["dist_km"] <= raio].sort_values("dist_km")
        for _, a in hoje_perto[hoje_perto["ativo"]].iterrows():
            st.error(f"**Alagamento ativo agora** a {a['dist_km']:.1f} km: {a['local']} ({a['bairro']}), "
                     f"desde {a['inicio']}" + (" — **intransitável**" if a["intransitavel"] else "")
                     + ". Fonte: CGE.", icon="🔴")

if prev is not None:
    ui.aviso_offline(servico.previsao_salva_em(), prev.agora, prev.cel_h["time"].max())
    pts = prev.pts.copy()
else:
    pts = servico.pontos().copy()
pts["dist_km"] = geo.haversine_m(lat, lon, pts["lat"].values, pts["lon"].values) / 1000
perto = pts[pts["dist_km"] <= raio].sort_values("p_janela" if prev is not None else "n_eventos", ascending=False)

if prev is not None:
    try:
        atual = servico.tempo_atual(lat, lon)
    except Exception:  # noqa: BLE001 — sem internet: "agora" vem da previsão horária guardada
        hora = local[local["time"] == prev.agora]
        atual = weather.tempo_da_previsao((hora if len(hora) else local).iloc[0])

    prox24 = risk.janela(local, prev.agora, 24)
    p_regiao = risk.prob_alguma(prox24["p"])
    p_perto = risk.prob_alguma(perto["p_janela"])
    normal_perto = risk.prob_alguma(perto["p_normal"])
    nivel = risk.pior([risk.classificar(p_perto), risk.classificar(p_regiao, "regiao")])

    # ------------------------------------------------ situação
    if len(perto):
        ui.cartao_risco(
            nivel, f"{ui.pct(p_perto)} de chance de alagar perto de você nas próximas 24h",
            f"<b>{risk.vezes_normal(p_perto, normal_perto).capitalize()}</b> para os {len(perto)} pontos "
            f"recorrentes de alagamento a até {raio} km (num dia qualquer: {ui.pct(normal_perto)}).")
    else:
        ui.cartao_risco(nivel, f"{ui.pct(p_regiao)} de chance de alagamento na sua região nas próximas 24h",
                        f"Nenhum ponto recorrente de alagamento a até {raio} km. A chance é da região (~11 km).")

    rajada = atual.get("wind_gusts_10m") or 0
    pico = prox24.loc[prox24["precip"].idxmax(), "time"] if prox24["precip"].max() > 0 else None
    ui.blocos([
        ("Agora", f"{atual['temperature_2m']:.0f} °C",
         f"{atual['descricao']} · sensação de {atual.get('apparent_temperature', atual['temperature_2m']):.0f} °C"),
        ("Umidade do ar", f"{atual['relative_humidity_2m']:.0f}%",
         "ar muito seco" if atual["relative_humidity_2m"] < 30 else ""),
        ("Vento", f"{atual['wind_speed_10m']:.0f} km/h {atual.get('direcao', '')}".strip(),
         f"rajadas de {rajada:.0f} km/h"),
        ("Chuva agora", f"{atual['precipitation']:.1f} mm", ""),
        ("Chuva nas próximas 24h", f"{prox24['precip'].sum():.1f} mm", f"pico de {prox24['precip'].max():.1f} mm/h"),
        ("Hora de mais chuva", f"{pico:%Hh}" if pico is not None else "Sem chuva",
         f"{pico:%d/%m}" if pico is not None else "nas próximas 24h"),
    ])

    rajada_max = prox24["rajada"].max() if "rajada" in prox24 else float("nan")
    if rajada_max >= 60:
        st.warning(f"Rajadas de até **{rajada_max:.0f} km/h** previstas nas próximas 24h — risco de queda de "
                   "árvores e de falta de energia. Evite ficar sob árvores e perto de fiação durante a chuva.",
                   icon="💨")

# ------------------------------------------------ mapa e previsão
col_m, col_g = st.columns([3, 2], gap="medium") if prev is not None else (st.container(), None)
with col_m:
    m = ui.mapa((lat, lon), 14 if raio <= 1 else 13)
    folium.Marker((lat, lon), tooltip="Você está aqui", icon=folium.Icon(color="blue", icon="home")).add_to(m)
    folium.Circle((lat, lon), radius=raio * 1000, color=ui.AZUL, fill=True, fill_opacity=0.04,
                  weight=1.5, dash_array="6 6").add_to(m)
    ui.camada_pontos(m, perto)
    if hoje_perto is not None and len(hoje_perto):
        ui.camada_ao_vivo(m, hoje_perto)
    ui.mostrar_mapa(m, 440)
if col_g is not None:
    with col_g:
        st.markdown("**Previsão hora a hora**")
        serie = local[(local["time"] >= prev.agora - pd.Timedelta(hours=6))
                      & (local["time"] < prev.agora + pd.Timedelta(hours=36))]
        st.altair_chart(ui.grafico_chuva_risco(serie, prev.agora, 300), width="stretch")
        st.caption("Barras: chuva prevista. Linha: chance de alagamento na região (~11 km) a cada hora.")

# ------------------------------------------------ pontos próximos e histórico
st.subheader(f"Pontos de alagamento a até {raio} km")
if perto.empty:
    st.write("Nenhum ponto recorrente registrado pelo CGE nesse raio.")
else:
    colunas = ["nome", "bairro", "dist_km", "p_janela", "hora_pico", "n_eventos", "ultimo"]
    st.dataframe(perto[[c for c in colunas if c in perto.columns]],
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
    ui.blocos([
        ("Alagamentos registrados", f"{len(hist)}", f"desde {hist['data'].min()[:4]}"),
        ("Último registro", pd.to_datetime(hist["data"]).max().strftime("%d/%m/%Y"), ""),
        ("Ficaram intransitáveis", ui.pct(hist["intransitavel"].mean()), "dos alagamentos"),
    ])
    por_ano = hist.assign(ano=hist["data"].str[:4]).groupby("ano").size().rename("Alagamentos")
    st.bar_chart(por_ano, height=200, color=ui.AZUL)

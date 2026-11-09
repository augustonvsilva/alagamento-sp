import altair as alt
import pandas as pd
import streamlit as st

from src import servico, ui

met = servico.metricas()
ui.cabecalho("Como o modelo funciona", "Dados, validação e limites da previsão — para entender o que "
             "as porcentagens do app querem dizer.", sobre="Modelo")


def n(x: int) -> str:
    return f"{x:,}".replace(",", ".")


st.markdown(f"""
O app estima, **para cada região da cidade e cada hora**, a probabilidade de o CGE registrar um
alagamento, a partir da chuva prevista. O modelo foi treinado com dados reais:

| Item | Descrição |
|---|---|
| **Alvo** | Início de alagamento registrado pelo CGE na região, naquela hora |
| **Unidade** | Região da grade (~11 km) × hora |
| **Variáveis** | Chuva acumulada em 1h, 3h, 6h, 24h e 72h · hora do dia · histórico de alagamentos da região |
| **Período** | {met['periodo'][0]} a {met['periodo'][1]} |
| **Validação** | Temporal: treino até {met['data_corte']}, teste depois ({n(met['n_teste'])} horas-região, {n(met['positivos_teste'])} com alagamento) |
| **Modelo escolhido** | {met['modelo_escolhido']}. Regra de parcimônia: o gradient boosting só seria escolhido com PR-AUC pelo menos 5% maior; a diferença foi de {met.get('ganho_complexo', 0):+.1%} |
| **Ajuste temporal** | Pesos com meia-vida de 2 anos + recalibração do intercepto para a taxa dos últimos 12 meses |
""")

st.subheader("Desempenho no período de teste")
res = pd.DataFrame(met["resultados"]).T.reset_index(names="Modelo")
st.dataframe(res, hide_index=True, width="stretch", column_config={
    "roc_auc": st.column_config.NumberColumn("ROC-AUC", format="%.3f",
                                             help="Capacidade de ordenar horas com e sem alagamento (0,5 = acaso)"),
    "pr_auc": st.column_config.NumberColumn("PR-AUC", format="%.3f",
                                            help="Precisão média. Mais informativa com eventos raros."),
    "brier": st.column_config.NumberColumn("Brier", format="%.5f", help="Erro quadrático da probabilidade (menor é melhor)"),
    "taxa_base": st.column_config.NumberColumn("Taxa base", format="percent",
                                               help="Fração de horas-região com alagamento"),
})
base = met["resultados"][met["modelo_escolhido"]]["taxa_base"]
melhor_pr = met["resultados"][met["modelo_escolhido"]]["pr_auc"]
st.caption(f"Alagamento é um evento raro ({base:.2%} das horas-região). Um modelo que chutasse ao acaso "
           f"teria PR-AUC ≈ {base:.3f}. O modelo escolhido tem {melhor_pr:.3f}, ou seja, "
           f"**{melhor_pr / base:.0f}× melhor que o acaso**. A heurística do protótipo serve de base de comparação.")

with st.container(border=True):
    st.markdown(f"""
**Como ler as porcentagens do app**

- **Alagamento é raro.** Em uma hora qualquer, a chance de o CGE registrar um alagamento numa região
  é de {base:.2%}. Por isso uma chance de **3% já é alta**: é muitas vezes o normal.
- Por isso o app sempre compara com o **normal do local** ("5× o normal"): a média histórica de
  alagamentos daquele ponto ou região, calculada com os dados do CGE desde {met['periodo'][0][:4]}.
- O modelo **ordena bem** as situações de risco (ROC-AUC {met['resultados'][met['modelo_escolhido']]['roc_auc']:.2f}),
  mas **não acerta o momento exato**: mesmo nas horas de maior risco, a maioria não termina em
  alagamento registrado (PR-AUC {melhor_pr:.3f}). Use o nível de risco como **aviso para ficar atento**,
  não como certeza.
- O CGE só registra alagamentos que viu; alagamentos pequenos ou em ruas menores podem ficar de fora.
""")

c1, c2 = st.columns(2)
with c1:
    st.markdown("**Calibração:** quando o modelo diz X%, acontece X%?")
    cal = pd.DataFrame(met["calibracao"])
    lim = float(max(cal["prevista"].max(), cal["observada"].max()) * 1.1)
    diag = alt.Chart(pd.DataFrame({"x": [0, lim], "y": [0, lim]})).mark_line(
        strokeDash=[4, 4], color="gray").encode(x="x:Q", y="y:Q")
    pts = alt.Chart(cal).mark_line(point=True, color=ui.VERMELHO).encode(
        x=alt.X("prevista:Q", title="Probabilidade prevista", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, lim])),
        y=alt.Y("observada:Q", title="Frequência observada", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, lim])),
        tooltip=[alt.Tooltip("prevista:Q", format=".2%"), alt.Tooltip("observada:Q", format=".2%"), "n:Q"])
    st.altair_chart((diag + pts).properties(height=300), width="stretch")
    st.caption("Pontos próximos da diagonal indicam probabilidades confiáveis. "
               "Só entram horas com chuva relevante (metade superior das previsões). "
               "O modelo ainda superestima no teste porque 2026 alagou bem menos que os anos "
               "anteriores (veja a tendência em *Análise histórica*). O modelo em produção "
               "já inclui 2026 na recalibração.")
with c2:
    st.markdown("**Importância das variáveis** (permutação no teste)")
    imp = pd.DataFrame(met["importancia"])
    st.altair_chart(alt.Chart(imp).mark_bar(color=ui.AZUL).encode(
        y=alt.Y("feature:N", sort="-x", title=None, axis=alt.Axis(labelLimit=260)),
        x=alt.X("importancia:Q", title="Queda no PR-AUC ao embaralhar"),
        tooltip=["feature", alt.Tooltip("importancia:Q", format=".4f")]).properties(height=300),
        width="stretch")

st.markdown("**Resposta do modelo à chuva:** probabilidade por hora numa região típica, às 17h, "
            "com chuva constante")
resp = pd.DataFrame(met["resposta_chuva"])
st.altair_chart(alt.Chart(resp).mark_line(color=ui.VERMELHO, strokeWidth=3).encode(
    x=alt.X("chuva_mm_h:Q", title="Chuva (mm/h, mantida por 6h)"),
    y=alt.Y("prob:Q", title="Probabilidade de alagamento na hora", axis=alt.Axis(format="%")),
    tooltip=[alt.Tooltip("chuva_mm_h:Q", title="mm/h"), alt.Tooltip("prob:Q", format=".1%")]
).properties(height=260), width="stretch")

st.subheader("Umidade do ar e vento ajudam a prever?")
exp = met.get("experimento_clima")
if not exp:
    st.info("Este teste roda junto com a atualização mensal dos dados (GitHub Actions), que baixa "
            "o histórico de umidade e vento de cada região. O resultado aparece aqui depois da "
            "próxima atualização.", icon="🧪")
else:
    tab_exp = pd.DataFrame(exp["resultados"]).T.reset_index(names="Variáveis")
    st.dataframe(tab_exp[["Variáveis", "roc_auc", "pr_auc", "brier"]], hide_index=True, width="stretch",
                 column_config={"roc_auc": st.column_config.NumberColumn("ROC-AUC", format="%.3f"),
                                "pr_auc": st.column_config.NumberColumn("PR-AUC", format="%.3f"),
                                "brier": st.column_config.NumberColumn("Brier", format="%.5f")})
    g = exp["ganho_pr_auc"]
    coef = ", ".join(f"{k}: {v:+.2f}" for k, v in exp["coef_padronizado"].items())
    ic = exp.get("ganho_ic90")
    txt_ic = (f" (intervalo de 90%: {ic[0]:+.0%} a {ic[1]:+.0%}; ganho positivo em "
              f"{exp['prob_ganho_positivo']:.0%} dos sorteios)") if ic else ""
    sinais_negativos = all(v < 0 for v in exp["coef_padronizado"].values())
    if g >= 0.05 and ic and ic[0] > 0:
        conclusao = (f"Umidade e vento trazem uma **melhora pequena, mas consistente**: {g:+.1%} de PR-AUC no "
                     f"teste{txt_ic}. Por outro lado, o ROC-AUC quase não muda"
                     + (" e os coeficientes têm sinal pouco intuitivo (mais umidade e mais vento → *menos* "
                        "alagamento, com a mesma chuva). Isso sugere que essas variáveis estão captando o "
                        "**tipo de tempestade** (frentes frias com vento × pancadas de verão, que alagam mais), "
                        "e não uma causa do alagamento." if sinais_negativos else ".")
                     + " **Decisão:** por enquanto mantivemos o modelo só com chuva, mais simples e fácil de "
                       "explicar; as novas variáveis ficam como candidatas, reavaliadas a cada atualização mensal.")
    elif g >= 0.05:
        conclusao = (f"Umidade e vento melhoraram {g:+.1%} o PR-AUC{txt_ic}, mas o intervalo inclui zero: "
                     "o ganho pode ser acaso. Mantivemos o modelo só com chuva.")
    else:
        conclusao = (f"Umidade e vento **não melhoram o suficiente** ({g:+.1%} de PR-AUC no teste, abaixo "
                     "dos 5% exigidos). Mantivemos o modelo só com chuva: mais simples e igual de bom. "
                     "Faz sentido: o alagamento depende da quantidade de água que cai; umidade alta e "
                     "vento forte acompanham as tempestades, mas a chuva já carrega essa informação.")
    st.markdown(conclusao)
    st.caption(f"Mesmas {n(exp['n_horas'])} horas-região e mesma validação temporal nos dois modelos "
               f"({n(exp['positivos_teste'])} alagamentos no teste). Coeficientes padronizados das "
               f"novas variáveis: {coef}.")

st.subheader("Do modelo ao mapa")
st.markdown("""
1. **Região:** o modelo dá a probabilidade *p(região, hora)* de algum alagamento na região.
2. **Ponto:** cada ponto recorrente recebe *p(região, hora) × participação*, onde a participação
   é a fração das horas com alagamento na região em que aquele ponto específico alagou.
3. **Janela:** a chance de alagar nas próximas *N* horas combina as horas assumindo
   independência: 1 − ∏(1 − pₕ).
4. **Trajeto:** a chance de encontrar algum ponto alagado combina os pontos a menos de
   *X* metros da rota durante o tempo de viagem.

**Limitações**
- A previsão do tempo erra, principalmente nas pancadas de verão, que são muito localizadas. A
  resolução dos modelos meteorológicos (~10–25 km) não enxerga a chuva rua a rua.
- O CGE registra alagamentos em vias monitoradas. Ruas pequenas e bairros periféricos podem ficar sub-representados.
- Locais sem endereço preciso foram posicionados no centro do bairro.
- Tratar as horas como independentes é uma simplificação que tende a superestimar janelas longas.
""")

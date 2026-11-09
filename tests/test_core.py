from datetime import date

import numpy as np
import pandas as pd
import pytest

from pipeline.coletar_cge import parse_dia
from src.nomes import expandir, normalizar
from src import features, geo, risk
from src.grade import celula_id, id_para_coord

HTML_CGE = """
<h1 class="tit-bairros">Zona Norte</h1>
<table class="tb-pontos-de-alagamentos">
  <tr><td class="bairro arial-bairros-alag linha-pontilhada">Casa Verde <hr/></td>
      <td class="total-pts arial-bairros-alag">1 pts.</td></tr>
  <tr><td colspan="3"><div class="ponto-de-alagamento"><ul>
    <li class="inativo-intransitavel" title="Inativo Intransitável"></li>
    <li class="espaco"></li>
    <li class="arial-descr-alag col-local">De 15:52 a 16:10<br/>R REIMS</li>
    <li class="ln-vert"></li>
    <li class="arial-descr-alag">Sentido: UNICO<br/>Referência: AV CASA VERDE</li>
  </ul></div></td></tr>
</table>
<h1 class="tit-bairros">Zona Sul</h1>
<table class="tb-pontos-de-alagamentos">
  <tr><td class="bairro arial-bairros-alag linha-pontilhada">Santo Amaro <hr/></td></tr>
  <tr><td colspan="3"><div class="ponto-de-alagamento"><ul>
    <li class="ativo-transitavel"></li>
    <li class="arial-descr-alag col-local">De 17:05 a <br/>AV JOAO DIAS</li>
    <li class="arial-descr-alag">Sentido: AMBOS<br/>Referência: ALTURA DO N. 10</li>
  </ul></div></td></tr>
</table>
"""


def test_parse_dia_extrai_campos():
    regs = parse_dia(HTML_CGE, date(2026, 1, 15))
    assert len(regs) == 2
    r = regs[0]
    assert (r["zona"], r["bairro"], r["inicio"], r["fim"], r["local"]) == \
        ("Zona Norte", "Casa Verde", "15:52", "16:10", "R REIMS")
    assert r["referencia"] == "AV CASA VERDE" and r["intransitavel"] is True
    assert regs[1]["zona"] == "Zona Sul" and regs[1]["fim"] is None and regs[1]["intransitavel"] is False


def test_parse_dia_vazio():
    assert parse_dia("<html><body>Nenhum alagamento</body></html>", date(2026, 1, 1)) == []


@pytest.mark.parametrize("entrada,esperado", [
    ("R REIMS", "Rua Reims"),
    ("AV PROF LUIZ IGNACIO ANHAIA MELLO", "Avenida Professor Luiz Ignacio Anhaia Mello"),
    ("PTE DAS BANDEIRAS", "Ponte das Bandeiras"),
    ("AV DOS BANDEIRANTES", "Avenida dos Bandeirantes"),
])
def test_expandir_abreviacoes(entrada, esperado):
    assert expandir(entrada) == esperado


def test_normalizar_unifica_variantes():
    assert normalizar("AV. MERCURIO") == normalizar("AV MERCURIO") == normalizar(" av  mercurio ")


def test_grade_ida_e_volta():
    cid = celula_id(-23.5489, -46.6388)
    assert cid == "-23.5_-46.6"
    assert id_para_coord(cid) == (-23.5, -46.6)


def test_haversine_conhecido():
    # Praça da Sé -> Av. Paulista (MASP): ~2,5 km em linha reta
    d = geo.haversine_m(-23.5503, -46.6339, -23.5614, -46.6559)
    assert 2400 < d < 2700


def test_features_janelas_acumuladas():
    t = pd.date_range("2026-01-01", periods=5, freq="h")
    chuva = pd.DataFrame({"celula": "c", "time": t, "precip": [0, 10, 5, 0, 1]})
    f = features.construir(chuva, {"c": 2.0})
    assert f["p3h"].tolist() == [0, 10, 15, 15, 6]
    assert np.isclose(f["log_taxa_celula"].iloc[0], np.log1p(2.0))
    assert set(features.FEATURES) <= set(f.columns)


def test_prob_alguma_e_niveis():
    assert risk.prob_alguma([]) == 0
    assert np.isclose(risk.prob_alguma([0.5, 0.5]), 0.75)
    assert risk.classificar(0.0) == "Baixo"
    assert risk.classificar(0.99) == "Muito alto"
    assert risk.pior(["Baixo", "Alto", "Moderado"]) == "Alto"


def test_404_html_igual_ao_index():
    """O GitHub Pages serve o 404.html nas sub-URLs (ex.: /trajeto): precisa ser cópia do index.html."""
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent
    assert (raiz / "404.html").read_bytes() == (raiz / "index.html").read_bytes(), \
        "Rode: Copy-Item index.html 404.html"


def test_index_html_lista_arquivos_do_app():
    """Todo .py usado pelo app precisa estar na lista `arquivos` do index.html (stlite)."""
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent
    html = (raiz / "index.html").read_text(encoding="utf-8")
    for arq in ["app.py", *[f"src/{p.name}" for p in (raiz / "src").glob("*.py")],
                *[f"paginas/{p.name}" for p in (raiz / "paginas").glob("*.py")]]:
        assert f'"{arq}"' in html, f"{arq} não está no index.html"


def test_simulacao_so_altera_janela():
    t = pd.date_range("2026-01-01", periods=6, freq="h")
    fc = pd.DataFrame({"time": t, "precip": 0.0, "prob": 0.0})
    s = risk.simular_chuva(fc, t[2], 30, 2)
    assert s["precip"].tolist() == [0, 0, 30, 30, 0, 0]


def test_offline_salvar_e_carregar(tmp_path, monkeypatch):
    from src import offline
    monkeypatch.setattr(offline, "PASTA", tmp_path)
    assert offline.carregar_previsao(["a"]) is None
    t = pd.date_range("2026-11-07", periods=3, freq="h")
    fc = lambda cel, v: pd.DataFrame({"celula": cel, "time": t, "precip": v})  # noqa: E731
    offline.salvar_previsao(pd.concat([fc("a", 1.0), fc("b", 2.0)]), pd.Timestamp("2026-11-07 10:00"))
    offline.salvar_previsao(fc("b", 5.0), pd.Timestamp("2026-11-07 11:00"))  # substitui só a célula b
    df, quando = offline.carregar_previsao(["a", "b"])
    assert len(df) == 6 and quando == pd.Timestamp("2026-11-07 10:00")
    assert df.loc[df["celula"] == "b", "precip"].eq(5.0).all()
    assert offline.carregar_previsao(["c"]) is None


def test_tempo_da_previsao():
    from src.weather import direcao_vento, tempo_da_previsao
    atual = tempo_da_previsao(pd.Series({"temp": 21.0, "sensacao": 23.0, "umidade": 80, "precip": 0.4,
                                         "vento": 12.0, "rajada": 40.0, "codigo": 61, "direcao_graus": 180}))
    assert atual["descricao"] == "Chuva fraca" and atual["direcao"] == "S"
    assert atual["relative_humidity_2m"] == 80
    assert direcao_vento(350) == "N" and direcao_vento(None) == ""


def test_pontos_de_desvio_ficam_dos_dois_lados():
    # caminho reto de oeste para leste; ponto no meio -> desvios ao norte e ao sul, ~900 m
    path = np.c_[np.full(50, -23.55), np.linspace(-46.70, -46.60, 50)]
    vias = geo.pontos_de_desvio(path, -23.55, -46.65)
    assert len(vias) == 2
    lats = sorted(v[0] for v in vias)
    assert lats[0] < -23.55 < lats[1]
    for la, lo in vias:
        assert 800 < geo.haversine_m(-23.55, -46.65, la, lo) < 1000


def test_rotas_desviando_so_aceita_rota_que_evita_o_ponto(monkeypatch):
    from src import servico
    reta = np.c_[np.full(50, -23.55), np.linspace(-46.70, -46.60, 50)]
    rts = [{"dist_km": 10.0, "dur_min": 20.0, "path": reta}]
    ponto = pd.DataFrame({"ponto": [1], "lat": [-23.55], "lon": [-46.65], "nome": ["Rua X"]})

    def via(o, v, d):  # rota que sobe até o ponto de desvio (passa longe do alagamento)
        return {"dist_km": 11.0, "dur_min": 23.0,
                "path": np.array([[-23.55, -46.70], [v[0], -46.66], [v[0], -46.64], [-23.55, -46.60]])}
    monkeypatch.setattr(servico, "_rota_via", via)
    novas = servico.rotas_desviando((-23.55, -46.70), (-23.55, -46.60), rts, ponto)
    assert len(novas) == 1 and novas[0]["desvio"] == "Rua X"  # a segunda tem a mesma distância

    monkeypatch.setattr(servico, "_rota_via", lambda o, v, d: {**rts[0], "dist_km": 12.0})
    assert servico.rotas_desviando((-23.55, -46.70), (-23.55, -46.60), rts, ponto) == []


def test_parse_dia_marca_alagamento_ativo():
    regs = parse_dia(HTML_CGE, date(2026, 11, 2))
    por_local = {r["local"]: r for r in regs}
    assert por_local["AV JOAO DIAS"]["ativo"] is True
    assert por_local["R REIMS"]["ativo"] is False


def test_ao_vivo_localiza_pelo_historico():
    from pathlib import Path
    from src import ao_vivo
    raiz = Path(__file__).resolve().parent.parent
    ev = pd.read_parquet(raiz / "data/processed/alagamentos_geo.parquet")
    pts = pd.read_parquet(raiz / "data/processed/pontos.parquet")
    dia = ev["data"].value_counts().index[0]  # o dia com mais alagamentos
    regs = ev[ev["data"] == dia][ao_vivo.COLUNAS[:-1]].assign(ativo=True).to_dict("records")
    regs.append({**regs[0], "local": "RUA QUE NAO EXISTE", "bairro": "Bairro Inventado"})
    df = ao_vivo.localizar(regs, ev, pts)
    assert len(df) == len(regs)
    assert df["lat"].iloc[:-1].notna().all()          # todos os do histórico foram localizados
    assert df["precisao"].iloc[-1] == "desconhecida"   # o inventado não
    assert df["ponto"].notna().any()                    # e parte bate com pontos monitorados
    assert "ainda ativo" in ao_vivo.resumo_texto(df)


def test_experimento_clima_detecta_variavel_util():
    """Com dados sintéticos em que a umidade influencia o alagamento, o experimento mostra ganho."""
    sk = pytest.importorskip("sklearn")  # noqa: F841 — só no ambiente do pipeline
    from pipeline.treinar_modelo import experimento_clima
    rng = np.random.default_rng(0)
    t = pd.date_range("2024-01-01", periods=24 * 400, freq="h")
    chuva = pd.DataFrame({"celula": "a", "time": t, "precip": np.where(rng.random(len(t)) < 0.1, rng.gamma(1.5, 5, len(t)), 0)})
    df = features.construir(chuva, {"a": 20.0})
    umid = rng.uniform(30, 100, len(t))
    z = -9 + 1.2 * df["log_p3h"] + 0.06 * (umid - 65)
    df["y"] = (rng.random(len(t)) < 1 / (1 + np.exp(-z))).astype(int)
    clima = pd.DataFrame({"celula": "a", "time": t, "umidade": umid,
                          "vento": rng.uniform(0, 30, len(t)), "rajada": rng.uniform(0, 60, len(t))})
    r = experimento_clima(df, clima, pd.Timestamp("2024-11-01"))
    assert r["ganho_pr_auc"] > 0.05
    assert r["coef_padronizado"]["Umidade do ar"] > abs(r["coef_padronizado"]["Vento"])

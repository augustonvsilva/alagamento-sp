"""O alerta do Android (CalculoRisco.java) calcula o mesmo risco que o app em Python?

Compila a classe Java com o JDK da máquina (JAVA_HOME ou javac no PATH) e compara as
probabilidades com src/features.py para a mesma chuva. Sem JDK, o teste é pulado.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import features, risk
from src.grade import celula_id

ROOT = Path(__file__).resolve().parent.parent
JAVA_SRC = ROOT / "android/app/src/main/java/br/alagamentosp/app/CalculoRisco.java"


def _jdk():
    home = os.environ.get("JAVA_HOME")
    for cand in ([Path(home) / "bin"] if home else []) + [Path(p).parent for p in filter(None, [shutil.which("javac")])]:
        if (cand / "javac").exists() or (cand / "javac.exe").exists():
            return cand
    for cand in Path.home().glob(".android-build-tools/jdk/*/bin"):
        return cand
    return None


HARNESS = """package br.alagamentosp.app;
import java.util.*;
public class Harness {
  static double[] linha(Scanner s, int n) { double[] v = new double[n]; for (int i = 0; i < n; i++) v[i] = s.nextDouble(); return v; }
  public static void main(String[] a) {
    Scanner s = new Scanner(System.in).useLocale(Locale.ROOT);
    double[] media = linha(s, 8), escala = linha(s, 8), coef = linha(s, 8);
    double inter = s.nextDouble(), delta = s.nextDouble(), taxa = s.nextDouble();
    int n = s.nextInt(); double[] chuva = linha(s, n); int[] horas = new int[n];
    for (int i = 0; i < n; i++) horas[i] = s.nextInt();
    double[] p = new CalculoRisco(media, escala, coef, inter, delta).probHoraria(chuva, horas, taxa);
    StringBuilder sb = new StringBuilder();
    for (double x : p) sb.append(String.format(Locale.ROOT, "%.15e%n", x));
    sb.append(String.format(Locale.ROOT, "%.15e%n", CalculoRisco.chanceNormal(taxa, 0.3, 24)));
    sb.append(CalculoRisco.celula(-23.5614, -46.6559)).append("\\n");
    sb.append(CalculoRisco.celula(-23.45, -46.65)).append("\\n");
    System.out.print(sb);
  }
}
"""


@pytest.mark.skipif(_jdk() is None, reason="JDK não encontrado")
def test_java_calcula_igual_ao_python(tmp_path):
    jdk = _jdk()
    pasta = tmp_path / "br/alagamentosp/app"
    pasta.mkdir(parents=True)
    shutil.copy(JAVA_SRC, pasta / "CalculoRisco.java")
    (pasta / "Harness.java").write_text(HARNESS, encoding="utf-8")
    subprocess.run([str(jdk / "javac"), "-encoding", "UTF-8", "-d", str(tmp_path / "out"),
                    str(pasta / "CalculoRisco.java"), str(pasta / "Harness.java")], check=True)

    modelo = json.loads((ROOT / "models/modelo.json").read_text(encoding="utf-8"))
    rng = np.random.default_rng(1)
    t = pd.date_range("2026-01-10 00:00", periods=120, freq="h")
    chuva = np.where(rng.random(120) < 0.25, rng.gamma(1.2, 6, 120), 0.0)
    chuva[60:64] = [20, 35, 15, 4]  # uma pancada forte
    taxa = 35.26
    df = features.construir(pd.DataFrame({"celula": "x", "time": t, "precip": chuva}), {"x": taxa})
    p_py = features.prever_json(modelo, df)
    p_py = np.where(df["p6h"] < 0.2, np.minimum(p_py, 1e-4), p_py)

    entrada = " ".join(map(str, [*modelo["media"], *modelo["escala"], *modelo["coef"],
                                 modelo["intercepto"], modelo.get("delta", 0.0), taxa, len(t),
                                 *chuva, *t.hour]))
    saida = subprocess.run([str(jdk / "java"), "-cp", str(tmp_path / "out"), "br.alagamentosp.app.Harness"],
                           input=entrada, capture_output=True, text=True, check=True).stdout.split()
    p_java = np.array(saida[:120], dtype=float)
    np.testing.assert_allclose(p_java, p_py, rtol=1e-9, atol=1e-12)
    assert float(saida[120]) == pytest.approx(float(risk.chance_normal(taxa, 0.3)), rel=1e-12)
    assert saida[121] == celula_id(-23.5614, -46.6559)
    assert saida[122] == celula_id(-23.45, -46.65)

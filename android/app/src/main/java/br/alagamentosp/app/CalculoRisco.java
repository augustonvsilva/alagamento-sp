package br.alagamentosp.app;

/**
 * Mesmo cálculo de risco do app (src/features.py + src/risk.py), em Java puro, para o alerta
 * em segundo plano funcionar sem abrir o app. Sem dependências do Android: é testado no
 * computador contra o Python (tests/test_alerta_java.py).
 */
final class CalculoRisco {

    static final int[] JANELAS = {1, 3, 6, 24, 72};

    final double[] media;
    final double[] escala;
    final double[] coef;
    final double intercepto;
    final double delta;

    CalculoRisco(double[] media, double[] escala, double[] coef, double intercepto, double delta) {
        if (media.length != 8 || escala.length != 8 || coef.length != 8) {
            throw new IllegalArgumentException("modelo com variáveis diferentes das esperadas");
        }
        this.media = media;
        this.escala = escala;
        this.coef = coef;
        this.intercepto = intercepto;
        this.delta = delta;
    }

    /**
     * Probabilidade de alagamento na região em cada hora.
     *
     * @param chuva chuva horária (mm), em ordem, incluindo os dias anteriores (janelas de até 72h)
     * @param horas hora do dia (0-23) de cada posição
     * @param taxa  alagamentos por ano na região (taxa histórica)
     */
    double[] probHoraria(double[] chuva, int[] horas, double taxa) {
        int n = chuva.length;
        double[] p = new double[n];
        double[] acum = new double[n + 1];
        for (int i = 0; i < n; i++) acum[i + 1] = acum[i] + Math.max(0, chuva[i]);
        double logTaxa = Math.log1p(taxa);
        double[] x = new double[8];
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < JANELAS.length; j++) {
                int ini = Math.max(0, i + 1 - JANELAS[j]);  // rolling(h, min_periods=1)
                x[j] = Math.log1p(acum[i + 1] - acum[ini]);
            }
            x[5] = Math.sin(2 * Math.PI * horas[i] / 24.0);
            x[6] = Math.cos(2 * Math.PI * horas[i] / 24.0);
            x[7] = logTaxa;
            double z = intercepto + delta;
            for (int k = 0; k < 8; k++) z += (x[k] - media[k]) / escala[k] * coef[k];
            double prob = 1 / (1 + Math.exp(-z));
            // Sem chuva relevante nas últimas 6h o risco é desprezível (igual ao app)
            double p6h = acum[i + 1] - acum[Math.max(0, i + 1 - 6)];
            if (p6h < 0.2) prob = Math.min(prob, 1e-4);
            p[i] = prob;
        }
        return p;
    }

    /** P(pelo menos um evento) = 1 - Π(1 - p), nas posições [ini, fim). */
    static double probAlguma(double[] p, int ini, int fim, double fator) {
        double nenhum = 1;
        for (int i = Math.max(0, ini); i < Math.min(fim, p.length); i++) {
            nenhum *= 1 - Math.min(1, Math.max(0, p[i] * fator));
        }
        return 1 - nenhum;
    }

    /** Chance "normal" (média histórica) de alagar em N horas — igual a risk.chance_normal. */
    static double chanceNormal(double taxa, double participacao, int horas) {
        double b = Math.min(1, Math.max(0, taxa / 8766.0 * participacao));
        return 1 - Math.pow(1 - b, horas);
    }

    /** Índice do nível (0 = Baixo ... 3 = Muito alto) para os limiares dados. */
    static int nivel(double p, double[] limiares) {
        for (int i = 0; i < limiares.length; i++) if (p < limiares[i]) return i;
        return limiares.length;
    }

    static double distanciaKm(double lat1, double lon1, double lat2, double lon2) {
        double r = 6371.0;
        double f1 = Math.toRadians(lat1), f2 = Math.toRadians(lat2);
        double df = f2 - f1, dl = Math.toRadians(lon2 - lon1);
        double a = Math.sin(df / 2) * Math.sin(df / 2) + Math.cos(f1) * Math.cos(f2) * Math.sin(dl / 2) * Math.sin(dl / 2);
        return 2 * r * Math.asin(Math.sqrt(a));
    }

    /** Id da célula da grade de 0,1° (igual a src/grade.celula_id). */
    static String celula(double lat, double lon) {
        return String.format(java.util.Locale.ROOT, "%.1f_%.1f",
                Math.rint(lat / 0.1) * 0.1, Math.rint(lon / 0.1) * 0.1);  // rint = arredonda .5 para o par, como o numpy
    }
}

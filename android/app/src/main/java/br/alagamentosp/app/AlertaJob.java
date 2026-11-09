package br.alagamentosp.app;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.job.JobInfo;
import android.app.job.JobParameters;
import android.app.job.JobScheduler;
import android.app.job.JobService;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.PersistableBundle;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Alerta em segundo plano: a cada hora, sem abrir o app, calcula o risco de alagamento perto
 * do último local visto pelo app (mesmo modelo e mesmas regras da página "Minha região") e
 * avisa com uma notificação quando ele fica alto.
 *
 * Para não incomodar: só notifica em risco Alto ou Muito alto, e repete no máximo a cada 6 h
 * — a não ser que o risco suba de nível.
 */
public class AlertaJob extends JobService {

    static final String TAG = "AlertaJob";
    static final int JOB_PERIODICO = 1;
    static final int JOB_TESTE = 2;
    static final String PREFS = "alerta";
    static final String CANAL = "alertas";
    private static final int NIVEL_AVISO = 2;  // "Alto"
    private static final long REPETIR_MS = 6 * 3600_000L;

    /** Agenda a verificação de hora em hora (não duplica se já estiver agendada). */
    static void agendar(Context ctx) {
        JobScheduler js = ctx.getSystemService(JobScheduler.class);
        if (js == null || js.getPendingJob(JOB_PERIODICO) != null) return;
        js.schedule(new JobInfo.Builder(JOB_PERIODICO, new ComponentName(ctx, AlertaJob.class))
                .setPeriodic(3600_000L, 15 * 60_000L)
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .setPersisted(true)
                .build());
    }

    /** Roda uma vez agora e notifica mesmo com risco baixo (para demonstrar o alerta). */
    static void testarAgora(Context ctx) {
        PersistableBundle extras = new PersistableBundle();
        extras.putBoolean("teste", true);
        JobScheduler js = ctx.getSystemService(JobScheduler.class);
        if (js == null) return;
        js.schedule(new JobInfo.Builder(JOB_TESTE, new ComponentName(ctx, AlertaJob.class))
                .setOverrideDeadline(0)
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .setExtras(extras)
                .build());
    }

    static void salvarLocal(Context ctx, double lat, double lon) {
        ctx.getSharedPreferences(PREFS, MODE_PRIVATE).edit()
                .putString("lat", Double.toString(lat)).putString("lon", Double.toString(lon)).apply();
    }

    @Override
    public boolean onStartJob(JobParameters params) {
        boolean teste = params.getExtras().getBoolean("teste", false);
        new Thread(() -> {
            boolean deNovo = false;
            try {
                verificar(teste);
            } catch (Exception e) {
                Log.w(TAG, "falha na verificação", e);
                deNovo = !teste;  // sem internet etc.: o sistema tenta de novo mais tarde
            }
            jobFinished(params, deNovo);
        }).start();
        return true;
    }

    @Override
    public boolean onStopJob(JobParameters params) {
        return true;
    }

    private void verificar(boolean teste) throws Exception {
        SharedPreferences prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        if (!prefs.contains("lat")) {
            Log.i(TAG, "sem localização salva ainda");
            return;
        }
        double lat = Double.parseDouble(prefs.getString("lat", "0"));
        double lon = Double.parseDouble(prefs.getString("lon", "0"));

        JSONObject cfg = new JSONObject(ler(getAssets().open("www/models/alerta.json")));
        CalculoRisco calc = new CalculoRisco(vetor(cfg.getJSONArray("media")), vetor(cfg.getJSONArray("escala")),
                vetor(cfg.getJSONArray("coef")), cfg.getDouble("intercepto"), cfg.optDouble("delta", 0));
        JSONObject taxas = cfg.getJSONObject("celulas");
        double raio = cfg.getDouble("raio_km");

        // Pontos monitorados a até `raio` km e as regiões (células) necessárias
        String minhaCelula = CalculoRisco.celula(lat, lon);
        Map<String, double[]> chuva = new LinkedHashMap<>();
        chuva.put(minhaCelula, null);
        List<JSONArray> perto = new ArrayList<>();
        JSONArray pontos = cfg.getJSONArray("pontos");
        for (int i = 0; i < pontos.length(); i++) {
            JSONArray p = pontos.getJSONArray(i);
            if (CalculoRisco.distanciaKm(lat, lon, p.getDouble(0), p.getDouble(1)) <= raio) {
                perto.add(p);
                chuva.put(p.getString(2), null);
            }
        }

        // Previsão horária de chuva para essas células (inclui 3 dias passados: janelas de 72h)
        List<String> ids = new ArrayList<>(chuva.keySet());
        StringBuilder la = new StringBuilder(), lo = new StringBuilder();
        for (String id : ids) {
            String[] c = id.split("_");
            la.append(la.length() > 0 ? "," : "").append(c[0]);
            lo.append(lo.length() > 0 ? "," : "").append(c[1]);
        }
        String url = "https://api.open-meteo.com/v1/forecast?latitude=" + la + "&longitude=" + lo
                + "&hourly=precipitation&past_days=3&forecast_days=2&timezone=America%2FSao_Paulo";
        String corpo = ler(abrir(url));
        JSONArray locais = corpo.trim().startsWith("[") ? new JSONArray(corpo) : new JSONArray().put(new JSONObject(corpo));

        String agora = ZonedDateTime.now(ZoneId.of("America/Sao_Paulo"))
                .format(DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:00", Locale.ROOT));
        Map<String, double[]> prob = new LinkedHashMap<>();
        int ini = -1;
        for (int k = 0; k < ids.size(); k++) {
            JSONObject h = locais.getJSONObject(k).getJSONObject("hourly");
            JSONArray tempos = h.getJSONArray("time"), mm = h.getJSONArray("precipitation");
            double[] c = new double[tempos.length()];
            int[] horas = new int[tempos.length()];
            for (int i = 0; i < c.length; i++) {
                c[i] = mm.isNull(i) ? 0 : mm.getDouble(i);
                horas[i] = Integer.parseInt(tempos.getString(i).substring(11, 13));
                if (k == 0 && tempos.getString(i).equals(agora)) ini = i;
            }
            prob.put(ids.get(k), calc.probHoraria(c, horas, taxas.optDouble(ids.get(k), 0)));
        }
        if (ini < 0) throw new IllegalStateException("hora atual fora da previsão: " + agora);
        int fim = ini + 24;

        double pRegiao = CalculoRisco.probAlguma(prob.get(minhaCelula), ini, fim, 1);
        double nenhumPerto = 1, nenhumNormal = 1;
        for (JSONArray p : perto) {
            String cel = p.getString(2);
            double part = p.getDouble(3);
            nenhumPerto *= 1 - CalculoRisco.probAlguma(prob.get(cel), ini, fim, part);
            nenhumNormal *= 1 - CalculoRisco.chanceNormal(taxas.optDouble(cel, 0), part, 24);
        }
        double pPerto = 1 - nenhumPerto, normalPerto = 1 - nenhumNormal;
        int nivel = Math.max(CalculoRisco.nivel(pPerto, vetor(cfg.getJSONArray("limiares_ponto"))),
                CalculoRisco.nivel(pRegiao, vetor(cfg.getJSONArray("limiares_regiao"))));
        String nomeNivel = cfg.getJSONArray("niveis").getString(nivel);
        Log.i(TAG, String.format(Locale.ROOT, "local=%s pontos=%d p_perto=%.5f p_regiao=%.5f nivel=%s",
                minhaCelula, perto.size(), pPerto, pRegiao, nomeNivel));

        int ultimo = prefs.getInt("ultimo_nivel", 0);
        long ultimoMs = prefs.getLong("ultimo_ms", 0);
        long agoraMs = System.currentTimeMillis();
        boolean avisar = teste || (nivel >= NIVEL_AVISO && (nivel > ultimo || agoraMs - ultimoMs > REPETIR_MS));
        SharedPreferences.Editor ed = prefs.edit().putInt("ultimo_nivel", nivel);
        if (avisar) {
            String texto = perto.isEmpty()
                    ? "Chance de alagamento na sua região (~11 km) nas próximas 24h: " + pct(pRegiao) + "."
                    : "Chance de algum dos " + perto.size() + " pontos de alagamento a até " + (int) raio
                      + " km alagar nas próximas 24h: " + pct(pPerto) + " (" + vezesNormal(pPerto, normalPerto) + ").";
            notificar((teste ? "[Teste] " : "") + "Risco " + nomeNivel.toLowerCase(new Locale("pt", "BR"))
                    + " de alagamento perto de você", texto + " Toque para ver.");
            if (!teste) ed.putLong("ultimo_ms", agoraMs);
        }
        ed.apply();
    }

    private void notificar(String titulo, String texto) {
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            Log.i(TAG, "sem permissão para notificar");
            return;
        }
        NotificationManager nm = getSystemService(NotificationManager.class);
        nm.createNotificationChannel(new NotificationChannel(CANAL, "Alertas de alagamento",
                NotificationManager.IMPORTANCE_HIGH));
        PendingIntent abrir = PendingIntent.getActivity(this, 0,
                new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Notification n = new Notification.Builder(this, CANAL)
                .setSmallIcon(android.R.drawable.stat_sys_warning)
                .setContentTitle(titulo)
                .setContentText(texto)
                .setStyle(new Notification.BigTextStyle().bigText(texto))
                .setContentIntent(abrir)
                .setAutoCancel(true)
                .build();
        nm.notify(1, n);
    }

    static String pct(double p) {
        return p < 0.01 ? "< 1%" : String.format(Locale.ROOT, "%.0f%%", p * 100);
    }

    /** Igual a risk.vezes_normal. */
    static String vezesNormal(double p, double normal) {
        if (normal <= 0) return "sem histórico para comparar";
        double r = p / normal;
        if (r >= 10) return String.format(Locale.ROOT, "%.0f× o normal", r);
        if (r >= 1.5) return String.format(Locale.ROOT, "%.1f× o normal", r).replace('.', ',');
        if (r >= 0.67) return "perto do normal";
        return "abaixo do normal";
    }

    private static double[] vetor(JSONArray a) throws Exception {
        double[] v = new double[a.length()];
        for (int i = 0; i < v.length; i++) v[i] = a.getDouble(i);
        return v;
    }

    private static InputStream abrir(String url) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(20000);
        c.setReadTimeout(30000);
        c.setRequestProperty("User-Agent", "alagamento-sp/1.0 (projeto academico de analise de dados)");
        if (c.getResponseCode() != 200) throw new IllegalStateException("HTTP " + c.getResponseCode());
        return c.getInputStream();
    }

    private static String ler(InputStream in) throws Exception {
        try (InputStream i = in; ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buf = new byte[16384];
            int n;
            while ((n = i.read(buf)) > 0) out.write(buf, 0, n);
            return out.toString(StandardCharsets.UTF_8.name());
        }
    }
}

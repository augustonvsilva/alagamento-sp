package br.alagamentosp.app;

import android.content.Context;
import android.content.res.AssetManager;
import android.util.Log;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HashMap;
import java.util.Map;
import java.util.Properties;

/**
 * Cache permanente dos arquivos que o app baixa da internet — é o que faz o app abrir offline.
 *
 * O Python (Pyodide), os pacotes (pandas, streamlit...), as bibliotecas do mapa e os
 * pedaços de mapa já vistos ficam gravados no armazenamento do app. Ordem de busca:
 *   1. cópia gravada no celular (files/web-cache);
 *   2. cópia que veio dentro do APK (assets/semente — ver baixarSemente no build.gradle);
 *   3. internet.
 *
 * Arquivos com versão no endereço (CDN, PyPI) nunca mudam: usa a cópia local direto.
 * Mapa e índice do PyPI podem mudar: tenta a internet e usa a cópia só sem conexão.
 * APIs de tempo, endereço e rota não passam por aqui (o Python trata a falta de internet).
 *
 * Cada arquivo só entra no cache depois de baixado por inteiro — um download interrompido
 * não deixa cópia estragada (era a causa dos erros "ModuleNotFoundError" com internet fraca).
 */
final class CacheWeb {

    private static final String TAG = "CacheWeb";

    private enum Politica { CACHE_PRIMEIRO, REDE_PRIMEIRO, SEM_CACHE }

    private final File pasta;
    private final AssetManager assets;

    CacheWeb(Context ctx) {
        pasta = new File(ctx.getFilesDir(), "web-cache");
        //noinspection ResultOfMethodCallIgnored
        pasta.mkdirs();
        assets = ctx.getAssets();
    }

    private static Politica politica(String host) {
        if (host == null) return Politica.SEM_CACHE;
        if (host.endsWith("open-meteo.com") || host.startsWith("nominatim.")
                || host.contains("osrm") || host.startsWith("routing.")) {
            return Politica.SEM_CACHE;
        }
        if (host.endsWith("tile.openstreetmap.org") || host.equals("pypi.org")) {
            return Politica.REDE_PRIMEIRO;
        }
        return Politica.CACHE_PRIMEIRO;
    }

    /** Resposta para o WebView, ou null para ele seguir pela rede normalmente. */
    WebResourceResponse responder(WebResourceRequest req) {
        if (!"GET".equalsIgnoreCase(req.getMethod())) return null;
        Map<String, String> cabReq = req.getRequestHeaders();
        if (cabReq != null && (cabReq.containsKey("Range") || cabReq.containsKey("range"))) return null;
        String url = req.getUrl().toString();
        Politica p = politica(req.getUrl().getHost());
        if (p == Politica.SEM_CACHE) return null;

        String chave = chave(url);
        if (p == Politica.CACHE_PRIMEIRO) {
            WebResourceResponse r = daCopia(chave);
            if (r != null) {
                Log.d(TAG, "copia " + url);
                return r;
            }
        }
        try {
            WebResourceResponse r = baixar(url, chave, cabReq);
            Log.d(TAG, "rede " + url);
            return r;
        } catch (IOException e) {
            Log.d(TAG, "sem rede (" + e.getClass().getSimpleName() + ") " + url);
            return daCopia(chave);  // REDE_PRIMEIRO offline: usa o que tiver; senão null
        }
    }

    /** Cópia gravada no celular ou embutida no APK. */
    private WebResourceResponse daCopia(String chave) {
        try {
            File arq = new File(pasta, chave);
            File meta = new File(pasta, chave + ".meta");
            if (arq.isFile() && meta.isFile()) {
                Properties m = new Properties();
                try (InputStream in = new FileInputStream(meta)) {
                    m.load(in);
                }
                return resposta(m.getProperty("tipo"), 200, "OK", new FileInputStream(arq));
            }
        } catch (IOException ignorado) { }
        try {
            Properties m = new Properties();
            try (InputStream in = assets.open("semente/" + chave + ".meta")) {
                m.load(in);
            }
            return resposta(m.getProperty("tipo"), 200, "OK", assets.open("semente/" + chave));
        } catch (IOException e) {
            return null;
        }
    }

    private WebResourceResponse baixar(String url, String chave, Map<String, String> cabReq) throws IOException {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(15000);
        c.setReadTimeout(60000);
        c.setInstanceFollowRedirects(true);
        if (cabReq != null) {
            for (Map.Entry<String, String> e : cabReq.entrySet()) {
                String k = e.getKey();
                // Sem Accept-Encoding: o HttpURLConnection descompacta sozinho e grava o arquivo pronto
                if (k.equalsIgnoreCase("Accept-Encoding") || k.equalsIgnoreCase("Range")) continue;
                c.setRequestProperty(k, e.getValue());
            }
        }
        int status = c.getResponseCode();
        String tipo = c.getContentType();
        if (status != 200) {
            InputStream erro = c.getErrorStream() != null ? c.getErrorStream() : vazio();
            String frase = c.getResponseMessage();
            return resposta(tipo, status, frase == null || frase.isEmpty() ? "Erro" : frase, erro);
        }

        long esperado = c.getContentLengthLong();
        File tmp = new File(pasta, chave + "." + Thread.currentThread().getId() + "." + System.nanoTime() + ".tmp");
        long total = 0;
        try (InputStream in = c.getInputStream(); OutputStream out = new FileOutputStream(tmp)) {
            byte[] buf = new byte[64 * 1024];
            int n;
            while ((n = in.read(buf)) > 0) {
                out.write(buf, 0, n);
                total += n;
            }
        } catch (IOException e) {
            //noinspection ResultOfMethodCallIgnored
            tmp.delete();
            throw e;
        }
        if (esperado >= 0 && total != esperado) {
            //noinspection ResultOfMethodCallIgnored
            tmp.delete();
            throw new IOException("download incompleto: " + total + " de " + esperado);
        }
        Properties m = new Properties();
        m.setProperty("url", url);
        m.setProperty("tipo", tipo == null ? "application/octet-stream" : tipo);
        File meta = new File(pasta, chave + ".meta");
        try (OutputStream out = new FileOutputStream(meta)) {
            m.store(out, null);
        }
        File arq = new File(pasta, chave);
        if (!tmp.renameTo(arq)) {
            //noinspection ResultOfMethodCallIgnored
            tmp.delete();
            throw new IOException("falha ao gravar " + arq);
        }
        return resposta(m.getProperty("tipo"), 200, "OK", new FileInputStream(arq));
    }

    private static WebResourceResponse resposta(String tipoCompleto, int status, String frase, InputStream corpo) {
        String tipo = tipoCompleto == null ? "application/octet-stream" : tipoCompleto;
        String mime = tipo.split(";")[0].trim();
        String charset = null;
        for (String parte : tipo.split(";")) {
            String t = parte.trim();
            if (t.toLowerCase().startsWith("charset=")) charset = t.substring(8).replace("\"", "");
        }
        if (charset == null && (mime.startsWith("text/") || mime.endsWith("javascript") || mime.endsWith("json"))) {
            charset = "utf-8";
        }
        Map<String, String> cab = new HashMap<>();
        cab.put("Access-Control-Allow-Origin", "*");
        cab.put("Cross-Origin-Resource-Policy", "cross-origin");
        cab.put("Cache-Control", "no-store");  // quem guarda é este cache, não o do WebView
        return new WebResourceResponse(mime, charset, status, frase, cab, corpo);
    }

    private static InputStream vazio() {
        return new java.io.ByteArrayInputStream(new byte[0]);
    }

    /** Nome do arquivo no cache: SHA-256 do endereço (o mesmo cálculo é usado no build.gradle). */
    static String chave(String url) {
        try {
            byte[] h = MessageDigest.getInstance("SHA-256").digest(url.getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            for (byte b : h) sb.append(String.format("%02x", b));
            return sb.toString();
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    /** Apaga as cópias gravadas no celular (as embutidas no APK continuam). */
    void limpar() {
        File[] arqs = pasta.listFiles();
        if (arqs == null) return;
        for (File f : arqs) {
            //noinspection ResultOfMethodCallIgnored
            f.delete();
        }
    }
}

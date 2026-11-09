package br.alagamentosp.app;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.location.LocationManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.webkit.GeolocationPermissions;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import java.io.IOException;
import java.io.InputStream;
import java.util.HashMap;
import java.util.Map;

/**
 * Casca nativa do app: um WebView que roda o app Streamlit (via stlite) empacotado no APK.
 *
 * Os arquivos do app ficam em assets/www e são servidos na origem segura
 * https://appassets.androidplatform.net/ (necessária para a API de geolocalização funcionar).
 * Ao abrir, o app pede a permissão de localização; o index.html usa a posição para abrir
 * direto na página "Minha região".
 */
public class MainActivity extends Activity {

    private static final String HOST = "appassets.androidplatform.net";
    private static final String INICIO = "https://" + HOST + "/";
    private static final int PEDIDO_LOCALIZACAO = 1;

    private static final Map<String, String> TIPOS = new HashMap<>();
    static {
        TIPOS.put("html", "text/html");
        TIPOS.put("js", "text/javascript");
        TIPOS.put("css", "text/css");
        TIPOS.put("json", "application/json");
        TIPOS.put("py", "text/x-python");
        TIPOS.put("svg", "image/svg+xml");
        TIPOS.put("png", "image/png");
    }

    private WebView web;
    private CacheWeb cache;
    // Pedido de geolocalização do WebView aguardando a resposta da permissão do Android
    private GeolocationPermissions.Callback geoCallback;
    private String geoOrigem;
    private boolean permissaoRespondida;

    @Override
    protected void onCreate(Bundle estado) {
        super.onCreate(estado);
        getWindow().setStatusBarColor(Color.parseColor("#1f4e79"));

        cache = new CacheWeb(this);
        web = new WebView(this);
        web.setBackgroundColor(Color.WHITE);
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setGeolocationEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setMediaPlaybackRequiresUserGesture(true);

        web.setWebViewClient(new Cliente());
        web.setWebChromeClient(new ClienteChrome());
        web.addJavascriptInterface(new Ponte(), "AppAndroid");

        // Já na abertura: pede a localização para mostrar como está a área da pessoa
        // (e, no Android 13+, a permissão de notificação para o alerta de alagamento).
        permissaoRespondida = temPermissao();
        boolean pedirNotificacao = Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
                && !getSharedPreferences(AlertaJob.PREFS, MODE_PRIVATE).getBoolean("notif_pedida", false);
        if (!permissaoRespondida || pedirNotificacao) {
            java.util.List<String> pedir = new java.util.ArrayList<>();
            if (!permissaoRespondida) {
                pedir.add(Manifest.permission.ACCESS_FINE_LOCATION);
                pedir.add(Manifest.permission.ACCESS_COARSE_LOCATION);
            }
            if (pedirNotificacao) {
                pedir.add(Manifest.permission.POST_NOTIFICATIONS);
                getSharedPreferences(AlertaJob.PREFS, MODE_PRIVATE).edit().putBoolean("notif_pedida", true).apply();
            }
            requestPermissions(pedir.toArray(new String[0]), PEDIDO_LOCALIZACAO);
        } else {
            sugerirLigarGps();
        }

        // Alerta em segundo plano: verifica o risco de hora em hora, mesmo com o app fechado
        AlertaJob.agendar(this);
        // Demonstração: adb shell am start -n br.alagamentosp.app/.MainActivity --ez testar_alerta true
        if (getIntent().getBooleanExtra("testar_alerta", false)) AlertaJob.testarAgora(this);

        if (estado != null) {
            web.restoreState(estado);
        } else {
            web.loadUrl(INICIO);
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        if (intent.getBooleanExtra("testar_alerta", false)) AlertaJob.testarAgora(this);
    }

    @Override
    protected void onSaveInstanceState(Bundle estado) {
        super.onSaveInstanceState(estado);
        web.saveState(estado);
    }

    private boolean temPermissao() {
        return checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
                || checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED;
    }

    @Override
    public void onRequestPermissionsResult(int codigo, String[] permissoes, int[] resultados) {
        if (codigo != PEDIDO_LOCALIZACAO) return;
        permissaoRespondida = true;
        boolean ok = temPermissao();
        if (geoCallback != null) {
            geoCallback.invoke(geoOrigem, ok, false);
            geoCallback = null;
        }
        if (ok) sugerirLigarGps();
    }

    /** Com a permissão dada mas a localização do aparelho desligada, oferece ligá-la. */
    private void sugerirLigarGps() {
        LocationManager lm = (LocationManager) getSystemService(LOCATION_SERVICE);
        if (lm == null || lm.isLocationEnabled()) return;
        new AlertDialog.Builder(this)
                .setTitle("Localização desligada")
                .setMessage("Ative a localização do celular para vermos o risco de alagamento na sua área.")
                .setPositiveButton("Ativar", (d, w) -> {
                    try {
                        startActivity(new Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS));
                    } catch (ActivityNotFoundException ignorado) { }
                })
                .setNegativeButton("Agora não", null)
                .show();
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    /** Funções que o index.html pode chamar (window.AppAndroid). */
    private class Ponte {
        /**
         * Apaga o cache HTTP do WebView. Usado quando um pacote Python chega corrompido (ex.: o app
         * foi fechado no meio do download) — sem isso, recarregar reaproveitaria a cópia estragada.
         */
        /** Guarda a localização do aparelho para o alerta em segundo plano (AlertaJob). */
        @JavascriptInterface
        public void salvarLocal(double lat, double lon) {
            AlertaJob.salvarLocal(MainActivity.this, lat, lon);
        }

        @JavascriptInterface
        public void limparCache() {
            cache.limpar();
            runOnUiThread(() -> web.clearCache(true));
        }
    }

    private class ClienteChrome extends WebChromeClient {
        @Override
        public void onGeolocationPermissionsShowPrompt(String origem, GeolocationPermissions.Callback cb) {
            if (temPermissao()) {
                cb.invoke(origem, true, false);
            } else if (permissaoRespondida) {
                cb.invoke(origem, false, false);  // a pessoa recusou: o app segue sem localização
            } else {
                geoOrigem = origem;  // aguarda a resposta do diálogo aberto no onCreate
                geoCallback = cb;
            }
        }
    }

    private class Cliente extends WebViewClient {
        @Override
        public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest req) {
            Uri u = req.getUrl();
            if (HOST.equals(u.getHost())) return false;
            if (!req.isForMainFrame()) return false;
            // Links externos (fontes de dados, mapas etc.) abrem no navegador do celular
            try {
                startActivity(new Intent(Intent.ACTION_VIEW, u));
            } catch (ActivityNotFoundException ignorado) { }
            return true;
        }

        @Override
        public WebResourceResponse shouldInterceptRequest(WebView v, WebResourceRequest req) {
            Uri u = req.getUrl();
            // CDN, pacotes Python, mapa: cache permanente (app offline). APIs de tempo etc.: rede normal
            if (!HOST.equals(u.getHost())) return cache.responder(req);
            String caminho = u.getPath() == null ? "" : u.getPath().replaceFirst("^/+", "");
            if (caminho.isEmpty()) caminho = "index.html";
            InputStream in = abrir(caminho);
            if (in == null && !caminho.contains(".")) {
                // Sub-URL de página do Streamlit (ex.: /minha_regiao) ao recarregar
                caminho = "index.html";
                in = abrir(caminho);
            }
            if (in == null) {
                return new WebResourceResponse("text/plain", "utf-8", 404, "Not Found",
                        new HashMap<>(), null);
            }
            String ext = caminho.substring(caminho.lastIndexOf('.') + 1).toLowerCase();
            String tipo = TIPOS.getOrDefault(ext, "application/octet-stream");
            Map<String, String> cab = new HashMap<>();
            cab.put("Cache-Control", "no-cache");
            cab.put("Access-Control-Allow-Origin", "*");
            return new WebResourceResponse(tipo, tipo.startsWith("text") ? "utf-8" : null,
                    200, "OK", cab, in);
        }

        private InputStream abrir(String caminho) {
            try {
                return getAssets().open("www/" + caminho);
            } catch (IOException e) {
                return null;
            }
        }
    }
}

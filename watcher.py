#!/usr/bin/env python3
"""
Signalstation Watcher — läuft periodisch via GitHub Actions.

Zwei Arten von Benachrichtigungen:
1. Schwellenwert-Alarme (alert_above/below/change) — wie bisher, einfach und schnell.
2. Signal-Alarme (signal_watch: true) — volle Technik-Engine (dieselbe Methodik wie in
   der Signalstation-App: Wilder-RSI, MACD, Bollinger, relative Stärke vs. Benchmark,
   Volumen), meldet "Einstieg sinnvoll" beim Übergang in ein Kaufsignal und
   "Ausstieg sinnvoll" beim Abrutschen unter die Beobachten-Schwelle — pro Asset wird
   dafür ein einfacher Positions-Status (none/entered) in state.json mitgeführt.

Beide Arten sind edge-getriggert: sie melden sich nur beim Übergang, nicht bei jedem Lauf.
"""

import json
import os
import sys
import time
from pathlib import Path

import requests
import yaml

STATE_FILE = Path(__file__).parent / "state.json"
CONFIG_FILE = Path(__file__).parent / "config.yml"

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}" if NTFY_TOPIC else None
VS_CURRENCY = os.environ.get("VS_CURRENCY", "eur")

# CoinGecko verlangt inzwischen fuer zuverlaessigen Zugriff einen kostenlosen "Demo"-API-Key
# (https://www.coingecko.com/en/api/pricing -> "Create Free Account" -> Developer Dashboard ->
# API Keys -> "+ Add New Key", kein Zahlungsmittel noetig). Ohne Key: stark gedrosselt, laut
# CoinGecko selbst nur fuer "quick prototyping" gedacht -- kann bei laengeren Historienabfragen
# mit 401 Unauthorized fehlschlagen (genau das, was den ersten Backtest-Lauf blockiert hat).
# Mit Key: 100 Anfragen/Min, 10.000/Monat, ein Jahr taegliche Historie.
COINGECKO_API_KEY = os.environ.get("COINGECKO_API_KEY", "").strip()

def coingecko_params(extra):
    """Haengt den Demo-Key als Query-Parameter an, falls gesetzt -- sonst unveraendert."""
    p = dict(extra)
    if COINGECKO_API_KEY:
        p["x_cg_demo_api_key"] = COINGECKO_API_KEY
    return p

# Optional: qualitativer Nachrichtenkontext via Gemini, rein ergaenzend zur Push-Nachricht.
# Fliesst NIEMALS in den deterministischen Score zurueck (siehe fetch_gemini_context) --
# bewusste Architekturentscheidung: Sprachmodelle sind gut in Sprache/Kontext, nicht darin,
# eine reproduzierbare, testbare Zahl zu liefern. Ohne GEMINI_API_KEY komplett inaktiv,
# kein Fehler, kein Unterschied im Verhalten.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")  # konfigurierbar, da sich
    # Modellnamen bei Google erfahrungsgemaess regelmaessig aendern -- lieber hier einmal
    # zentral anpassen als im Code danach suchen muessen.

ENTRY_SCORE = 65   # identisch zur Kaufsignal-Schwelle in der Signalstation-App
EXIT_SCORE = 40    # identisch zur Beobachten/Meiden-Schwelle
HISTORY_DAYS = 150

# Handelstage-korrekte Alternativen zu den Krypto-Defaults (siehe compute_conviction):
# 30 Kalendertage ≈ 21 Handelstage (252/365), +1 für die Index-Konvention "-N" = N-1 Perioden zurück.
STOCK_LOOKBACK_PERIODS = 22
STOCK_WEEKLY_STRIDE = 5


# ===================== INFRASTRUKTUR (Config/State/Push) =====================

def load_config():
    if not CONFIG_FILE.exists():
        print("config.yml nicht gefunden.", file=sys.stderr)
        sys.exit(1)
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_state():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)


def send_push(title, message, priority="default", tags=None):
    if not NTFY_URL:
        print(f"[ntfy uebersprungen, kein NTFY_TOPIC gesetzt] {title}: {message}")
        return
    headers = {"Title": title.encode("utf-8"), "Priority": priority}
    if tags:
        headers["Tags"] = ",".join(tags)
    try:
        resp = requests.post(NTFY_URL, data=message.encode("utf-8"), headers=headers, timeout=15)
        resp.raise_for_status()
        print(f"Push gesendet: {title}")
    except requests.RequestException as e:
        print(f"Push fehlgeschlagen ({title}): {e}", file=sys.stderr)


def fmt_price(n, currency_symbol="€"):
    if n is None:
        return "n/a"
    if n < 1:
        return f"{currency_symbol}{n:.4f}"
    if n < 10:
        return f"{currency_symbol}{n:.3f}"
    return f"{currency_symbol}{n:,.2f}"


# ===================== TECHNISCHE ENGINE (Port aus Signalstation, gleiche Methodik) =====================

def average(arr):
    return sum(arr) / len(arr)


def compute_sma(closes, period):
    if len(closes) < period:
        return None
    return average(closes[-period:])


def compute_rsi_series(closes, period=14):
    n = len(closes)
    rsi = [None] * n
    if n < period + 1:
        return rsi
    gains, losses = 0.0, 0.0
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains += diff
        else:
            losses -= diff
    avg_gain, avg_loss = gains / period, losses / period
    rsi[period] = 100 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))
    for i in range(period + 1, n):
        diff = closes[i] - closes[i - 1]
        gain = diff if diff > 0 else 0
        loss = -diff if diff < 0 else 0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        rsi[i] = 100 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))
    return rsi


def compute_ema_series(closes, period):
    n = len(closes)
    ema = [None] * n
    if n < period:
        return ema
    seed = average(closes[:period])
    ema[period - 1] = seed
    k = 2 / (period + 1)
    for i in range(period, n):
        ema[i] = closes[i] * k + ema[i - 1] * (1 - k)
    return ema


def compute_macd(closes):
    if len(closes) < 45:
        return None
    ema12 = compute_ema_series(closes, 12)
    ema26 = compute_ema_series(closes, 26)
    start_idx = 25
    macd_raw = [ema12[i] - ema26[i] for i in range(start_idx, len(closes))]
    signal_raw = compute_ema_series(macd_raw, 9)
    n = len(closes)
    macd_line, signal_line, hist = [None] * n, [None] * n, [None] * n
    for i in range(len(macd_raw)):
        macd_line[start_idx + i] = macd_raw[i]
        if signal_raw[i] is not None:
            signal_line[start_idx + i] = signal_raw[i]
            hist[start_idx + i] = macd_raw[i] - signal_raw[i]
    return {"macd_line": macd_line, "signal_line": signal_line, "hist": hist}


def compute_bollinger(closes, period=20, mult=2):
    if len(closes) < period:
        return None
    sl = closes[-period:]
    mean = average(sl)
    variance = average([(v - mean) ** 2 for v in sl])
    sd = variance ** 0.5
    return {"mean": mean, "sd": sd, "upper": mean + mult * sd, "lower": mean - mult * sd}


def resample_weekly(closes, stride=7):
    """stride=7 fuer Kalendertage (Krypto, handelt jeden Tag), stride=5 fuer Handelstage
    (Aktien, Mo-Fr) -- sonst würde ein "Wochen"-Bucket bei Aktien real ~1,4 Kalenderwochen
    umfassen statt einer echten Woche."""
    weekly = []
    for i in range(len(closes) - 1, -1, -stride):
        weekly.insert(0, closes[i])
    return weekly


def _argmin(arr):
    mi = 0
    for i in range(1, len(arr)):
        if arr[i] < arr[mi]:
            mi = i
    return mi


def _argmax(arr):
    mi = 0
    for i in range(1, len(arr)):
        if arr[i] > arr[mi]:
            mi = i
    return mi


def detect_divergence(closes, rsi_series):
    n = len(closes)
    if n < 30:
        return {"bullish": False, "bearish": False}
    price_window, rsi_window = closes[-30:], rsi_series[-30:]
    half = 15
    p1, p2 = price_window[:half], price_window[half:]
    r1, r2 = rsi_window[:half], rsi_window[half:]
    lo1, lo2 = _argmin(p1), _argmin(p2)
    hi1, hi2 = _argmax(p1), _argmax(p2)
    bullish = r1[lo1] is not None and r2[lo2] is not None and p2[lo2] < p1[lo1] and r2[lo2] > r1[lo1]
    bearish = r1[hi1] is not None and r2[hi2] is not None and p2[hi2] > p1[hi1] and r2[hi2] < r1[hi1]
    return {"bullish": bullish, "bearish": bearish}


def market_phase(price, sma20, sma50, sma100):
    if sma20 is None or sma50 is None:
        return "unklar (kurze Historie)"
    if sma100 is not None:
        if price > sma20 and sma20 > sma50 and sma50 > sma100:
            return "Aufwärtstrend (stark)"
        if price < sma50 and sma50 < sma100:
            return "Abwärtstrend (stark)"
    if price > sma50:
        return "Aufwärtstrend (moderat)"
    if price < sma50:
        return "Abwärtstrend (moderat)"
    return "Seitwärts"


def trend_score(price, sma20, sma50, sma100, macd):
    s = 0
    if sma20 is not None and sma50 is not None and sma100 is not None:
        if price > sma20 and sma20 > sma50 and sma50 > sma100:
            s = 2
        elif price > sma50:
            s = 1
        elif price < sma50 and sma50 < sma100:
            s = -2
        elif price < sma50:
            s = -1
    elif sma20 is not None and sma50 is not None:
        s = 1 if price > sma50 else (-1 if price < sma50 else 0)
    if macd and macd["hist"]:
        h = macd["hist"]
        n = len(h)
        bull_cross = bear_cross = False
        for i in range(max(1, n - 3), n):
            if h[i - 1] is None or h[i] is None:
                continue
            if h[i - 1] <= 0 and h[i] > 0:
                bull_cross = True
            if h[i - 1] >= 0 and h[i] < 0:
                bear_cross = True
        if bull_cross:
            s = min(2, s + 1)
        if bear_cross:
            s = max(-2, s - 1)
    return s


def momentum_score(rsi_latest, divergence):
    s = 0
    if rsi_latest is not None:
        if rsi_latest < 30:
            s = 2
        elif rsi_latest < 40:
            s = 1
        elif rsi_latest > 70:
            s = -2
        elif rsi_latest > 60:
            s = -1
    if divergence["bullish"]:
        s = min(2, s + 1)
    if divergence["bearish"]:
        s = max(-2, s - 1)
    return s


def vol_position_score(percent_b):
    if percent_b is None:
        return 0
    if percent_b < 0:
        return 2
    if percent_b < 0.2:
        return 1
    if percent_b > 1:
        return -2
    if percent_b > 0.8:
        return -1
    return 0


def rel_strength_score(rs):
    if rs is None:
        return 0
    if rs > 10:
        return 2
    if rs > 3:
        return 1
    if rs < -10:
        return -2
    if rs < -3:
        return -1
    return 0


def volume_score(ratio, chg24h):
    if ratio is None:
        return 0
    if ratio > 1.5 and chg24h is not None and chg24h > 0:
        return 2
    if ratio > 1.2:
        return 1
    if ratio < 0.7:
        return -1
    return 0


def compute_conviction(closes, volumes, price, chg24h, benchmark_closes, lookback_periods=31, weekly_stride=7,
                        is_self_benchmark=False):
    """Gleiche Methodik und Gewichtung wie computeAllMetrics() in der Signalstation-App:
    Trend 25% / Momentum 20% / Bollinger-Position 15% / rel. Stärke 25% / Volumen 15%.

    lookback_periods/weekly_stride sind bewusst parametrisiert: Krypto handelt an jedem
    Kalendertag (Default 31/7 = ~30 Tage / echte Woche), Aktien nur an Handelstagen
    (Mo-Fr). Mit dem Krypto-Default auf Aktiendaten angewendet würde "relative Stärke"
    in Wahrheit ~44 Kalendertage statt 30 messen, und ein "Wochen"-Bucket ~1,4 echte
    Kalenderwochen statt einer. Für Aktien werden unten kleinere, handelstage-korrekte
    Werte übergeben.

    is_self_benchmark=True: für Bitcoin selbst, wenn Bitcoin auch als Benchmark dient --
    "relative Stärke vs. sich selbst" ist immer trivial 0 und kein echter Faktor. Statt
    das stillschweigend als neutralen Punktwert einzurechnen (der 25% Gewicht verschenkt),
    wird der Faktor ausgelassen und sein Gewicht auf die anderen vier umverteilt."""
    sma20 = compute_sma(closes, 20)
    sma50 = compute_sma(closes, 50)
    sma100 = compute_sma(closes, 100) if len(closes) >= 100 else None

    rsi_series = compute_rsi_series(closes, 14)
    rsi_latest = rsi_series[-1]

    macd = compute_macd(closes)
    bb = compute_bollinger(closes, 20, 2)
    percent_b = None
    if bb and (bb["upper"] - bb["lower"]) > 0:
        percent_b = (price - bb["lower"]) / (bb["upper"] - bb["lower"])
    # bei bb["upper"] == bb["lower"] (Standardabweichung 0 -- z.B. eine komplett flache
    # Kursreihe) bleibt percent_b bewusst None statt durch Null zu teilen; vol_position_score
    # behandelt None bereits korrekt als neutral (siehe dort).

    divergence = detect_divergence(closes, rsi_series)

    rs = None
    if not is_self_benchmark and benchmark_closes and len(benchmark_closes) >= lookback_periods and len(closes) >= lookback_periods:
        coin_ret = (closes[-1] / closes[-lookback_periods] - 1) * 100
        bench_ret = (benchmark_closes[-1] / benchmark_closes[-lookback_periods] - 1) * 100
        rs = coin_ret - bench_ret

    vol_ratio = None
    if volumes and len(volumes) >= lookback_periods:
        latest_vol = volumes[-2]
        avg_vol = average(volumes[-lookback_periods:-1])
        vol_ratio = (latest_vol / avg_vol) if avg_vol > 0 else None

    weekly = resample_weekly(closes, stride=weekly_stride)
    weekly_sma10 = compute_sma(weekly, 10) if len(weekly) >= 10 else None
    weekly_trend = None
    if weekly_sma10 is not None:
        weekly_trend = "bullish" if weekly[-1] > weekly_sma10 else "bearish"

    t = trend_score(price, sma20, sma50, sma100, macd)
    m = momentum_score(rsi_latest, divergence)
    v = vol_position_score(percent_b)
    r = None if is_self_benchmark else rel_strength_score(rs)
    vo = volume_score(vol_ratio, chg24h)

    if is_self_benchmark:
        weighted = t*(0.25/0.75) + m*(0.20/0.75) + v*(0.15/0.75) + vo*(0.15/0.75)
    else:
        weighted = t * 0.25 + m * 0.20 + v * 0.15 + r * 0.25 + vo * 0.15
    conviction = round(((weighted + 2) / 4) * 100)

    if conviction >= 65:
        label, cls = "Kaufsignal", "buy"
    elif conviction >= 40:
        label, cls = "Beobachten", "watch"
    else:
        label, cls = "Meiden", "avoid"

    window = closes[-90:] if len(closes) >= 90 else closes
    low90 = min(window)
    stop_loss = low90 * 0.98

    return {
        "conviction": conviction, "label": label, "cls": cls, "rsi": rsi_latest,
        "phase": market_phase(price, sma20, sma50, sma100), "weekly_trend": weekly_trend,
        "rs": rs, "stop_loss": stop_loss, "t": t, "m": m, "v": v, "r": r, "vo": vo,
    }


# ===================== DATENABRUF =====================

def fetch_crypto_history(coin_id, vs_currency=VS_CURRENCY, days=HISTORY_DAYS, retries=1):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = coingecko_params({"vs_currency": vs_currency, "days": days, "interval": "daily"})
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=25)
            resp.raise_for_status()
            data = resp.json()
            closes = [p[1] for p in data.get("prices", [])]
            volumes = [v[1] for v in data.get("total_volumes", [])]
            return closes, volumes
        except requests.RequestException as e:
            if attempt < retries:
                time.sleep(2)
                continue
            print(f"CoinGecko-Historie fuer {coin_id} fehlgeschlagen: {e}", file=sys.stderr)
            return [], []


def fetch_crypto_simple(ids, vs_currency=VS_CURRENCY):
    if not ids:
        return {}
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = coingecko_params({"ids": ",".join(ids), "vs_currencies": vs_currency, "include_24hr_change": "true"})
    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"CoinGecko-Preisabruf fehlgeschlagen: {e}", file=sys.stderr)
        return {}
    out = {}
    for coin_id in ids:
        row = data.get(coin_id)
        if row:
            out[coin_id] = {"price": row.get(vs_currency), "chg24h": row.get(f"{vs_currency}_24h_change")}
    return out


YAHOO_HOSTS = ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]


def fetch_stock_history(symbol, days=HISTORY_DAYS, retries=1):
    """retries rotiert zwischen query1/query2.finance.yahoo.com -- beide sind offiziell
    unbestaetigte Endpunkte; GitHub-Actions-Runner-IPs sind oeffentlich bekannt und
    koennten von Yahoo eher gedrosselt werden als eine normale Heim-IP. Der Host-Wechsel
    ist kein Garant, aber ein einfacher, kostenloser erster Schritt gegen einen einzelnen
    blockierten Host."""
    params = {"range": "1y", "interval": "1d"}
    headers = {"User-Agent": "Mozilla/5.0 (compatible; SignalstationWatcher/1.0)"}
    last_error = None
    for attempt in range(retries + 1):
        host = YAHOO_HOSTS[attempt % len(YAHOO_HOSTS)]
        url = f"https://{host}/v8/finance/chart/{symbol}"
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=25)
            resp.raise_for_status()
            data = resp.json()
            result = data["chart"]["result"][0]
            quote = result["indicators"]["quote"][0]
            closes_raw = quote["close"]
            volumes_raw = quote.get("volume") or [None] * len(closes_raw)
            pairs = [(c, v) for c, v in zip(closes_raw, volumes_raw) if c is not None]
            closes = [c for c, _ in pairs]
            volumes = [v if v is not None else 0 for _, v in pairs]
            if len(closes) > days:
                closes, volumes = closes[-days:], volumes[-days:]
            meta = result["meta"]
            price = meta.get("regularMarketPrice")
            chg24h = None
            if price is not None and len(closes) >= 2:
                chg24h = ((price / closes[-2]) - 1) * 100
            return closes, volumes, price, chg24h
        except (requests.RequestException, KeyError, IndexError, TypeError) as e:
            last_error = e
            if attempt < retries:
                time.sleep(2)
                continue
            print(f"Yahoo-Finance-Historie fuer {symbol} fehlgeschlagen (zuletzt {host}): {last_error}", file=sys.stderr)
            return [], [], None, None


def fetch_stock_fundamentals(symbol):
    """P/E, Verschuldung, Marge -- rein informativ, geht NICHT in den Score ein (siehe
    Warren-Buffett-Kritik: der technische Score sagt nichts ueber den Unternehmenswert).
    Nutzt einen inoffiziellen Yahoo-Endpunkt, der sich jederzeit aendern kann -- daher
    komplett fehlertolerant: jeder Fehler gibt einfach None zurueck, bricht nie den Lauf ab."""
    for host in YAHOO_HOSTS:
        url = f"https://{host}/v10/finance/quoteSummary/{symbol}"
        params = {"modules": "defaultKeyStatistics,financialData"}
        headers = {"User-Agent": "Mozilla/5.0 (compatible; SignalstationWatcher/1.0)"}
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            result = data["quoteSummary"]["result"][0]
            stats = result.get("defaultKeyStatistics", {})
            fin = result.get("financialData", {})

            def raw(d, key):
                v = d.get(key)
                return v.get("raw") if isinstance(v, dict) else None

            return {
                "pe": raw(stats, "forwardPE") or raw(stats, "trailingPE"),
                "debt_to_equity": raw(fin, "debtToEquity"),
                "profit_margin": raw(fin, "profitMargins"),
            }
        except (requests.RequestException, KeyError, IndexError, TypeError) as e:
            print(f"Fundamentaldaten fuer {symbol} von {host} nicht verfuegbar: {e}", file=sys.stderr)
            continue
    return None


def fetch_gemini_context(symbol, name):
    """Optionaler, rein qualitativer Nachrichtenkontext ueber Gemini -- ergaenzt die Push-
    Nachricht, geht NIEMALS in den deterministischen Score ein (siehe GEMINI_API_KEY oben).

    Wichtige Einschraenkung, die hier bewusst nicht verschwiegen wird: Dieser Aufruf nutzt
    Geminis eigenes, antrainiertes Wissen -- kein Such-Grounding, kein Internetzugriff des
    Modells selbst. "Aktueller Kontext" kann also trotzdem veraltet sein. Der Prompt bittet
    das Modell deshalb explizit, Unsicherheit zuzugeben statt zu spekulieren."""
    if not GEMINI_API_KEY:
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    headers = {"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"}
    prompt = (
        f"Du bist ein nuechterner Finanz-Redakteur, kein Berater. In maximal zwei kurzen "
        f"Saetzen auf Deutsch: Was ist dir an wichtigem, aktuellem Kontext zu '{name}' "
        f"({symbol}) bekannt -- z.B. Produktentwicklungen, regulatorische Ereignisse, "
        f"grosse Nachrichten? Keine Kursprognose, keine Kauf-/Verkaufsempfehlung, nur "
        f"Fakten. Wenn dir dazu nichts Konkretes oder Aktuelles bekannt ist, sag das "
        f"ehrlich in einem Satz statt zu spekulieren."
    )
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=25)
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return text.strip()
    except (requests.RequestException, KeyError, IndexError, TypeError) as e:
        print(f"Gemini-Kontext fuer {symbol} nicht verfuegbar: {e}", file=sys.stderr)
        return None


# ===================== BEDINGUNGS-PRÜFUNG =====================

def check_thresholds(asset_key, symbol, price, chg24h, cfg, state, currency_symbol="€"):
    """Die einfachen Preis-/Prozent-Schwellenwerte von vorher — weiterhin verfügbar,
    unabhängig von signal_watch."""
    if asset_key not in state:
        state[asset_key] = {}
    checks = [
        ("above", cfg.get("alert_above"),
         price is not None and cfg.get("alert_above") is not None and price > cfg["alert_above"],
         f"über {fmt_price(cfg.get('alert_above'), currency_symbol)}"),
        ("below", cfg.get("alert_below"),
         price is not None and cfg.get("alert_below") is not None and price < cfg["alert_below"],
         f"unter {fmt_price(cfg.get('alert_below'), currency_symbol)}"),
        ("chg_above", cfg.get("alert_change_24h_above"),
         chg24h is not None and cfg.get("alert_change_24h_above") is not None and chg24h > cfg["alert_change_24h_above"],
         f"24h-Änderung über +{cfg.get('alert_change_24h_above')}%"),
        ("chg_below", cfg.get("alert_change_24h_below"),
         chg24h is not None and cfg.get("alert_change_24h_below") is not None and chg24h < cfg["alert_change_24h_below"],
         f"24h-Änderung unter {cfg.get('alert_change_24h_below')}%"),
    ]
    for check_id, threshold, is_triggered, description in checks:
        if threshold is None:
            continue
        was_triggered = state[asset_key].get(check_id, False)
        if is_triggered and not was_triggered:
            body = f"Preis: {fmt_price(price, currency_symbol)}" + (f" · 24h: {chg24h:+.2f}%" if chg24h is not None else "")
            send_push(f"{symbol}: {description}", body, priority="high", tags=["warning"])
            state[asset_key][check_id] = True
        elif not is_triggered and was_triggered:
            state[asset_key][check_id] = False


def check_signal(asset_key, symbol, closes, volumes, price, chg24h, benchmark_closes, cfg, state,
                  currency_symbol="€", lookback_periods=31, weekly_stride=7, fundamentals=None,
                  is_self_benchmark=False, name=None):
    """Volle Technik-Engine. Meldet 'Einstieg sinnvoll' beim Übergang none -> Kaufsignal
    und 'Ausstieg sinnvoll' beim Abfallen unter die Beobachten-Schwelle, solange als
    'entered' geführt. already_holding: true in config.yml startet direkt im Zustand
    'entered', ohne erst auf ein Einstiegssignal zu warten.

    lookback_periods/weekly_stride: siehe compute_conviction — für Aktien werden hier
    handelstage-korrekte Werte übergeben, nicht die Krypto-Defaults.
    fundamentals: optionales Dict (P/E, Verschuldung etc.) fuer Aktien, wird der Push-
    Nachricht angehängt, damit die Entscheidung nicht rein technisch getroffen wird.
    is_self_benchmark: True fuer Bitcoin selbst -- siehe compute_conviction.
    name: Klartextname fuer den Gemini-Kontext-Prompt (fällt auf symbol zurück).
    Gemini wird bewusst NUR aufgerufen, wenn tatsächlich ein Push versendet wird --
    nicht bei jedem Lauf, um Kosten/Kontingent zu schonen."""
    if len(closes) < 30 or price is None:
        print(f"{symbol}: zu wenig Historie/Daten fuer Signal-Check, uebersprungen")
        return

    metrics = compute_conviction(closes, volumes, price, chg24h, benchmark_closes,
                                  lookback_periods=lookback_periods, weekly_stride=weekly_stride,
                                  is_self_benchmark=is_self_benchmark)

    if asset_key not in state:
        state[asset_key] = {}
    if "signal_position" not in state[asset_key]:
        state[asset_key]["signal_position"] = "entered" if cfg.get("already_holding") else "none"

    position = state[asset_key]["signal_position"]
    conviction = metrics["conviction"]
    rsi_txt = f"RSI {metrics['rsi']:.0f} · " if metrics["rsi"] is not None else ""
    weekly_txt = f" · Wochentrend {'bullisch' if metrics['weekly_trend']=='bullish' else 'bärisch'}" if metrics["weekly_trend"] else ""
    fund_txt = ""
    if fundamentals:
        parts = []
        if fundamentals.get("pe") is not None:
            parts.append(f"KGV {fundamentals['pe']:.1f}")
        if fundamentals.get("debt_to_equity") is not None:
            parts.append(f"Verschuldung/EK {fundamentals['debt_to_equity']:.0f}%")
        if fundamentals.get("profit_margin") is not None:
            parts.append(f"Marge {fundamentals['profit_margin']*100:.1f}%")
        if parts:
            fund_txt = " · " + " · ".join(parts) + " (Fundamentaldaten, nicht Teil des Scores!)"

    def gemini_line():
        ctx = fetch_gemini_context(symbol, name or symbol)
        return f"\n\n🔎 Gemini-Kontext (ergänzend, nicht Teil des Scores): {ctx}" if ctx else ""

    if position == "none" and conviction >= ENTRY_SCORE:
        title = f"{symbol}: Einstieg sinnvoll (Score {conviction})"
        body = f"{rsi_txt}{metrics['phase']}{weekly_txt} · Preis {fmt_price(price, currency_symbol)}{fund_txt}{gemini_line()}"
        send_push(title, body, priority="high", tags=["large_green_circle", "chart_with_upwards_trend"])
        state[asset_key]["signal_position"] = "entered"
    elif position == "entered" and conviction < EXIT_SCORE:
        title = f"{symbol}: Ausstieg sinnvoll (Score {conviction})"
        body = (f"{rsi_txt}{metrics['phase']}{weekly_txt} · Preis {fmt_price(price, currency_symbol)}"
                f" · Techn. Stop {fmt_price(metrics['stop_loss'], currency_symbol)}{fund_txt}{gemini_line()}")
        send_push(title, body, priority="high", tags=["red_circle", "chart_with_downwards_trend"])
        state[asset_key]["signal_position"] = "none"

    print(f"{symbol}: Score={conviction} ({metrics['label']}), Position={state[asset_key]['signal_position']}")


# ===================== ORCHESTRIERUNG =====================

def main():
    config = load_config()
    state = load_state()

    crypto_cfg = config.get("crypto") or []
    stock_cfg = config.get("stocks") or []

    eur_symbol = "€" if VS_CURRENCY == "eur" else ("$" if VS_CURRENCY == "usd" else VS_CURRENCY.upper() + " ")

    # ---- Krypto: einfache Schwellenwerte (immer, günstig) ----
    if crypto_cfg:
        simple_prices = fetch_crypto_simple([c["id"] for c in crypto_cfg])
        for c in crypto_cfg:
            row = simple_prices.get(c["id"])
            if row:
                check_thresholds(f"crypto:{c['id']}", c.get("symbol", c["id"]).upper(),
                                  row["price"], row["chg24h"], c, state, eur_symbol)

    # ---- Krypto: Signal-Engine (nur fuer signal_watch: true, braucht Historie) ----
    signal_crypto = [c for c in crypto_cfg if c.get("signal_watch")]
    if signal_crypto:
        btc_closes, _ = fetch_crypto_history("bitcoin")
        for c in signal_crypto:
            closes, volumes = fetch_crypto_history(c["id"])
            simple = fetch_crypto_simple([c["id"]]).get(c["id"], {})
            price = simple.get("price") or (closes[-1] if closes else None)
            chg24h = simple.get("chg24h")
            check_signal(f"crypto:{c['id']}", c.get("symbol", c["id"]).upper(),
                         closes, volumes, price, chg24h, btc_closes, c, state, eur_symbol,
                         is_self_benchmark=(c["id"] == "bitcoin"), name=c.get("name", c["id"]))
            time.sleep(0.5)

    # ---- Aktien: Historie deckt sowohl Schwellenwerte als auch Signal-Engine ab ----
    signal_stocks = [s for s in stock_cfg if s.get("signal_watch")]
    spy_closes = []
    if signal_stocks:
        spy_closes, _, _, _ = fetch_stock_history("SPY")

    for s in stock_cfg:
        closes, volumes, price, chg24h = fetch_stock_history(s["symbol"])
        check_thresholds(f"stock:{s['symbol']}", s["symbol"], price, chg24h, s, state, "$")
        if s.get("signal_watch"):
            fundamentals = fetch_stock_fundamentals(s["symbol"])
            check_signal(f"stock:{s['symbol']}", s["symbol"], closes, volumes, price, chg24h,
                         spy_closes, s, state, "$",
                         lookback_periods=STOCK_LOOKBACK_PERIODS, weekly_stride=STOCK_WEEKLY_STRIDE,
                         fundamentals=fundamentals, name=s.get("name", s["symbol"]))
        time.sleep(0.5)

    save_state(state)
    print("Lauf abgeschlossen.")


if __name__ == "__main__":
    main()

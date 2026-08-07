#!/usr/bin/env python3
"""
Signalstation Briefing -- läuft zweimal täglich, durchsucht eine breite Aktien- und
Krypto-Auswahl und schreibt eine lesbare Begründung zu den stärksten Kandidaten.

Architekturprinzip (siehe watcher.py, Gemini-Kontext): die Zahl bleibt deterministisch.
compute_conviction() entscheidet, WAS ein Kandidat ist. Gemini bekommt diese fertige
Zahl plus RSI/Trend/Fundamentaldaten und erklärt sie in Worten -- es erfindet nichts
Neues, es interpretiert nur, was bereits berechnet wurde. Ohne GEMINI_API_KEY läuft
alles trotzdem, nur ohne die Prosa-Begründung (reine Kennzahlen statt Fließtext).

Wiederverwendet ausschließlich Funktionen aus watcher.py -- kein drittes Nachbauen der
Engine.
"""

import json
import sys
import time
from pathlib import Path

import requests
import yaml

sys.path.insert(0, str(Path(__file__).parent))
from watcher import (  # noqa: E402
    compute_conviction, fetch_crypto_history, fetch_stock_history, fetch_stock_fundamentals,
    fmt_price, GEMINI_API_KEY, GEMINI_MODEL, VS_CURRENCY, STOCK_LOOKBACK_PERIODS,
    STOCK_WEEKLY_STRIDE, NTFY_URL, send_push, coingecko_params,
)

CONFIG_FILE = Path(__file__).parent / "config.yml"
BRIEFING_MIN_SCORE = 65          # identisch zur Kaufsignal-Schwelle -- ein Briefing zeigt nur echte Kandidaten
BRIEFING_MAX_RESULTS = 8         # Obergrenze fuer die Gesamtliste
BRIEFING_MAX_NARRATIVES = 6      # Gemini wird nur fuer die staerksten N aufgerufen (Kosten/Kontingent)
STOCK_FOCUS_COUNT = 3            # garantierte Sichtbarkeit: die staerksten N Aktien werden immer
                                  # gezeigt, auch unterhalb der Kaufsignal-Schwelle -- Aktien schwanken
                                  # strukturell weniger als Krypto und wuerden sonst in einem
                                  # gemischten Ranking fast immer untergehen
CRYPTO_SHORTLIST_SIZE = 12       # wie viele Krypto-Kandidaten nach dem Vorfilter tief analysiert werden

DISCOVERY_EXCLUDE = {
    "tether", "usd-coin", "binance-usd", "dai", "true-usd", "usdd", "frax",
    "first-digital-usd", "paypal-usd", "ethena-usde", "usual-usd", "gemini-dollar",
    "pax-dollar", "fdusd", "terrausd", "stasis-eurs", "wrapped-steth", "weth",
    "staked-ether", "wrapped-bitcoin", "coinbase-wrapped-btc", "wrapped-eeth",
}


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ===================== KRYPTO-VORFILTER (portiert aus der App-Logik) =====================

def rel_strength_score_simple(rs):
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


def crypto_prefilter_score(coin, btc_chg30d):
    """Günstiger Vorfilter aus einem einzigen /coins/markets-Aufruf (keine Historie nötig) --
    entscheidet nur, welche ~12 Coins die teure volle Analyse bekommen. Dieselbe Logik wie
    discoveryPrefilterScore() in der App."""
    c24 = coin.get("price_change_percentage_24h_in_currency")
    c7 = coin.get("price_change_percentage_7d_in_currency")
    c30 = coin.get("price_change_percentage_30d_in_currency")

    mom = 0
    if c7 is not None and c30 is not None:
        if c7 > 0 and c30 > 0 and c24 is not None and c24 > 0:
            mom = 2
        elif c7 > 0 and c30 > 0:
            mom = 1
        elif c24 is not None and c24 > 0 and c7 < 0 and c30 < 0:
            mom = 1
        elif c7 < 0 and c30 < 0 and c24 is not None and c24 < 0:
            mom = -2
        elif c7 < 0 and c30 < 0:
            mom = -1

    rel = 0
    if c30 is not None and btc_chg30d is not None:
        rel = rel_strength_score_simple(c30 - btc_chg30d)

    turn = 0
    vol, mcap = coin.get("total_volume"), coin.get("market_cap")
    if vol and mcap:
        turnover = vol / mcap
        if turnover > 0.15:
            turn = 2
        elif turnover > 0.08:
            turn = 1
        elif turnover < 0.02:
            turn = -1

    return mom * 0.4 + rel * 0.35 + turn * 0.25


def fetch_crypto_universe(size):
    url = f"https://api.coingecko.com/api/v3/coins/markets"
    params = coingecko_params({
        "vs_currency": VS_CURRENCY, "order": "market_cap_desc", "per_page": size, "page": 1,
        "price_change_percentage": "24h,7d,30d", "sparkline": "false",
    })
    try:
        resp = requests.get(url, params=params, timeout=25)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"Krypto-Marktübersicht fehlgeschlagen: {e}", file=sys.stderr)
        return []


# ===================== GEMINI-BEGRÜNDUNG (rein erklärend, siehe Modulkopf) =====================

def generate_narrative(symbol, name, metrics, fundamentals=None):
    if not GEMINI_API_KEY:
        return None

    fund_block = ""
    if fundamentals:
        parts = []
        if fundamentals.get("pe") is not None:
            parts.append(f"KGV {fundamentals['pe']:.1f}")
        if fundamentals.get("debt_to_equity") is not None:
            parts.append(f"Verschuldung/EK {fundamentals['debt_to_equity']:.0f}%")
        if fundamentals.get("profit_margin") is not None:
            parts.append(f"Gewinnmarge {fundamentals['profit_margin']*100:.1f}%")
        if parts:
            fund_block = "Fundamentaldaten: " + ", ".join(parts) + "\n"

    weekly = "bullisch" if metrics.get("weekly_trend") == "bullish" else ("bärisch" if metrics.get("weekly_trend") == "bearish" else "unklar")
    rsi_txt = f"{metrics['rsi']:.0f}" if metrics.get("rsi") is not None else "n/a"

    prompt = (
        "Du bist ein nüchterner Finanzanalyst, kein Verkäufer. Nutze AUSSCHLIESSLICH die "
        "folgenden bereits berechneten Daten -- erfinde keine zusätzlichen Fakten, "
        "Nachrichten, Kursziele oder Ereignisse, die hier nicht stehen:\n\n"
        f"Symbol: {symbol} ({name})\n"
        f"Technischer Score: {metrics['conviction']}/100 ({metrics['label']})\n"
        f"RSI(14): {rsi_txt}\n"
        f"Trendphase: {metrics['phase']}\n"
        f"Wochentrend: {weekly}\n"
        f"{fund_block}\n"
        "Schreibe auf Deutsch in 3-4 Sätzen, warum dieser technische Aufbau aktuell "
        "interessant ist, und nenne explizit mindestens ein konkretes Risiko oder einen "
        "Unsicherheitsfaktor. Keine Kursprognose in Euro/Dollar, keine Garantie, keine "
        "Kaufaufforderung -- beschreibe die Lage, überlasse die Entscheidung."
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    headers = {"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"}
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=25)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (requests.RequestException, KeyError, IndexError, TypeError) as e:
        print(f"Gemini-Begründung für {symbol} nicht verfügbar: {e}", file=sys.stderr)
        return None


# ===================== ORCHESTRIERUNG =====================

def scan_stocks(symbols):
    """Gibt ALLE bewerteten Aktien zurueck, nicht nur die mit Score >= Schwelle --
    main() leitet daraus sowohl die echten Kandidaten als auch eine garantierte
    'Aktien im Fokus'-Sektion ab (siehe dort). Aktien schwanken strukturell weniger
    als Krypto, daher ueberschreiten sie seltener die 65er-Schwelle, obwohl sie
    fundamental relevant sein koennen -- ohne Garantie-Sektion wuerden sie in einem
    gemischten Krypto/Aktien-Ranking fast immer untergehen."""
    all_stocks = []
    for idx, symbol in enumerate(symbols):
        print(f"[Aktie {idx+1}/{len(symbols)}] {symbol} ...")
        closes, volumes, price, chg24h = fetch_stock_history(symbol)
        if len(closes) < 30 or price is None:
            print("  zu wenig Daten, übersprungen")
            time.sleep(1.0)
            continue
        metrics = compute_conviction(closes, volumes, price, chg24h, [],
                                      lookback_periods=STOCK_LOOKBACK_PERIODS,
                                      weekly_stride=STOCK_WEEKLY_STRIDE)
        print(f"  Score={metrics['conviction']} ({metrics['label']})")
        all_stocks.append({"symbol": symbol, "name": symbol, "kind": "Aktie",
                            "price": price, "metrics": metrics})
        time.sleep(1.0)
    return all_stocks


def scan_crypto(scan_size):
    universe = fetch_crypto_universe(scan_size)
    if not universe:
        return []
    btc_row = next((c for c in universe if c["id"] == "bitcoin"), None)
    btc_chg30d = btc_row.get("price_change_percentage_30d_in_currency") if btc_row else None

    ranked = sorted(
        (c for c in universe if c["id"] not in DISCOVERY_EXCLUDE),
        key=lambda c: crypto_prefilter_score(c, btc_chg30d),
        reverse=True,
    )
    shortlist = ranked[:CRYPTO_SHORTLIST_SIZE]

    btc_closes, _ = fetch_crypto_history("bitcoin")
    time.sleep(1.0)

    candidates = []
    for idx, coin in enumerate(shortlist):
        coin_id = coin["id"]
        print(f"[Krypto {idx+1}/{len(shortlist)}] {coin_id} ...")
        closes, volumes = fetch_crypto_history(coin_id)
        if len(closes) < 30:
            print("  zu wenig Historie, übersprungen")
            time.sleep(1.0)
            continue
        is_self = (coin_id == "bitcoin")
        metrics = compute_conviction(closes, volumes, coin["current_price"],
                                      coin.get("price_change_percentage_24h_in_currency"),
                                      btc_closes, is_self_benchmark=is_self)
        print(f"  Score={metrics['conviction']} ({metrics['label']})")
        if metrics["conviction"] >= BRIEFING_MIN_SCORE:
            candidates.append({"symbol": coin["symbol"].upper(), "name": coin["name"], "kind": "Krypto",
                                "price": coin["current_price"], "metrics": metrics})
        time.sleep(1.0)
    return candidates


def main():
    config = load_config()
    stock_symbols = config.get("briefing_stocks") or []
    crypto_scan_size = config.get("briefing_crypto_scan_size", 100)

    print(f"Durchsuche {len(stock_symbols)} Aktien und Top-{crypto_scan_size} Krypto nach Marktkapitalisierung.\n")

    all_stocks = scan_stocks(stock_symbols)
    stock_candidates = [c for c in all_stocks if c["metrics"]["conviction"] >= BRIEFING_MIN_SCORE]
    stock_focus = sorted(all_stocks, key=lambda c: c["metrics"]["conviction"], reverse=True)[:STOCK_FOCUS_COUNT]
    # bereits qualifizierende Aktien nicht doppelt in der Fokus-Sektion zeigen -- die stehen
    # schon prominent in der Hauptliste
    stock_focus_only = [c for c in stock_focus if c["metrics"]["conviction"] < BRIEFING_MIN_SCORE]

    crypto_candidates = scan_crypto(crypto_scan_size)
    all_candidates = sorted(stock_candidates + crypto_candidates,
                             key=lambda c: c["metrics"]["conviction"], reverse=True)
    top = all_candidates[:BRIEFING_MAX_RESULTS]

    lines = [f"# Signalstation Briefing\n", f"{len(top)} Kandidat(en) mit Score ≥ {BRIEFING_MIN_SCORE} "
             f"aus {len(stock_symbols)} Aktien und Top-{crypto_scan_size} Krypto.\n"]
    json_candidates = []  # strukturierte Fassung fuer briefing.json -- das liest die App direkt,
                           # ohne Markdown parsen zu muessen (siehe "Elon-Review": ein Ort statt vier)

    if not top:
        lines.append("Aktuell kein Titel über der Kaufsignal-Schwelle. Der Markt ändert sich laufend -- "
                      "das nächste Briefing kommt in wenigen Stunden.\n")
    else:
        for i, c in enumerate(top):
            m = c["metrics"]
            currency_symbol = "$" if c["kind"] == "Aktie" else ("€" if VS_CURRENCY == "eur" else VS_CURRENCY.upper() + " ")
            fundamentals = fetch_stock_fundamentals(c["symbol"]) if c["kind"] == "Aktie" else None
            narrative = None
            if i < BRIEFING_MAX_NARRATIVES:
                narrative = generate_narrative(c["symbol"], c["name"], m, fundamentals)

            lines.append(f"## {c['symbol']} ({c['kind']}) — Score {m['conviction']}/100, {m['label']}\n")
            lines.append(f"Preis: {fmt_price(c['price'], currency_symbol)} · {m['phase']}"
                         + (f" · RSI {m['rsi']:.0f}" if m.get("rsi") is not None else ""))
            if fundamentals and fundamentals.get("pe") is not None:
                lines.append(f"KGV: {fundamentals['pe']:.1f}"
                             + (f" · Verschuldung/EK: {fundamentals['debt_to_equity']:.0f}%" if fundamentals.get("debt_to_equity") is not None else ""))
            if narrative:
                lines.append(f"\n{narrative}\n")
            else:
                lines.append("\n(Kein Gemini-Kontext verfügbar oder GEMINI_API_KEY nicht gesetzt -- reine Kennzahlen oben.)\n")

            json_candidates.append({
                "symbol": c["symbol"], "name": c["name"], "kind": c["kind"],
                "price": c["price"], "currency": currency_symbol,
                "conviction": m["conviction"], "label": m["label"], "cls": m["cls"],
                "rsi": m.get("rsi"), "phase": m.get("phase"), "weekly_trend": m.get("weekly_trend"),
                "fundamentals": fundamentals, "narrative": narrative,
            })

    # Garantierte Sichtbarkeit fuer Aktien, unabhaengig von der 65er-Schwelle -- siehe
    # STOCK_FOCUS_COUNT oben. Kein Kaufsignal, nur "das ist aktuell am staerksten unter
    # den beobachteten Aktien", klar als solches benannt, keine Verwaesserung von
    # "Kaufsignal" als Begriff.
    json_stock_focus = []
    if stock_focus_only:
        lines.append("\n## Aktien im Fokus (unabhängig von der Kaufsignal-Schwelle)\n")
        lines.append(
            f"Aktien schwanken strukturell weniger als Krypto und überschreiten die "
            f"{BRIEFING_MIN_SCORE}er-Schwelle seltener — diese {len(stock_focus_only)} "
            f"waren aktuell die stärksten unter den {len(stock_symbols)} beobachteten, "
            f"auch wenn (noch) kein Kaufsignal vorliegt.\n"
        )
        for c in stock_focus_only:
            m = c["metrics"]
            fundamentals = fetch_stock_fundamentals(c["symbol"])
            lines.append(f"- **{c['symbol']}** — Score {m['conviction']}/100, {m['label']} · "
                         f"{fmt_price(c['price'], '$')} · {m['phase']}"
                         + (f" · RSI {m['rsi']:.0f}" if m.get("rsi") is not None else ""))
            json_stock_focus.append({
                "symbol": c["symbol"], "name": c["name"], "price": c["price"], "currency": "$",
                "conviction": m["conviction"], "label": m["label"], "cls": m["cls"],
                "rsi": m.get("rsi"), "phase": m.get("phase"), "fundamentals": fundamentals,
            })

    lines.append(
        "\n---\nKeine Anlageberatung. Alle Angaben basieren auf dem regelbasierten "
        "Signalstation-Score plus optionalem, ausdrücklich als solchem markiertem "
        "Gemini-Kontext -- keine Garantie, keine Kursprognose. Eigene Prüfung nötig."
    )

    report = "\n".join(lines)
    (Path(__file__).parent / "BRIEFING.md").write_text(report, encoding="utf-8")

    briefing_json = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "universe_size": {"stocks": len(stock_symbols), "crypto_scanned": crypto_scan_size},
        "min_score": BRIEFING_MIN_SCORE,
        "candidates": json_candidates,
        "stock_focus": json_stock_focus,  # garantierte Aktien-Sichtbarkeit, siehe oben
    }
    (Path(__file__).parent / "briefing.json").write_text(
        json.dumps(briefing_json, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    if top or stock_focus_only:
        parts = []
        if top:
            parts.append(" · ".join(f"{c['symbol']} ({c['metrics']['conviction']})" for c in top))
        if stock_focus_only:
            focus_txt = " · ".join(f"{c['symbol']} ({c['metrics']['conviction']})" for c in stock_focus_only)
            parts.append(f"📈 Aktien im Fokus: {focus_txt}")
        summary = "\n".join(parts)
        send_push(f"📋 Briefing: {len(top)} Kandidat(en)", summary, priority="default", tags=["clipboard"])
    else:
        print("Kein Kandidat über der Schwelle -- kein Push versendet, um nicht grundlos zu stören.")

    print(f"\nBRIEFING.md + briefing.json geschrieben mit {len(top)} Kandidat(en) "
          f"+ {len(stock_focus_only)} Aktien im Fokus.")


if __name__ == "__main__":
    main()

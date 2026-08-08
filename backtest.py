#!/usr/bin/env python3
"""
Signalstation Backtest — prueft die 65/40-Kaufsignal/Meiden-Schwellen und die
Faktorgewichtung (25/20/15/25/15%) tatsaechlich gegen echte Mehrjahres-Kurshistorie,
statt sie nur zu vermuten. Direkte Antwort auf den Warren-Buffett-Kritikpunkt:
"vier Backtests sind statistisch bedeutungslos, woher kommen 65/40 ueberhaupt?"

Wiederverwendet die EXAKT GLEICHEN Scoring-Funktionen wie watcher.py (und damit
dieselben wie die JS-Engine der App) -- kein drittes, potenziell abweichendes
Nachbauen der Logik.

Streng Point-in-Time: an jedem Auswertungstag i wird compute_conviction() nur mit
closes[:i+1] aufgerufen -- der Algorithmus kann nicht in die Zukunft schauen. Das ist
der Kern eines seriösen Backtests; ohne das waere jedes Ergebnis wertlos (Lookahead-Bias).

Ausgabe: REPORT.md mit Trefferquote, Rendite, Vergleich gegen Buy-and-Hold und gegen
zufaellige Einstiegszeitpunkte (Baseline -- schlaegt die Engine den Zufall ueberhaupt?).
"""

import json
import random
import statistics
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from watcher import (  # noqa: E402  -- bewusste Wiederverwendung der validierten Engine
    VS_CURRENCY, coingecko_params,
)
from simulation_core import (  # noqa: E402  -- gemeinsamer Kern, auch von stock_backtest.py genutzt
    WARMUP_DAYS, EVAL_STRIDE, max_drawdown_pct, benchmark_bearish_regime, simulate_asset,
    random_baseline, summarize, buy_and_hold_return, matched_benchmark_return,
)

# Etablierte Coins mit mehrjaehriger Historie -- bewusst keine sehr neuen Token, sonst
# waere die Historie zu kurz fuer eine aussagekraeftige Auswertung.
CRYPTO_UNIVERSE = [
    "bitcoin", "ethereum", "litecoin", "ripple", "cardano", "polkadot", "chainlink",
    "stellar", "dogecoin", "monero", "tron", "eos", "tezos", "cosmos", "vechain",
    "algorand", "aave", "uniswap", "maker", "the-graph", "solana", "avalanche-2",
]

# CoinGecko-Demo-Plan liefert laut CoinGecko explizit "one year of daily and hourly
# historical data" -- 365 ist der sichere Rueckfall-Wert fuer Coins, die nicht bei
# Binance gelistet sind (siehe BINANCE_SYMBOL_MAP unten fuer die Haupt-Historienquelle).
MAX_HISTORY_DAYS = 365
RANDOM_SEED = 42          # fuer reproduzierbare Baseline-Vergleiche

# Binances oeffentliche Klines-API: komplett schluessellos, liefert fuer die meisten
# grossen Coins mehrere Jahre taegliche Historie -- im Gegensatz zum CoinGecko-Demo-Plan,
# der nur ein Jahr hergibt. Deckt aber nur Coins ab, die bei Binance gegen USDT gelistet
# sind, deshalb als ERGAENZUNG eingebaut, nicht als Ersatz: wo verfuegbar, mehr Historie;
# sonst automatischer Ruckfall auf CoinGecko (weiterhin auf MAX_HISTORY_DAYS begrenzt).
#
# Technischer Hinweis: Binance quotiert in USDT, nicht EUR. Fuer RSI/MACD/Bollinger und
# Rendite in Prozent ist das praktisch ohne Belang -- das sind relative Kennzahlen, und
# die EUR/USD-Wechselkursschwankung faellt gegenueber der krypto-eigenen Volatilitaet
# kaum ins Gewicht.
BINANCE_SYMBOL_MAP = {
    "bitcoin": "BTCUSDT", "ethereum": "ETHUSDT", "litecoin": "LTCUSDT",
    "ripple": "XRPUSDT", "cardano": "ADAUSDT", "polkadot": "DOTUSDT",
    "chainlink": "LINKUSDT", "stellar": "XLMUSDT", "dogecoin": "DOGEUSDT",
    "monero": "XMRUSDT", "tron": "TRXUSDT", "eos": "EOSUSDT",
    "tezos": "XTZUSDT", "cosmos": "ATOMUSDT", "vechain": "VETUSDT",
    "algorand": "ALGOUSDT", "aave": "AAVEUSDT", "uniswap": "UNIUSDT",
    "maker": "MKRUSDT", "the-graph": "GRTUSDT", "solana": "SOLUSDT",
    "avalanche-2": "AVAXUSDT",
}
MAX_HISTORY_DAYS_BINANCE = 1000  # Binance liefert bis zu 1000 Kerzen pro Anfrage, keine Paginierung noetig


def fetch_binance_history(coin_id, days=MAX_HISTORY_DAYS_BINANCE):
    """Schluessellos, mehrjaehrige Historie wo verfuegbar. Gibt ([], []) zurueck, wenn der
    Coin nicht gemappt ist oder die Anfrage fehlschlaegt -- der Aufrufer faellt dann auf
    CoinGecko zurueck, kein Fehler wird nach aussen weitergereicht."""
    symbol = BINANCE_SYMBOL_MAP.get(coin_id)
    if not symbol:
        return [], []
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": "1d", "limit": min(days, 1000)}
    try:
        resp = requests.get(url, params=params, timeout=25)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list) or not data:
            return [], []
        # Kline-Format: [open_time, open, high, low, close, volume, close_time, ...]
        closes = [float(k[4]) for k in data]
        volumes = [float(k[5]) for k in data]
        return closes, volumes
    except (requests.RequestException, ValueError, IndexError, TypeError) as e:
        print(f"  Binance-Historie fuer {coin_id} nicht verfuegbar ({e})", file=sys.stderr)
        return [], []


def fetch_full_history(coin_id, days=MAX_HISTORY_DAYS, retries=2):
    binance_closes, binance_volumes = fetch_binance_history(coin_id)
    if len(binance_closes) >= WARMUP_DAYS:
        print(f"  {len(binance_closes)} Tage von Binance geladen")
        return binance_closes, binance_volumes

    print(f"  nicht auf Binance verfuegbar oder zu wenig Historie -- falle zurueck auf CoinGecko")
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = coingecko_params({"vs_currency": VS_CURRENCY, "days": days, "interval": "daily"})
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            closes = [p[1] for p in data.get("prices", [])]
            volumes = [v[1] for v in data.get("total_volumes", [])]
            return closes, volumes
        except requests.RequestException as e:
            if attempt < retries:
                time.sleep(3)
                continue
            print(f"  Historie fuer {coin_id} fehlgeschlagen: {e}", file=sys.stderr)
            return [], []



def main():
    print(f"Backtest ueber {len(CRYPTO_UNIVERSE)} Coins, bis zu {MAX_HISTORY_DAYS_BINANCE} Tage Historie "
          f"(Binance, wo gelistet) bzw. {MAX_HISTORY_DAYS} Tage (CoinGecko-Ruckfall), "
          f"Auswertung alle {EVAL_STRIDE} Tage. Das dauert eine Weile.\n")

    rng = random.Random(RANDOM_SEED)

    print("Lade Bitcoin-Historie als Benchmark...")
    btc_closes, _ = fetch_full_history("bitcoin")
    if not btc_closes:
        print("Konnte Bitcoin-Historie nicht laden -- Abbruch.", file=sys.stderr)
        sys.exit(1)
    time.sleep(1.5)

    all_trades = []
    regime_trades = []  # zweite Simulation mit Markt-Regime-Filter, gleiche Daten, kein Mehraufwand beim Abruf
    buy_hold_returns = []
    per_coin_results = []
    closes_by_coin = {}   # fuer die Zufalls-Baseline weiterverwendet, kein erneuter Netzabruf noetig

    for idx, coin_id in enumerate(CRYPTO_UNIVERSE):
        print(f"[{idx+1}/{len(CRYPTO_UNIVERSE)}] {coin_id} ...")
        closes, volumes = fetch_full_history(coin_id)
        if len(closes) < WARMUP_DAYS + EVAL_STRIDE:
            print(f"  zu wenig Historie ({len(closes)} Tage), uebersprungen")
            time.sleep(1.5)
            continue

        bench = btc_closes if coin_id != "bitcoin" else closes  # BTC braucht sich nicht selbst als Benchmark
        is_self = (coin_id == "bitcoin")
        trades = simulate_asset(coin_id, closes, volumes, bench, is_self_benchmark=is_self)
        all_trades.extend(trades)
        # zweite Simulation, exakt dieselben Kursdaten, nur mit Regime-Filter an --
        # direkter Vergleich, kein zusaetzlicher Netzabruf
        rtrades = simulate_asset(coin_id, closes, volumes, bench, is_self_benchmark=is_self,
                                  use_regime_filter=True, regime_benchmark_closes=btc_closes)
        regime_trades.extend(rtrades)
        closes_by_coin[coin_id] = closes

        bh = buy_and_hold_return(closes)
        if bh is not None:
            buy_hold_returns.append(bh)
        btc_matched = matched_benchmark_return(btc_closes, closes) if coin_id != "bitcoin" else None
        beats_btc = (bh is not None and btc_matched is not None and bh > btc_matched)

        closed = [t for t in trades if not t["closed_at_end"]]
        bh_txt = f"{bh:+.1f}%" if bh is not None else "n/a"
        print(f"  {len(closed)} abgeschlossene Trades, Buy-and-Hold ueber denselben Zeitraum: {bh_txt}")

        per_coin_results.append({
            "coin": coin_id, "trades": len(closed), "buy_hold_pct": bh,
            "btc_matched_pct": btc_matched, "beats_btc": beats_btc,
        })
        time.sleep(1.5)  # CoinGecko-Rate-Limit schonen

    engine_summary = summarize(all_trades, "Signalstation-Engine (echte Einstieg/Ausstieg-Signale)")
    regime_summary = summarize(regime_trades, "Signalstation-Engine + Markt-Regime-Filter")

    # Zufalls-Baseline: gleiche Anzahl Trades PRO COIN wie die Engine tatsaechlich gemacht hat,
    # gleiche Haltedauer-Verteilung, aber zufaellige statt signalbasierte Einstiegszeitpunkte --
    # auf denselben, bereits geladenen Kursreihen, kein erneuter Netzabruf.
    holding_pool = [t["holding_days"] for t in all_trades if not t["closed_at_end"]] or [30]
    baseline_returns = []
    trades_per_coin = {}
    for t in all_trades:
        if not t["closed_at_end"]:
            trades_per_coin[t["coin"]] = trades_per_coin.get(t["coin"], 0) + 1
    for coin_id, n_trades in trades_per_coin.items():
        coin_closes = closes_by_coin.get(coin_id)
        if not coin_closes or n_trades == 0:
            continue
        baseline_returns.extend(random_baseline(coin_closes, n_trades, holding_pool, rng))

    baseline_summary = None
    if baseline_returns:
        baseline_wins = [r for r in baseline_returns if r > 0]
        baseline_summary = {
            "n": len(baseline_returns),
            "win_rate": (len(baseline_wins) / len(baseline_returns)) * 100,
            "avg_return": statistics.mean(baseline_returns),
            "median_return": statistics.median(baseline_returns),
        }

    report_lines = []
    report_lines.append("# Signalstation Backtest-Report\n")
    report_lines.append(f"Universum: {len(CRYPTO_UNIVERSE)} Coins · Historie bis {MAX_HISTORY_DAYS_BINANCE} Tage "
                         f"(Binance, wo gelistet) bzw. {MAX_HISTORY_DAYS} Tage (CoinGecko-Rückfall) · "
                         f"Auswertungsraster alle {EVAL_STRIDE} Tage · Schwellen 65 (Einstieg) / 40 (Ausstieg)\n")

    report_lines.append("## Ergebnis: Signalstation-Engine\n")
    if engine_summary["n"] == 0:
        report_lines.append("Keine abgeschlossenen Trades im Beobachtungszeitraum.\n")
    else:
        report_lines.append(f"- Abgeschlossene Trades: **{engine_summary['n']}**")
        report_lines.append(f"- Trefferquote: **{engine_summary['win_rate']:.1f}%**")
        report_lines.append(f"- Ø Rendite pro Trade: **{engine_summary['avg_return']:+.1f}%**")
        report_lines.append(f"- Median-Rendite: {engine_summary['median_return']:+.1f}%")
        report_lines.append(f"- Beste / schlechteste Trade: {engine_summary['best']:+.1f}% / {engine_summary['worst']:+.1f}%")
        report_lines.append(f"- Streuung (Stdev): {engine_summary['stdev']:.1f} Prozentpunkte")
        report_lines.append(f"- Ø Haltedauer: {engine_summary['avg_holding_days']:.0f} Tage")
        if engine_summary["avg_max_drawdown"] is not None:
            report_lines.append(
                f"- **Ø maximaler Rücksetzer während der Position: {engine_summary['avg_max_drawdown']:.1f}%** "
                f"(schlechtester Einzelfall: {engine_summary['worst_max_drawdown']:.1f}%)"
            )
            report_lines.append(
                "  Das ist der schlimmste Zwischenstand *während* der Position, nicht die Endrendite — "
                "zeigt, wie holprig der Weg dorthin tatsächlich war, selbst wenn der Trade am Ende gewann."
            )
        if engine_summary["return_to_risk"] is not None:
            report_lines.append(
                f"- **Rendite-Risiko-Verhältnis (Ø Rendite / Streuung): {engine_summary['return_to_risk']:.2f}**"
            )
            report_lines.append(
                "  Grobe Orientierung, kein echter Sharpe-Ratio (dafür fehlt ein risikofreier Zins und "
                "eine gleichmäßige Zeitbasis) — aber besser als die Durchschnittsrendite allein zu lesen, "
                "ohne zu wissen, wie stark sie streut."
            )
        report_lines.append("")

    report_lines.append("## Experiment: Markt-Regime-Filter\n")
    report_lines.append(
        "Hypothese, unabhängig von diesen Testdaten hergeleitet (kein Overfitting-Risiko wie bei "
        "einer Gewichts-Neujustierung): Diese Engine ist im Kern ein Mean-Reversion-System — sie "
        "kauft \"überverkauft\" und wettet auf Erholung. Das funktioniert strukturell schlecht in "
        "einem anhaltenden Gesamtmarkt-Abwärtstrend. Der Filter unterdrückt neue Einstiege, "
        "solange Bitcoin selbst unter SMA50 unter SMA100 steht — Ausstiege bleiben unberührt.\n"
    )
    if regime_summary.get("n", 0) == 0:
        report_lines.append("Keine abgeschlossenen Trades mit aktivem Filter im Beobachtungszeitraum.\n")
    else:
        report_lines.append("| | Ohne Filter | Mit Regime-Filter |")
        report_lines.append("|---|---|---|")
        report_lines.append(f"| Trades | {engine_summary.get('n','–')} | {regime_summary.get('n','–')} |")
        report_lines.append(f"| Trefferquote | {engine_summary.get('win_rate',0):.1f}% | {regime_summary.get('win_rate',0):.1f}% |")
        report_lines.append(f"| Ø Rendite | {engine_summary.get('avg_return',0):+.1f}% | {regime_summary.get('avg_return',0):+.1f}% |")
        report_lines.append(f"| Ø Drawdown | {engine_summary.get('avg_max_drawdown',0):.1f}% | {regime_summary.get('avg_max_drawdown',0):.1f}% |")
        report_lines.append(f"| Rendite-Risiko-Verh. | {engine_summary.get('return_to_risk') or 0:.2f} | {regime_summary.get('return_to_risk') or 0:.2f} |")
        diff = regime_summary["avg_return"] - engine_summary["avg_return"]
        report_lines.append(f"\n**Effekt des Filters auf die Ø Rendite: {diff:+.1f} Prozentpunkte.**")
        if diff > 0:
            report_lines.append(" Der Filter half in diesem Lauf tatsächlich — trotzdem nur ein Hinweis, kein Beweis, siehe Einschränkungen unten.")
        else:
            report_lines.append(" Der Filter half in diesem Lauf NICHT — die Hypothese wäre damit für diesen Zeitraum widerlegt, nicht bestätigt. Ehrlich berichten, nicht schönreden.")
        report_lines.append("")

    report_lines.append("## Vergleich: zufällige Einstiegszeitpunkte (Baseline)\n")
    report_lines.append(
        "Dieselbe Anzahl Trades pro Coin, dieselbe Haltedauer-Verteilung wie oben, aber zufällig "
        "statt signalbasiert gewählte Einstiege. Schlägt die Engine den Zufall überhaupt?\n"
    )
    if baseline_summary:
        report_lines.append(f"- Zufalls-Trades: **{baseline_summary['n']}**")
        report_lines.append(f"- Zufalls-Trefferquote: **{baseline_summary['win_rate']:.1f}%**")
        report_lines.append(f"- Ø Zufalls-Rendite: **{baseline_summary['avg_return']:+.1f}%**")
        if engine_summary["n"] > 0:
            edge = engine_summary["avg_return"] - baseline_summary["avg_return"]
            report_lines.append(f"\n**Vorsprung der Engine ggü. Zufall: {edge:+.1f} Prozentpunkte pro Trade.**")
            if edge <= 0:
                report_lines.append(
                    "\n⚠️ Kein positiver Vorsprung gegenüber zufälligen Einstiegen in diesem Lauf — "
                    "das ist ein ernstzunehmendes Signal, dass die aktuelle Schwelle/Gewichtung in "
                    "diesem Zeitraum keinen nachweisbaren Mehrwert gegenüber Zufall hatte."
                )
        report_lines.append("")
    else:
        report_lines.append("Keine Baseline-Daten verfügbar.\n")

    report_lines.append("## Vergleich: Buy-and-Hold pro Coin\n")
    report_lines.append("| Coin | Abgeschl. Trades | Buy-and-Hold (gesamter Zeitraum) |")
    report_lines.append("|---|---|---|")
    for r in per_coin_results:
        bh_txt = f"{r['buy_hold_pct']:+.1f}%" if r["buy_hold_pct"] is not None else "n/a"
        report_lines.append(f"| {r['coin']} | {r['trades']} | {bh_txt} |")
    if buy_hold_returns:
        report_lines.append(f"\nØ Buy-and-Hold über alle Coins: **{statistics.mean(buy_hold_returns):+.1f}%**\n")

    report_lines.append("\n## Alts vs. Bitcoin\n")
    report_lines.append(
        "Direkter Test der Bitcoin-Maximalisten-These (\"Altcoins bluten strukturell gegen "
        "Bitcoin, nicht nur zufällig\"): wie viele der Altcoins hätten über exakt denselben "
        "Zeitraum eine reine Bitcoin-Position geschlagen — nicht in Dollar, sondern relativ "
        "zu BTC selbst?\n"
    )
    alt_results = [r for r in per_coin_results if r["coin"] != "bitcoin" and r["btc_matched_pct"] is not None]
    if alt_results:
        beat_count = sum(1 for r in alt_results if r["beats_btc"])
        report_lines.append(f"- Altcoins mit Daten für den Vergleich: **{len(alt_results)}**")
        report_lines.append(f"- Davon besser als Bitcoin im selben Fenster: **{beat_count} von {len(alt_results)}** "
                             f"({(beat_count/len(alt_results)*100):.0f}%)")
        report_lines.append("\n| Coin | Buy-and-Hold | Bitcoin im selben Fenster | Alt schlägt BTC? |")
        report_lines.append("|---|---|---|---|")
        for r in sorted(alt_results, key=lambda x: x["buy_hold_pct"] - x["btc_matched_pct"], reverse=True):
            diff_txt = "✅ ja" if r["beats_btc"] else "❌ nein"
            report_lines.append(
                f"| {r['coin']} | {r['buy_hold_pct']:+.1f}% | {r['btc_matched_pct']:+.1f}% | {diff_txt} |"
            )
        report_lines.append("")
    else:
        report_lines.append("Keine Daten für den Alts-vs-BTC-Vergleich verfügbar.\n")

    report_lines.append("\n## Wichtige Einschränkungen dieses Backtests\n")
    report_lines.append(
        "- Keine Gebühren, kein Slippage, keine Steuer -- reale Ergebnisse wären schlechter.\n"
        "- CoinGecko liefert je nach Coin unterschiedlich lange Historie; nicht alle Coins decken "
        "den vollen Zeitraum ab.\n"
        "- Ein Auswertungsraster von alle 3 Tagen ist ein Kompromiss, kein exaktes Live-Verhalten.\n"
        "- Die Schwellen 65/40 und die Gewichtung 25/20/15/25/15% wurden NICHT anhand dieses "
        "Backtests optimiert (das wäre Overfitting auf die Testdaten selbst) -- dieser Lauf prüft "
        "die bereits feststehenden Werte, ändert sie nicht automatisch.\n"
        "- Ein einzelner Lauf über ein bestimmtes Zeitfenster ist immer noch nur eine Stichprobe "
        "der Marktgeschichte, kein Beweis für die Zukunft."
    )

    report = "\n".join(report_lines)
    out_path = Path(__file__).parent / "REPORT.md"
    out_path.write_text(report, encoding="utf-8")

    # Rohdaten zusätzlich als JSON, falls jemand selbst weiterrechnen will
    (Path(__file__).parent / "backtest_trades.json").write_text(
        json.dumps(all_trades, indent=2), encoding="utf-8"
    )

    # Kompakte Zusammenfassung fuer die App (Track-Record-Anzeige) -- siehe Elon-Review:
    # ein oeffentlich pruefbarer Trackrecord direkt in der App statt versteckt in einem Repo.
    summary_json = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "universe_size": len(CRYPTO_UNIVERSE),
        "max_history_days": MAX_HISTORY_DAYS,
        "engine": engine_summary if engine_summary.get("n", 0) > 0 else None,
        "regime_filtered": regime_summary if regime_summary.get("n", 0) > 0 else None,
        "baseline_random": baseline_summary,
        "avg_buy_and_hold": statistics.mean(buy_hold_returns) if buy_hold_returns else None,
    }
    (Path(__file__).parent / "backtest_summary.json").write_text(
        json.dumps(summary_json, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\nFertig. Report geschrieben nach {out_path}")
    print(report)


if __name__ == "__main__":
    main()

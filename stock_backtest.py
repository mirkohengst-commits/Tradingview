#!/usr/bin/env python3
"""
Signalstation Aktien/ETF-Backtest -- prueft dieselben 65/40-Schwellen wie der Krypto-
Backtest, aber fuer Aktien und ETFs, mit SPY als Referenzmarkt statt Bitcoin.

Direkte Reaktion darauf, dass Aktien/ETFs die eigentliche Prioritaet sind, nicht Krypto.
Nutzt exakt dieselbe Simulations-Engine wie backtest.py (simulation_core.py) -- kein
drittes Nachbauen der Logik, nur eine andere Datenquelle (Yahoo Finance statt
CoinGecko/Binance) und andere Zeitfenster-Parameter (STOCK_LOOKBACK_PERIODS/
STOCK_WEEKLY_STRIDE, handelstage- statt kalendertage-korrekt, siehe watcher.py).

Yahoo Finance liefert im Gegensatz zu CoinGecko fuer die meisten Aktien/ETFs Jahrzehnte
an kostenloser, schluessselloser Historie -- das Ein-Jahr-Problem, das den Krypto-
Backtest zweimal ausgebremst hat, existiert hier praktisch nicht.
"""

import json
import random
import statistics
import sys
import time
from pathlib import Path

import requests
import yaml

sys.path.insert(0, str(Path(__file__).parent))
from watcher import STOCK_LOOKBACK_PERIODS, STOCK_WEEKLY_STRIDE  # noqa: E402
from simulation_core import (  # noqa: E402
    WARMUP_DAYS, EVAL_STRIDE, simulate_asset, random_baseline, summarize,
    buy_and_hold_return, matched_benchmark_return,
)

CONFIG_FILE = Path(__file__).parent / "config.yml"
BENCHMARK_SYMBOL = "SPY"  # S&P 500 -- Referenzmarkt fuer relative Staerke UND den Regime-Filter

# Breit gestreute ETFs zusaetzlich zu den Einzelaktien aus config.yml -- deckt
# unterschiedliche Anlageklassen/Sektoren ab, nicht nur Einzeltitel.
BACKTEST_ETFS = [
    "SPY",   # S&P 500
    "QQQ",   # Nasdaq 100
    "VTI",   # Gesamter US-Markt
    "IWM",   # Russell 2000 (Small Caps)
    "EFA",   # Entwickelte Maerkte außerhalb USA/Kanada
    "AGG",   # US-Anleihen, breit
    "GLD",   # Gold
    "DIA",   # Dow Jones
    "VNQ",   # US-Immobilien (REITs)
    "XLE",   # Energie-Sektor
]

RANDOM_SEED = 42
MAX_HISTORY_DAYS = 3650  # ~10 Jahre -- Yahoo Finance liefert das fuer die meisten Titel kostenlos


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def fetch_stock_history_deep(symbol, retries=2):
    """Mehrjaehrige Historie ueber Yahoo Finance -- im Gegensatz zu fetch_stock_history()
    in watcher.py (die bewusst nur 1 Jahr fuer den taeglichen Live-Betrieb laedt), holt
    diese Funktion hier gezielt so viel Historie wie verfuegbar (range=max)."""
    hosts = ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]
    params = {"range": "max", "interval": "1d"}
    headers = {"User-Agent": "Mozilla/5.0 (compatible; SignalstationBacktest/1.0)"}
    last_error = None
    for attempt in range(retries + 1):
        host = hosts[attempt % len(hosts)]
        url = f"https://{host}/v8/finance/chart/{symbol}"
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            result = data["chart"]["result"][0]
            quote = result["indicators"]["quote"][0]
            closes_raw = quote["close"]
            volumes_raw = quote.get("volume") or [None] * len(closes_raw)
            pairs = [(c, v) for c, v in zip(closes_raw, volumes_raw) if c is not None]
            closes = [c for c, _ in pairs]
            volumes = [v if v is not None else 0 for _, v in pairs]
            if len(closes) > MAX_HISTORY_DAYS:
                closes, volumes = closes[-MAX_HISTORY_DAYS:], volumes[-MAX_HISTORY_DAYS:]
            return closes, volumes
        except (requests.RequestException, KeyError, IndexError, TypeError) as e:
            last_error = e
            if attempt < retries:
                time.sleep(2)
                continue
            print(f"  Historie fuer {symbol} fehlgeschlagen (zuletzt {host}): {last_error}", file=sys.stderr)
            return [], []


def main():
    config = load_config()
    stock_symbols = config.get("briefing_stocks") or []
    universe = sorted(set(stock_symbols) | set(BACKTEST_ETFS))

    print(f"Aktien/ETF-Backtest ueber {len(universe)} Titel ({len(stock_symbols)} Aktien + "
          f"{len(BACKTEST_ETFS)} ETFs, {len(set(stock_symbols) & set(BACKTEST_ETFS))} Ueberschneidungen), "
          f"bis zu {MAX_HISTORY_DAYS} Tage Historie, Auswertung alle {EVAL_STRIDE} Tage. "
          f"Das dauert eine Weile.\n")

    rng = random.Random(RANDOM_SEED)

    print(f"Lade {BENCHMARK_SYMBOL}-Historie als Referenzmarkt...")
    spy_closes, _ = fetch_stock_history_deep(BENCHMARK_SYMBOL)
    if not spy_closes:
        print("Konnte SPY-Historie nicht laden -- Abbruch.", file=sys.stderr)
        sys.exit(1)
    time.sleep(1.0)

    all_trades = []
    regime_trades = []
    buy_hold_returns = []
    per_symbol_results = []
    closes_by_symbol = {}

    for idx, symbol in enumerate(universe):
        print(f"[{idx+1}/{len(universe)}] {symbol} ...")
        closes, volumes = fetch_stock_history_deep(symbol)
        if len(closes) < WARMUP_DAYS + EVAL_STRIDE:
            print(f"  zu wenig Historie ({len(closes)} Tage), uebersprungen")
            time.sleep(1.0)
            continue

        is_self = (symbol == BENCHMARK_SYMBOL)
        bench = closes if is_self else spy_closes  # SPY braucht sich nicht selbst als Benchmark-Faktor

        trades = simulate_asset(symbol, closes, volumes, bench, is_self_benchmark=is_self,
                                 lookback_periods=STOCK_LOOKBACK_PERIODS, weekly_stride=STOCK_WEEKLY_STRIDE)
        all_trades.extend(trades)

        rtrades = simulate_asset(symbol, closes, volumes, bench, is_self_benchmark=is_self,
                                  lookback_periods=STOCK_LOOKBACK_PERIODS, weekly_stride=STOCK_WEEKLY_STRIDE,
                                  use_regime_filter=True, regime_benchmark_closes=spy_closes)
        regime_trades.extend(rtrades)

        closes_by_symbol[symbol] = closes

        bh = buy_and_hold_return(closes)
        if bh is not None:
            buy_hold_returns.append(bh)

        spy_matched = matched_benchmark_return(spy_closes, closes) if not is_self else None
        beats_spy = (bh is not None and spy_matched is not None and bh > spy_matched)

        closed = [t for t in trades if not t["closed_at_end"]]
        bh_txt = f"{bh:+.1f}%" if bh is not None else "n/a"
        print(f"  {len(closed)} abgeschlossene Trades, Buy-and-Hold: {bh_txt}")

        per_symbol_results.append({
            "symbol": symbol, "is_etf": symbol in BACKTEST_ETFS, "trades": len(closed),
            "buy_hold_pct": bh, "spy_matched_pct": spy_matched, "beats_spy": beats_spy,
        })
        time.sleep(1.0)

    engine_summary = summarize(all_trades, "Signalstation-Engine (Aktien/ETFs)")
    regime_summary = summarize(regime_trades, "Signalstation-Engine + Markt-Regime-Filter (SPY)")

    holding_pool = [t["holding_days"] for t in all_trades if not t["closed_at_end"]] or [30]
    baseline_returns = []
    trades_per_symbol = {}
    for t in all_trades:
        if not t["closed_at_end"]:
            trades_per_symbol[t["coin"]] = trades_per_symbol.get(t["coin"], 0) + 1
    for symbol, n_trades in trades_per_symbol.items():
        symbol_closes = closes_by_symbol.get(symbol)
        if not symbol_closes or n_trades == 0:
            continue
        baseline_returns.extend(random_baseline(symbol_closes, n_trades, holding_pool, rng))

    baseline_summary = None
    if baseline_returns:
        baseline_wins = [r for r in baseline_returns if r > 0]
        baseline_summary = {
            "n": len(baseline_returns),
            "win_rate": (len(baseline_wins) / len(baseline_returns)) * 100,
            "avg_return": statistics.mean(baseline_returns),
        }

    # ---------------- Report ----------------
    report_lines = []
    report_lines.append("# Signalstation Aktien/ETF-Backtest-Report\n")
    report_lines.append(f"Universum: {len(universe)} Titel ({len(stock_symbols)} Aktien + {len(BACKTEST_ETFS)} ETFs) · "
                         f"Historie bis {MAX_HISTORY_DAYS} Tage (Yahoo Finance) · "
                         f"Auswertungsraster alle {EVAL_STRIDE} Tage · Referenzmarkt {BENCHMARK_SYMBOL} · "
                         f"Schwellen 65 (Einstieg) / 40 (Ausstieg) · handelstage-korrekte Zeitfenster "
                         f"({STOCK_LOOKBACK_PERIODS}/{STOCK_WEEKLY_STRIDE}, nicht die Krypto-Defaults)\n")

    report_lines.append("## Ergebnis: Signalstation-Engine (Aktien/ETFs)\n")
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
        if engine_summary["return_to_risk"] is not None:
            report_lines.append(f"- **Rendite-Risiko-Verhältnis: {engine_summary['return_to_risk']:.2f}**")
        report_lines.append("")

    report_lines.append("## Experiment: Markt-Regime-Filter (SPY statt Bitcoin)\n")
    report_lines.append(
        "Dieselbe Hypothese wie im Krypto-Backtest, hier mit SPY als Referenzmarkt: neue "
        "Einstiege werden unterdrückt, solange SPY selbst unter SMA50 unter SMA100 steht. "
        "Ausstiege bleiben unberührt.\n"
    )
    if regime_summary.get("n", 0) == 0:
        report_lines.append("Keine abgeschlossenen Trades mit aktivem Filter im Beobachtungszeitraum.\n")
    else:
        report_lines.append("| | Ohne Filter | Mit Regime-Filter |")
        report_lines.append("|---|---|---|")
        report_lines.append(f"| Trades | {engine_summary.get('n','–')} | {regime_summary.get('n','–')} |")
        report_lines.append(f"| Trefferquote | {engine_summary.get('win_rate',0):.1f}% | {regime_summary.get('win_rate',0):.1f}% |")
        report_lines.append(f"| Ø Rendite | {engine_summary.get('avg_return',0):+.1f}% | {regime_summary.get('avg_return',0):+.1f}% |")
        diff = regime_summary["avg_return"] - engine_summary["avg_return"]
        report_lines.append(f"\n**Effekt des Filters auf die Ø Rendite: {diff:+.1f} Prozentpunkte.**")
        report_lines.append(" Half in diesem Lauf." if diff > 0 else " Half in diesem Lauf NICHT.")
        report_lines.append("")

    report_lines.append("## Vergleich: zufällige Einstiegszeitpunkte (Baseline)\n")
    if baseline_summary:
        report_lines.append(f"- Zufalls-Trades: **{baseline_summary['n']}**")
        report_lines.append(f"- Zufalls-Trefferquote: **{baseline_summary['win_rate']:.1f}%**")
        report_lines.append(f"- Ø Zufalls-Rendite: **{baseline_summary['avg_return']:+.1f}%**")
        if engine_summary["n"] > 0:
            edge = engine_summary["avg_return"] - baseline_summary["avg_return"]
            report_lines.append(f"\n**Vorsprung der Engine ggü. Zufall: {edge:+.1f} Prozentpunkte pro Trade.**")
            if edge <= 0:
                report_lines.append("\n⚠️ Kein positiver Vorsprung gegenüber zufälligen Einstiegen in diesem Lauf.")
        report_lines.append("")
    else:
        report_lines.append("Keine Baseline-Daten verfügbar.\n")

    report_lines.append("## Vergleich: Buy-and-Hold pro Titel\n")
    report_lines.append("| Symbol | Typ | Trades | Buy-and-Hold |")
    report_lines.append("|---|---|---|---|")
    for r in per_symbol_results:
        bh_txt = f"{r['buy_hold_pct']:+.1f}%" if r["buy_hold_pct"] is not None else "n/a"
        typ = "ETF" if r["is_etf"] else "Aktie"
        report_lines.append(f"| {r['symbol']} | {typ} | {r['trades']} | {bh_txt} |")
    if buy_hold_returns:
        report_lines.append(f"\nØ Buy-and-Hold über alle Titel: **{statistics.mean(buy_hold_returns):+.1f}%**\n")

    report_lines.append("\n## Einzeltitel vs. SPY\n")
    non_spy = [r for r in per_symbol_results if r["symbol"] != BENCHMARK_SYMBOL and r["spy_matched_pct"] is not None]
    if non_spy:
        beat_count = sum(1 for r in non_spy if r["beats_spy"])
        report_lines.append(f"- Titel mit Daten für den Vergleich: **{len(non_spy)}**")
        report_lines.append(f"- Davon besser als SPY im selben Fenster: **{beat_count} von {len(non_spy)}** "
                             f"({(beat_count/len(non_spy)*100):.0f}%)\n")

    report_lines.append(
        "\n## Wichtige Einschränkungen dieses Backtests\n"
        "- Keine Gebühren, kein Slippage, keine Steuer -- reale Ergebnisse wären schlechter.\n"
        "- Aktien werden nur wochentags gehandelt; die handelstage-korrekten Zeitfenster "
        "(22/5 statt 31/7) gleichen das aus, siehe Universum-Zeile oben.\n"
        "- Ein Auswertungsraster von alle 3 Tagen ist ein Kompromiss, kein exaktes Live-Verhalten.\n"
        "- Die Schwellen 65/40 und die Gewichtung 25/20/15/25/15% wurden NICHT anhand dieses "
        "Backtests optimiert -- dieser Lauf prüft die bereits feststehenden Werte.\n"
        "- Ein einzelner Lauf ist weiterhin nur eine Stichprobe der Marktgeschichte."
    )

    report = "\n".join(report_lines)
    (Path(__file__).parent / "STOCK_REPORT.md").write_text(report, encoding="utf-8")

    (Path(__file__).parent / "stock_backtest_trades.json").write_text(
        json.dumps(all_trades, indent=2), encoding="utf-8"
    )

    summary_json = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "universe_size": len(universe),
        "max_history_days": MAX_HISTORY_DAYS,
        "engine": engine_summary if engine_summary.get("n", 0) > 0 else None,
        "regime_filtered": regime_summary if regime_summary.get("n", 0) > 0 else None,
        "baseline_random": baseline_summary,
        "avg_buy_and_hold": statistics.mean(buy_hold_returns) if buy_hold_returns else None,
    }
    (Path(__file__).parent / "stock_backtest_summary.json").write_text(
        json.dumps(summary_json, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\nFertig. Report geschrieben nach STOCK_REPORT.md")
    print(report)


if __name__ == "__main__":
    main()

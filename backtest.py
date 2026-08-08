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
    ENTRY_SCORE, EXIT_SCORE, compute_conviction, compute_sma, VS_CURRENCY, coingecko_params,
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
WARMUP_DAYS = 150         # Mindesthistorie, bevor die volle Engine ueberhaupt bewertet wird
EVAL_STRIDE = 3           # nur jeden 3. Tag auswerten -- Signale aendern sich nicht stuendlich,
                           # spart ~3x Rechenzeit ohne die Aussagekraft nennenswert zu verringern
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


def max_drawdown_pct(price_path):
    """Größter Rückgang vom bisherigen Höchststand innerhalb einer Preisreihe, in Prozent
    (negativ oder 0). Nutzt die tatsächlichen Tagesschlusskurse zwischen Einstieg und
    Ausstieg -- nicht nur die EVAL_STRIDE-Stichprobenpunkte -- damit ein Rücksetzer
    zwischen zwei Auswertungstagen nicht unsichtbar bleibt. Ohne das würde ein Trade mit
    +20% Endrendite genauso aussehen wie einer, der unterwegs -50% durchgemacht hat,
    bevor er sich erholte -- ein entscheidender Unterschied für jeden, der die Position
    tatsächlich hätte halten müssen."""
    if not price_path:
        return 0.0
    peak = price_path[0]
    worst = 0.0
    for p in price_path:
        if p > peak:
            peak = p
        dd = (p - peak) / peak * 100
        if dd < worst:
            worst = dd
    return worst


def btc_bearish_regime(btc_closes_window):
    """Markt-Regime-Filter: True, wenn Bitcoin selbst in einem bestaetigten starken
    Abwaertstrend steckt (Kurs < SMA50 < SMA100). Diese Engine ist im Kern ein Mean-
    Reversion-System (kauft "ueberverkauft", wettet auf Erholung) -- das funktioniert
    strukturell schlecht, wenn der Gesamtmarkt in einem anhaltenden Abwaertstrend steckt,
    weil "ueberverkauft" dort oft nicht "Boden" bedeutet, sondern nur "noch nicht ganz
    unten". Bewusst unabhaengig vom einzelnen Coin-Score, unabhaengig von diesem
    speziellen Backtest-Datensatz kalibriert (keine Overfitting-Gefahr wie bei einer
    Gewichts-Neujustierung anhand derselben Trades)."""
    sma50 = compute_sma(btc_closes_window, 50)
    sma100 = compute_sma(btc_closes_window, 100)
    if sma50 is None or sma100 is None:
        return False  # zu wenig Historie -> Filter greift konservativ nicht ein
    price = btc_closes_window[-1]
    return price < sma50 < sma100


def simulate_coin(coin_id, closes, volumes, benchmark_closes, use_regime_filter=False, btc_closes=None):
    """Läuft Tag für Tag (im EVAL_STRIDE-Raster) durch die Historie, wendet dieselbe
    Einstieg/Ausstieg-Zustandsmaschine wie check_signal() in watcher.py an, und
    protokolliert jeden abgeschlossenen Trade. Streng point-in-time: closes[:i+1].

    use_regime_filter=True: unterdrueckt NEUE Einstiege, solange Bitcoin selbst im
    Abwaertstrend steckt (siehe btc_bearish_regime) -- Ausstiege bleiben davon unberuehrt,
    die sollen weiterhin jederzeit greifen koennen. btc_closes muss übergeben werden,
    wenn der Filter aktiv ist (fuer Bitcoin selbst ist das identisch zu 'closes')."""
    trades = []
    position = None  # None oder {"entry_idx","entry_price"}
    n = len(closes)
    is_self_benchmark = (coin_id == "bitcoin")  # siehe compute_conviction: BTC braucht sich nicht selbst als Benchmark-Faktor
    btc_ref = btc_closes if btc_closes is not None else closes

    for i in range(WARMUP_DAYS, n, EVAL_STRIDE):
        window_closes = closes[: i + 1]
        window_volumes = volumes[: i + 1] if volumes else []
        window_bench = benchmark_closes[: i + 1] if benchmark_closes else []
        price = closes[i]
        chg24h = ((closes[i] / closes[i - 1]) - 1) * 100 if i > 0 else None

        metrics = compute_conviction(window_closes, window_volumes, price, chg24h, window_bench,
                                      is_self_benchmark=is_self_benchmark)
        score = metrics["conviction"]

        regime_blocks_entry = False
        if use_regime_filter and i < len(btc_ref):
            regime_blocks_entry = btc_bearish_regime(btc_ref[: i + 1])

        if position is None and score >= ENTRY_SCORE and not regime_blocks_entry:
            position = {
                "entry_idx": i, "entry_price": price,
                # Teilwerte beim Einstieg -- fuer analyze_backtest.py (Korrelationsanalyse,
                # welcher Faktor tatsaechlich mit dem Ergebnis zusammenhaengt)
                "entry_t": metrics["t"], "entry_m": metrics["m"], "entry_v": metrics["v"],
                "entry_r": metrics["r"], "entry_vo": metrics["vo"],
            }
        elif position is not None and score < EXIT_SCORE:
            trades.append({
                "coin": coin_id,
                "entry_idx": position["entry_idx"], "entry_price": position["entry_price"],
                "exit_idx": i, "exit_price": price,
                "return_pct": (price / position["entry_price"] - 1) * 100,
                "holding_days": i - position["entry_idx"],
                "closed_at_end": False,
                "entry_t": position["entry_t"], "entry_m": position["entry_m"],
                "entry_v": position["entry_v"], "entry_r": position["entry_r"],
                "entry_vo": position["entry_vo"],
                "max_drawdown_pct": max_drawdown_pct(closes[position["entry_idx"]: i + 1]),
            })
            position = None

    # offene Position am Ende der Historie sauber abschliessen, aber separat markiert --
    # zaehlt nicht in die "echte" Trefferquote, weil kein echtes Ausstiegssignal vorlag.
    if position is not None:
        trades.append({
            "coin": coin_id,
            "entry_idx": position["entry_idx"], "entry_price": position["entry_price"],
            "exit_idx": n - 1, "exit_price": closes[-1],
            "return_pct": (closes[-1] / position["entry_price"] - 1) * 100,
            "holding_days": (n - 1) - position["entry_idx"],
            "closed_at_end": True,
            "entry_t": position["entry_t"], "entry_m": position["entry_m"],
            "entry_v": position["entry_v"], "entry_r": position["entry_r"],
            "entry_vo": position["entry_vo"],
            "max_drawdown_pct": max_drawdown_pct(closes[position["entry_idx"]:]),
        })

    return trades


def random_baseline(closes, n_entries, holding_days_pool, rng):
    """Fairer Vergleichsmassstab: dieselbe Anzahl Trades, dieselbe Verteilung der
    Haltedauer, aber zufaellige statt signalbasierte Einstiegszeitpunkte. Schlaegt die
    Engine das, oder haette man genauso gut wuerfeln koennen?"""
    if not closes or n_entries == 0:
        return []
    n = len(closes)
    results = []
    for _ in range(n_entries):
        hold = rng.choice(holding_days_pool) if holding_days_pool else 30
        max_start = n - hold - 1
        if max_start <= WARMUP_DAYS:
            continue
        start = rng.randint(WARMUP_DAYS, max_start)
        end = start + hold
        results.append((closes[end] / closes[start] - 1) * 100)
    return results


def summarize(trades, label):
    closed = [t for t in trades if not t["closed_at_end"]]
    returns = [t["return_pct"] for t in closed]
    wins = [r for r in returns if r > 0]
    holding = [t["holding_days"] for t in closed]
    drawdowns = [t["max_drawdown_pct"] for t in closed if t.get("max_drawdown_pct") is not None]

    if not returns:
        return {"label": label, "n": 0}

    stdev = statistics.stdev(returns) if len(returns) > 1 else 0
    avg_return = statistics.mean(returns)

    return {
        "label": label,
        "n": len(returns),
        "win_rate": (len(wins) / len(returns)) * 100,
        "avg_return": avg_return,
        "median_return": statistics.median(returns),
        "best": max(returns),
        "worst": min(returns),
        "stdev": stdev,
        "avg_holding_days": statistics.mean(holding) if holding else 0,
        # Risiko-Kennzahlen (Damodaran-Review): eine Endrendite allein sagt nichts darüber,
        # wie holprig der Weg dorthin war, und nichts über Rendite im Verhältnis zum Risiko.
        "avg_max_drawdown": statistics.mean(drawdowns) if drawdowns else None,
        "worst_max_drawdown": min(drawdowns) if drawdowns else None,
        "return_to_risk": (avg_return / stdev) if stdev > 0 else None,
    }


def buy_and_hold_return(closes):
    if len(closes) < 2:
        return None
    return (closes[-1] / closes[WARMUP_DAYS] - 1) * 100 if len(closes) > WARMUP_DAYS else None


def btc_matched_return(btc_closes, coin_closes):
    """Bitcoins Buy-and-Hold-Rendite ueber DIESELBE ANZAHL Perioden wie der Coin, ausgerichtet
    vom jeweils letzten (aktuellsten) Datenpunkt beider Reihen aus -- fuer einen fairen
    'Alt vs. BTC im selben Fenster'-Vergleich, auch wenn Coins unterschiedlich lange
    Historie bei CoinGecko haben."""
    span = len(coin_closes) - WARMUP_DAYS
    if span <= 0 or len(btc_closes) <= span:
        return None
    return (btc_closes[-1] / btc_closes[-(span + 1)] - 1) * 100


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
        trades = simulate_coin(coin_id, closes, volumes, bench)
        all_trades.extend(trades)
        # zweite Simulation, exakt dieselben Kursdaten, nur mit Regime-Filter an --
        # direkter Vergleich, kein zusaetzlicher Netzabruf
        rtrades = simulate_coin(coin_id, closes, volumes, bench, use_regime_filter=True, btc_closes=btc_closes)
        regime_trades.extend(rtrades)
        closes_by_coin[coin_id] = closes

        bh = buy_and_hold_return(closes)
        if bh is not None:
            buy_hold_returns.append(bh)
        btc_matched = btc_matched_return(btc_closes, closes) if coin_id != "bitcoin" else None
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

"""
Signalstation -- gemeinsamer Simulations-Kern fuer Backtests.

Wird sowohl von backtest.py (Krypto) als auch stock_backtest.py (Aktien/ETFs) genutzt.
Bewusst hier ausgelagert statt in beiden Skripten separat zu pflegen -- zwei Kopien
derselben Logik driften irgendwann unbemerkt auseinander, genau das Problem, das dieses
Projekt bei der JS/Python-Engine-Konsistenz von Anfang an vermeiden wollte.

Enthaelt KEINE Datenabruf-Funktionen (die sind Krypto- bzw. Aktien-spezifisch, bleiben in
den jeweiligen Skripten) -- nur die Simulation, Statistik und den Regime-Filter, die fuer
beide Anlageklassen identisch funktionieren.
"""

import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from watcher import ENTRY_SCORE, EXIT_SCORE, compute_conviction, compute_sma  # noqa: E402

WARMUP_DAYS = 150   # Mindesthistorie, bevor die volle Engine ueberhaupt bewertet wird
EVAL_STRIDE = 3     # nur jeden 3. Tag auswerten -- Signale aendern sich nicht taeglich,
                     # spart Rechenzeit ohne die Aussagekraft nennenswert zu verringern


def max_drawdown_pct(price_path):
    """Größter Rückgang vom bisherigen Höchststand innerhalb einer Preisreihe, in Prozent
    (negativ oder 0). Nutzt die tatsächlichen Tagesschlusskurse zwischen Einstieg und
    Ausstieg -- nicht nur die EVAL_STRIDE-Stichprobenpunkte -- damit ein Rücksetzer
    zwischen zwei Auswertungstagen nicht unsichtbar bleibt."""
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


def benchmark_bearish_regime(benchmark_closes_window):
    """Markt-Regime-Filter: True, wenn der Referenzmarkt (Bitcoin bei Krypto, SPY bei
    Aktien/ETFs) selbst in einem bestaetigten starken Abwaertstrend steckt
    (Kurs < SMA50 < SMA100). Diese Engine ist im Kern ein Mean-Reversion-System (kauft
    "ueberverkauft", wettet auf Erholung) -- das funktioniert strukturell schlecht, wenn
    der Gesamtmarkt in einem anhaltenden Abwaertstrend steckt. Unabhaengig vom einzelnen
    Score kalibriert, nicht anhand eines bestimmten Backtest-Datensatzes (kein
    Overfitting-Risiko wie bei einer Gewichts-Neujustierung)."""
    sma50 = compute_sma(benchmark_closes_window, 50)
    sma100 = compute_sma(benchmark_closes_window, 100)
    if sma50 is None or sma100 is None:
        return False  # zu wenig Historie -> Filter greift konservativ nicht ein
    price = benchmark_closes_window[-1]
    return price < sma50 < sma100


def simulate_asset(asset_id, closes, volumes, benchmark_closes, is_self_benchmark=False,
                    lookback_periods=31, weekly_stride=7,
                    use_regime_filter=False, regime_benchmark_closes=None):
    """Läuft Tag für Tag (im EVAL_STRIDE-Raster) durch die Historie, wendet dieselbe
    Einstieg/Ausstieg-Zustandsmaschine wie check_signal() in watcher.py an, und
    protokolliert jeden abgeschlossenen Trade. Streng point-in-time: closes[:i+1].

    lookback_periods/weekly_stride: siehe compute_conviction -- Krypto-Default 31/7
    (Kalendertage), fuer Aktien/ETFs werden STOCK_LOOKBACK_PERIODS/STOCK_WEEKLY_STRIDE
    (22/5, handelstage-korrekt) uebergeben.

    is_self_benchmark: True, wenn dieses Asset gleichzeitig der Referenzmarkt ist
    (Bitcoin bei Krypto, SPY bei Aktien) -- siehe compute_conviction.

    use_regime_filter=True: unterdrueckt NEUE Einstiege, solange der Referenzmarkt im
    Abwaertstrend steckt -- Ausstiege bleiben davon unberuehrt, die sollen weiterhin
    jederzeit greifen koennen. regime_benchmark_closes muss uebergeben werden, wenn der
    Filter aktiv ist."""
    trades = []
    position = None
    n = len(closes)
    regime_ref = regime_benchmark_closes if regime_benchmark_closes is not None else closes

    for i in range(WARMUP_DAYS, n, EVAL_STRIDE):
        window_closes = closes[: i + 1]
        window_volumes = volumes[: i + 1] if volumes else []
        window_bench = benchmark_closes[: i + 1] if benchmark_closes else []
        price = closes[i]
        chg24h = ((closes[i] / closes[i - 1]) - 1) * 100 if i > 0 else None

        metrics = compute_conviction(window_closes, window_volumes, price, chg24h, window_bench,
                                      is_self_benchmark=is_self_benchmark,
                                      lookback_periods=lookback_periods, weekly_stride=weekly_stride)
        score = metrics["conviction"]

        regime_blocks_entry = False
        if use_regime_filter and i < len(regime_ref):
            regime_blocks_entry = benchmark_bearish_regime(regime_ref[: i + 1])

        if position is None and score >= ENTRY_SCORE and not regime_blocks_entry:
            position = {
                "entry_idx": i, "entry_price": price,
                "entry_t": metrics["t"], "entry_m": metrics["m"], "entry_v": metrics["v"],
                "entry_r": metrics["r"], "entry_vo": metrics["vo"],
            }
        elif position is not None and score < EXIT_SCORE:
            trades.append({
                "coin": asset_id,
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

    if position is not None:
        trades.append({
            "coin": asset_id,
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
    Haltedauer, aber zufaellige statt signalbasierte Einstiegszeitpunkte."""
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
        "avg_max_drawdown": statistics.mean(drawdowns) if drawdowns else None,
        "worst_max_drawdown": min(drawdowns) if drawdowns else None,
        "return_to_risk": (avg_return / stdev) if stdev > 0 else None,
    }


def buy_and_hold_return(closes):
    if len(closes) < 2:
        return None
    return (closes[-1] / closes[WARMUP_DAYS] - 1) * 100 if len(closes) > WARMUP_DAYS else None


def matched_benchmark_return(benchmark_closes, asset_closes):
    """Referenzmarkt-Rendite (Bitcoin bzw. SPY) ueber DIESELBE ANZAHL Perioden wie das
    Asset, ausgerichtet vom jeweils letzten Datenpunkt beider Reihen aus -- fuer einen
    fairen Vergleich, auch wenn Assets unterschiedlich lange Historie haben."""
    span = len(asset_closes) - WARMUP_DAYS
    if span <= 0 or len(benchmark_closes) <= span:
        return None
    return (benchmark_closes[-1] / benchmark_closes[-(span + 1)] - 1) * 100


# ===================== TRENDFOLGE-ALTERNATIVE (Buffett-Kritik-Antwort) =====================
#
# Der Haupt-Score ist im Kern ein Mean-Reversion-System: er kauft "ueberverkauft" (RSI
# niedrig, Kurs nahe unterem Bollinger-Band) und wettet auf Erholung. Zwei unabhaengige
# Backtests (Krypto-Baermarkt, Aktien-Jahrzehnt-Bullenmarkt) zeigen: das System bleibt
# hinter zufaelligen Einstiegen zurueck, UND es kauft Qualitaets-Compounder wie AAPL,
# MSFT, JNJ so gut wie nie, weil die selten "ueberverkauft" genug werden -- sie steigen
# einfach stetig, statt sich staendig zu erholen.
#
# Diese Alternative ist bewusst das Gegenteil: Trendfolge statt Mean-Reversion. Kauft,
# wenn ein Aufwaertstrend bereits bestaetigt UND gesund ist (nicht ueberhitzt), verkauft,
# wenn der Trend bricht -- unabhaengig von RSI/Bollinger. Klassische, etablierte Logik
# (kein neues, ungeprueftes Konzept), aber im Signalstation-Kontext ein echter zweiter
# Signaltyp, kein Nachjustieren derselben Gewichte.

def trend_following_score(closes, extend_limit_pct=15.0):
    """0-100, hoeher = gesuenderer, bestaetigter Aufwaertstrend. Kein RSI, kein Bollinger,
    keine Mean-Reversion-Komponente -- rein SMA-basierte Trendbestaetigung.

    extend_limit_pct: wie weit der Kurs maximal ueber dem SMA50 liegen darf, um noch als
    "gesund" zu gelten (Standard 15%) -- verhindert, in einen bereits stark ueberhitzten,
    ueberkauften Ausbruch zu kaufen, ohne dafuer RSI zu benoetigen."""
    sma20 = compute_sma(closes, 20)
    sma50 = compute_sma(closes, 50)
    sma100 = compute_sma(closes, 100)
    if sma50 is None or sma100 is None:
        return 0
    price = closes[-1]

    # Basis: ist der Trend ueberhaupt etabliert?
    if price > sma50 > sma100:
        base = 2  # voll bestaetigter Aufwaertstrend
    elif price > sma100:
        base = 1  # schwaecher, aber noch positiv
    elif price < sma50 < sma100:
        base = -2  # bestaetigter Abwaertstrend
    else:
        base = -1

    # Ueberhitzungs-Abzug: zu weit ueber SMA50 gelaufen = eher ein spaeter, riskanter
    # Einstieg als ein gesunder frueher Trend
    extension_pct = ((price - sma50) / sma50) * 100 if sma50 else 0
    if extension_pct > extend_limit_pct * 2:
        base -= 1  # deutlich ueberhitzt
    elif extension_pct > extend_limit_pct:
        base -= 0.5  # leicht ueberhitzt

    base = max(-2, min(2, base))
    return round(((base + 2) / 4) * 100)


def simulate_trend_following(asset_id, closes, entry_score=65, exit_score=40):
    """Eigene, einfachere Zustandsmaschine als simulate_asset() -- bewusst getrennt
    gehalten, weil dieser Signaltyp konzeptionell etwas anderes ist (Trendfolge statt
    Mean-Reversion) und nicht denselben 5-Faktoren-Score nutzt. Gleiche Trade-Struktur
    (entry_idx, exit_idx, return_pct, max_drawdown_pct, ...) fuer direkte Vergleichbarkeit
    mit simulate_asset() in Reports."""
    trades = []
    position = None
    n = len(closes)

    for i in range(WARMUP_DAYS, n, EVAL_STRIDE):
        window_closes = closes[: i + 1]
        price = closes[i]
        score = trend_following_score(window_closes)

        if position is None and score >= entry_score:
            position = {"entry_idx": i, "entry_price": price}
        elif position is not None and score < exit_score:
            trades.append({
                "coin": asset_id,
                "entry_idx": position["entry_idx"], "entry_price": position["entry_price"],
                "exit_idx": i, "exit_price": price,
                "return_pct": (price / position["entry_price"] - 1) * 100,
                "holding_days": i - position["entry_idx"],
                "closed_at_end": False,
                "max_drawdown_pct": max_drawdown_pct(closes[position["entry_idx"]: i + 1]),
            })
            position = None

    if position is not None:
        trades.append({
            "coin": asset_id,
            "entry_idx": position["entry_idx"], "entry_price": position["entry_price"],
            "exit_idx": n - 1, "exit_price": closes[-1],
            "return_pct": (closes[-1] / position["entry_price"] - 1) * 100,
            "holding_days": (n - 1) - position["entry_idx"],
            "closed_at_end": True,
            "max_drawdown_pct": max_drawdown_pct(closes[position["entry_idx"]:]),
        })

    return trades

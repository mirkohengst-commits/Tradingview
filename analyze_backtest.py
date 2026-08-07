#!/usr/bin/env python3
"""
Signalstation -- Faktor-Analyse des Backtests.

Liest backtest_trades.json (von backtest.py erzeugt) und prüft: welcher der fünf
Scoring-Faktoren (Trend, Momentum, Bollinger-Position, relative Stärke, Volumen) hing
beim Einstieg tatsächlich mit dem späteren Handelsergebnis zusammen?

Bewusst KEIN neuronales Netz, kein Machine-Learning-Modell. Bei ein paar hundert Trades
aus 22 Coins wäre jedes trainierte Modell fast garantiert überangepasst -- es würde
Rauschen in den Daten auswendig lernen, keine echte Struktur. Eine einfache Pearson-
Korrelation ist hier nicht die einfachere Wahl aus Bequemlichkeit, sondern die ehrlichere:
sie überbehauptet nichts, was die Datenmenge nicht hergibt.

Wichtig: Dieses Skript SCHLÄGT KEINE NEUEN GEWICHTE VOR und ändert nichts automatisch.
Es liefert eine Diagnose zum Lesen und selbst Entscheiden.
"""

import json
import statistics
import sys
from pathlib import Path

FACTORS = ["entry_t", "entry_m", "entry_v", "entry_r", "entry_vo"]
FACTOR_LABELS = {
    "entry_t": "Trend (25%)",
    "entry_m": "Momentum (20%)",
    "entry_v": "Bollinger-Position (15%)",
    "entry_r": "Relative Stärke (25%)",
    "entry_vo": "Volumen (15%)",
}
MIN_TRADES_FOR_ANY_CLAIM = 30   # unter dieser Schwelle wird explizit "zu wenig Daten" ausgegeben,
                                 # keine Korrelationszahl mit falscher Praezision vorgetaeuscht


def pearson(xs, ys):
    """Pearson-Korrelationskoeffizient, reine Python-Standardbibliothek (keine
    zusaetzliche Abhaengigkeit fuer eine einzelne Kennzahl)."""
    n = len(xs)
    if n < 2:
        return None
    mean_x, mean_y = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = sum((x - mean_x) ** 2 for x in xs)
    den_y = sum((y - mean_y) ** 2 for y in ys)
    if den_x == 0 or den_y == 0:
        return None  # ein Faktor ohne jede Streuung (z.B. immer 0) hat keine definierte Korrelation
    return num / ((den_x * den_y) ** 0.5)


def analyze(trades):
    closed = [t for t in trades if not t.get("closed_at_end") and all(t.get(f) is not None for f in FACTORS)]
    n = len(closed)

    result = {"n_trades": n, "factors": {}}
    if n < MIN_TRADES_FOR_ANY_CLAIM:
        result["insufficient"] = True
        return result

    returns = [t["return_pct"] for t in closed]
    wins = [t for t in closed if t["return_pct"] > 0]
    losses = [t for t in closed if t["return_pct"] <= 0]

    for f in FACTORS:
        values = [t[f] for t in closed]
        corr = pearson(values, returns)
        win_mean = statistics.mean([t[f] for t in wins]) if wins else None
        loss_mean = statistics.mean([t[f] for t in losses]) if losses else None
        result["factors"][f] = {
            "correlation_with_return": corr,
            "avg_value_in_winning_trades": win_mean,
            "avg_value_in_losing_trades": loss_mean,
        }
    return result


def format_report(result):
    lines = ["# Signalstation Faktor-Analyse\n"]

    if result.get("insufficient"):
        lines.append(
            f"Nur {result['n_trades']} abgeschlossene Trades mit vollständigen Faktor-Daten -- "
            f"unter der Schwelle von {MIN_TRADES_FOR_ANY_CLAIM}, ab der eine Korrelationsaussage "
            "überhaupt sinnvoll interpretierbar ist. Keine Zahlen ausgegeben, um keine falsche "
            "Präzision vorzutäuschen. Führe zuerst einen größeren Backtest (mehr Coins, mehr "
            "Historie) durch."
        )
        return "\n".join(lines)

    lines.append(f"Basis: {result['n_trades']} abgeschlossene Trades mit vollständigen Faktor-Daten.\n")
    lines.append(
        "**Wichtig:** Dies ist eine einfache Korrelationsanalyse, kein trainiertes Modell und "
        "kein Beweis für Kausalität. Bei dieser Stichprobengröße sind auch diese Zahlen mit "
        "spürbarem Rauschen behaftet -- als Diagnose lesen, nicht als neue Wahrheit.\n"
    )
    lines.append("| Faktor | Korrelation mit Rendite | Ø-Wert bei Gewinn-Trades | Ø-Wert bei Verlust-Trades |")
    lines.append("|---|---|---|---|")

    sortable = []
    for f in FACTORS:
        d = result["factors"][f]
        corr = d["correlation_with_return"]
        sortable.append((abs(corr) if corr is not None else -1, f, d))

    for _, f, d in sorted(sortable, reverse=True):
        corr_txt = f"{d['correlation_with_return']:+.2f}" if d["correlation_with_return"] is not None else "n/a"
        win_txt = f"{d['avg_value_in_winning_trades']:+.2f}" if d["avg_value_in_winning_trades"] is not None else "n/a"
        loss_txt = f"{d['avg_value_in_losing_trades']:+.2f}" if d["avg_value_in_losing_trades"] is not None else "n/a"
        lines.append(f"| {FACTOR_LABELS[f]} | {corr_txt} | {win_txt} | {loss_txt} |")

    lines.append(
        "\nSortiert nach Stärke des Zusammenhangs (unabhängig von Richtung). Ein Faktor mit "
        "Korrelation nahe 0 hatte in dieser Stichprobe keinen erkennbaren Zusammenhang mit dem "
        "Ergebnis -- das ist ein Hinweis, sein Gewicht (25/20/15/25/15%) zu hinterfragen, "
        "kein automatischer Beleg, es zu ändern."
    )
    return "\n".join(lines)


def main():
    trades_path = Path(__file__).parent / "backtest_trades.json"
    if not trades_path.exists():
        print("backtest_trades.json nicht gefunden -- zuerst backtest.py laufen lassen.", file=sys.stderr)
        sys.exit(1)

    trades = json.loads(trades_path.read_text(encoding="utf-8"))
    result = analyze(trades)
    report = format_report(result)

    out_path = Path(__file__).parent / "FACTOR_ANALYSIS.md"
    out_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nGeschrieben nach {out_path}")


if __name__ == "__main__":
    main()

# Signalstation Aktien/ETF-Backtest-Report

Universum: 69 Titel (59 Aktien + 10 ETFs) · Historie bis 3650 Tage (Yahoo Finance) · Auswertungsraster alle 3 Tage · Referenzmarkt SPY · Schwellen 65 (Einstieg) / 40 (Ausstieg) · handelstage-korrekte Zeitfenster (22/5, nicht die Krypto-Defaults)

## Ergebnis: Signalstation-Engine (Aktien/ETFs)

- Abgeschlossene Trades: **61**
- Trefferquote: **52.5%**
- Ø Rendite pro Trade: **+48.4%**
- Median-Rendite: +6.3%
- Beste / schlechteste Trade: +528.8% / -65.5%
- Streuung (Stdev): 130.3 Prozentpunkte
- Ø Haltedauer: 34 Tage
- **Ø maximaler Rücksetzer während der Position: -29.5%** (schlechtester Einzelfall: -82.5%)
- **Rendite-Risiko-Verhältnis: 0.37**

## Experiment: Markt-Regime-Filter (SPY statt Bitcoin)

Dieselbe Hypothese wie im Krypto-Backtest, hier mit SPY als Referenzmarkt: neue Einstiege werden unterdrückt, solange SPY selbst unter SMA50 unter SMA100 steht. Ausstiege bleiben unberührt.

| | Ohne Filter | Mit Regime-Filter |
|---|---|---|
| Trades | 61 | 61 |
| Trefferquote | 52.5% | 52.5% |
| Ø Rendite | +48.4% | +48.4% |

**Effekt des Filters auf die Ø Rendite: +0.0 Prozentpunkte.**
 Half in diesem Lauf NICHT.

## Vergleich: zufällige Einstiegszeitpunkte (Baseline)

- Zufalls-Trades: **59**
- Zufalls-Trefferquote: **88.1%**
- Ø Zufalls-Rendite: **+61.4%**

**Vorsprung der Engine ggü. Zufall: -13.0 Prozentpunkte pro Trade.**

⚠️ Kein positiver Vorsprung gegenüber zufälligen Einstiegen in diesem Lauf.

## Vergleich: Buy-and-Hold pro Titel

| Symbol | Typ | Trades | Buy-and-Hold |
|---|---|---|---|
| AAPL | Aktie | 0 | +99.3% |
| ABBV | Aktie | 0 | +16.9% |
| ABT | Aktie | 0 | +5.0% |
| ADBE | Aktie | 0 | -42.7% |
| AGG | ETF | 1 | -12.0% |
| AMAT | Aktie | 0 | +473.1% |
| AMD | Aktie | 0 | +469.5% |
| AMZN | Aktie | 3 | +3980.9% |
| AVGO | Aktie | 0 | +579.3% |
| BA | Aktie | 0 | +93.6% |
| BAC | Aktie | 1 | +86.8% |
| CAT | Aktie | 0 | +413.3% |
| COP | Aktie | 0 | +7.5% |
| COST | Aktie | 0 | +29.4% |
| CRM | Aktie | 2 | +143.7% |
| CSCO | Aktie | 3 | +1058.7% |
| CVX | Aktie | 0 | +29.9% |
| DHR | Aktie | 0 | +183.7% |
| DIA | ETF | 4 | +438.5% |
| DIS | Aktie | 0 | +11.2% |
| EFA | ETF | 2 | +61.5% |
| GE | Aktie | 2 | +95.4% |
| GLD | ETF | 2 | +237.6% |
| GOOGL | Aktie | 1 | +735.8% |
| GS | Aktie | 1 | +1049.6% |
| HD | Aktie | 0 | +23.3% |
| HON | Aktie | 2 | +335.9% |
| IBM | Aktie | 1 | +105.1% |
| INTC | Aktie | 0 | +218.5% |
| IWM | ETF | 3 | +257.6% |
| JNJ | Aktie | 0 | +58.7% |
| JPM | Aktie | 0 | +214.4% |
| KO | Aktie | 0 | +55.4% |
| LIN | Aktie | 2 | +1035.5% |
| LLY | Aktie | 0 | +293.6% |
| LMT | Aktie | 0 | +52.2% |
| LRCX | Aktie | 0 | +427.8% |
| MA | Aktie | 0 | +198.4% |
| MCD | Aktie | 0 | +19.0% |
| META | Aktie | 0 | +1.1% |
| MRK | Aktie | 0 | +49.3% |
| MS | Aktie | 3 | +301.1% |
| MSFT | Aktie | 0 | +32.0% |
| NEM | Aktie | 0 | +173.2% |
| NKE | Aktie | 1 | -60.8% |
| NVDA | Aktie | 1 | +67205.8% |
| ORCL | Aktie | 0 | +26.5% |
| PEP | Aktie | 0 | -19.3% |
| PFE | Aktie | 1 | -40.8% |
| PG | Aktie | 0 | +15.5% |
| PLTR | Aktie | 3 | +1094.5% |
| QCOM | Aktie | 7 | +385.1% |
| QQQ | ETF | 2 | +1147.7% |
| RTX | Aktie | 0 | +172.5% |
| SBUX | Aktie | 3 | +682.1% |
| SLB | Aktie | 0 | +32.5% |
| SPY | ETF | 2 | +530.8% |
| TMO | Aktie | 0 | +8.9% |
| TSLA | Aktie | 0 | +89.7% |
| UNH | Aktie | 0 | -19.4% |
| UPS | Aktie | 2 | +32.7% |
| V | Aktie | 1 | +99.5% |
| VNQ | ETF | 1 | +18.9% |
| VTI | ETF | 2 | +311.0% |
| WFC | Aktie | 0 | +99.6% |
| WMT | Aktie | 0 | +525.6% |
| XLE | ETF | 2 | +50.4% |
| XOM | Aktie | 0 | +75.3% |

Ø Buy-and-Hold über alle Titel: **+1273.0%**


## Einzeltitel vs. SPY

- Titel mit Daten für den Vergleich: **67**
- Davon besser als SPY im selben Fenster: **36 von 67** (54%)


## Wichtige Einschränkungen dieses Backtests
- Keine Gebühren, kein Slippage, keine Steuer -- reale Ergebnisse wären schlechter.
- Aktien werden nur wochentags gehandelt; die handelstage-korrekten Zeitfenster (22/5 statt 31/7) gleichen das aus, siehe Universum-Zeile oben.
- Ein Auswertungsraster von alle 3 Tagen ist ein Kompromiss, kein exaktes Live-Verhalten.
- Die Schwellen 65/40 und die Gewichtung 25/20/15/25/15% wurden NICHT anhand dieses Backtests optimiert -- dieser Lauf prüft die bereits feststehenden Werte.
- Ein einzelner Lauf ist weiterhin nur eine Stichprobe der Marktgeschichte.
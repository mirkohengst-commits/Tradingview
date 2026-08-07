# Signalstation Backtest-Report

Universum: 22 Coins · Historie bis 365 Tage · Auswertungsraster alle 3 Tage · Schwellen 65 (Einstieg) / 40 (Ausstieg)

## Ergebnis: Signalstation-Engine

- Abgeschlossene Trades: **37**
- Trefferquote: **10.8%**
- Ø Rendite pro Trade: **-12.1%**
- Median-Rendite: -9.5%
- Beste / schlechteste Trade: +10.9% / -41.4%
- Streuung (Stdev): 12.4 Prozentpunkte
- Ø Haltedauer: 25 Tage
- **Ø maximaler Rücksetzer während der Position: -19.4%** (schlechtester Einzelfall: -59.3%)
  Das ist der schlimmste Zwischenstand *während* der Position, nicht die Endrendite — zeigt, wie holprig der Weg dorthin tatsächlich war, selbst wenn der Trade am Ende gewann.
- **Rendite-Risiko-Verhältnis (Ø Rendite / Streuung): -0.98**
  Grobe Orientierung, kein echter Sharpe-Ratio (dafür fehlt ein risikofreier Zins und eine gleichmäßige Zeitbasis) — aber besser als die Durchschnittsrendite allein zu lesen, ohne zu wissen, wie stark sie streut.

## Vergleich: zufällige Einstiegszeitpunkte (Baseline)

Dieselbe Anzahl Trades pro Coin, dieselbe Haltedauer-Verteilung wie oben, aber zufällig statt signalbasiert gewählte Einstiege. Schlägt die Engine den Zufall überhaupt?

- Zufalls-Trades: **37**
- Zufalls-Trefferquote: **45.9%**
- Ø Zufalls-Rendite: **-3.4%**

**Vorsprung der Engine ggü. Zufall: -8.7 Prozentpunkte pro Trade.**

⚠️ Kein positiver Vorsprung gegenüber zufälligen Einstiegen in diesem Lauf — das ist ein ernstzunehmendes Signal, dass die aktuelle Schwelle/Gewichtung in diesem Zeitraum keinen nachweisbaren Mehrwert gegenüber Zufall hatte.

## Vergleich: Buy-and-Hold pro Coin

| Coin | Abgeschl. Trades | Buy-and-Hold (gesamter Zeitraum) |
|---|---|---|
| bitcoin | 1 | -28.3% |
| ethereum | 1 | -38.4% |
| litecoin | 2 | -43.7% |
| ripple | 1 | -49.8% |
| cardano | 0 | -48.8% |
| polkadot | 2 | -61.7% |
| chainlink | 1 | -38.1% |
| stellar | 2 | -29.9% |
| dogecoin | 1 | -52.9% |
| monero | 2 | -10.8% |
| tron | 3 | +13.0% |
| eos | 2 | -63.3% |
| tezos | 1 | -62.8% |
| cosmos | 3 | -41.5% |
| vechain | 1 | -61.5% |
| algorand | 5 | -33.9% |
| aave | 1 | -44.6% |
| uniswap | 1 | -30.6% |
| maker | 1 | -13.1% |
| the-graph | 2 | -64.3% |
| solana | 3 | -44.4% |
| avalanche-2 | 1 | -54.2% |

Ø Buy-and-Hold über alle Coins: **-41.1%**


## Alts vs. Bitcoin

Direkter Test der Bitcoin-Maximalisten-These ("Altcoins bluten strukturell gegen Bitcoin, nicht nur zufällig"): wie viele der Altcoins hätten über exakt denselben Zeitraum eine reine Bitcoin-Position geschlagen — nicht in Dollar, sondern relativ zu BTC selbst?

- Altcoins mit Daten für den Vergleich: **21**
- Davon besser als Bitcoin im selben Fenster: **3 von 21** (14%)

| Coin | Buy-and-Hold | Bitcoin im selben Fenster | Alt schlägt BTC? |
|---|---|---|---|
| tron | +13.0% | -27.3% | ✅ ja |
| monero | -10.8% | -27.3% | ✅ ja |
| maker | -13.1% | -27.3% | ✅ ja |
| stellar | -29.9% | -27.3% | ❌ nein |
| uniswap | -30.6% | -27.3% | ❌ nein |
| algorand | -33.9% | -27.3% | ❌ nein |
| chainlink | -38.1% | -27.3% | ❌ nein |
| ethereum | -38.4% | -27.3% | ❌ nein |
| cosmos | -41.5% | -27.3% | ❌ nein |
| litecoin | -43.7% | -27.3% | ❌ nein |
| solana | -44.4% | -27.3% | ❌ nein |
| aave | -44.6% | -27.3% | ❌ nein |
| cardano | -48.8% | -27.3% | ❌ nein |
| ripple | -49.8% | -27.3% | ❌ nein |
| dogecoin | -52.9% | -27.3% | ❌ nein |
| avalanche-2 | -54.2% | -27.3% | ❌ nein |
| vechain | -61.5% | -27.3% | ❌ nein |
| polkadot | -61.7% | -27.3% | ❌ nein |
| tezos | -62.8% | -27.3% | ❌ nein |
| eos | -63.3% | -27.3% | ❌ nein |
| the-graph | -64.3% | -27.3% | ❌ nein |


## Wichtige Einschränkungen dieses Backtests

- Keine Gebühren, kein Slippage, keine Steuer -- reale Ergebnisse wären schlechter.
- CoinGecko liefert je nach Coin unterschiedlich lange Historie; nicht alle Coins decken den vollen Zeitraum ab.
- Ein Auswertungsraster von alle 3 Tagen ist ein Kompromiss, kein exaktes Live-Verhalten.
- Die Schwellen 65/40 und die Gewichtung 25/20/15/25/15% wurden NICHT anhand dieses Backtests optimiert (das wäre Overfitting auf die Testdaten selbst) -- dieser Lauf prüft die bereits feststehenden Werte, ändert sie nicht automatisch.
- Ein einzelner Lauf über ein bestimmtes Zeitfenster ist immer noch nur eine Stichprobe der Marktgeschichte, kein Beweis für die Zukunft.
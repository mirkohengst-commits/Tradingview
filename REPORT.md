# Signalstation Backtest-Report

Universum: 22 Coins · Historie bis 1000 Tage (Binance, wo gelistet) bzw. 365 Tage (CoinGecko-Rückfall) · Auswertungsraster alle 3 Tage · Schwellen 65 (Einstieg) / 40 (Ausstieg)

## Ergebnis: Signalstation-Engine

- Abgeschlossene Trades: **46**
- Trefferquote: **10.9%**
- Ø Rendite pro Trade: **-13.6%**
- Median-Rendite: -10.5%
- Beste / schlechteste Trade: +14.4% / -43.6%
- Streuung (Stdev): 14.2 Prozentpunkte
- Ø Haltedauer: 22 Tage
- **Ø maximaler Rücksetzer während der Position: -19.5%** (schlechtester Einzelfall: -59.3%)
  Das ist der schlimmste Zwischenstand *während* der Position, nicht die Endrendite — zeigt, wie holprig der Weg dorthin tatsächlich war, selbst wenn der Trade am Ende gewann.
- **Rendite-Risiko-Verhältnis (Ø Rendite / Streuung): -0.95**
  Grobe Orientierung, kein echter Sharpe-Ratio (dafür fehlt ein risikofreier Zins und eine gleichmäßige Zeitbasis) — aber besser als die Durchschnittsrendite allein zu lesen, ohne zu wissen, wie stark sie streut.

## Vergleich: zufällige Einstiegszeitpunkte (Baseline)

Dieselbe Anzahl Trades pro Coin, dieselbe Haltedauer-Verteilung wie oben, aber zufällig statt signalbasiert gewählte Einstiege. Schlägt die Engine den Zufall überhaupt?

- Zufalls-Trades: **46**
- Zufalls-Trefferquote: **47.8%**
- Ø Zufalls-Rendite: **-2.4%**

**Vorsprung der Engine ggü. Zufall: -11.1 Prozentpunkte pro Trade.**

⚠️ Kein positiver Vorsprung gegenüber zufälligen Einstiegen in diesem Lauf — das ist ein ernstzunehmendes Signal, dass die aktuelle Schwelle/Gewichtung in diesem Zeitraum keinen nachweisbaren Mehrwert gegenüber Zufall hatte.

## Vergleich: Buy-and-Hold pro Coin

| Coin | Abgeschl. Trades | Buy-and-Hold (gesamter Zeitraum) |
|---|---|---|
| bitcoin | 2 | -29.8% |
| ethereum | 2 | -39.7% |
| litecoin | 1 | -44.7% |
| ripple | 1 | -55.4% |
| cardano | 0 | -52.2% |
| polkadot | 3 | -62.5% |
| chainlink | 1 | -39.6% |
| stellar | 3 | -34.5% |
| dogecoin | 1 | -53.0% |
| monero | 2 | -11.6% |
| tron | 2 | +13.8% |
| eos | 1 | -64.3% |
| tezos | 1 | -63.1% |
| cosmos | 3 | -40.6% |
| vechain | 2 | -62.2% |
| algorand | 7 | -36.7% |
| aave | 1 | -46.7% |
| uniswap | 1 | -34.4% |
| maker | 4 | -16.0% |
| the-graph | 2 | -64.8% |
| solana | 4 | -45.0% |
| avalanche-2 | 2 | -54.2% |

Ø Buy-and-Hold über alle Coins: **-42.6%**


## Alts vs. Bitcoin

Direkter Test der Bitcoin-Maximalisten-These ("Altcoins bluten strukturell gegen Bitcoin, nicht nur zufällig"): wie viele der Altcoins hätten über exakt denselben Zeitraum eine reine Bitcoin-Position geschlagen — nicht in Dollar, sondern relativ zu BTC selbst?

- Altcoins mit Daten für den Vergleich: **21**
- Davon besser als Bitcoin im selben Fenster: **3 von 21** (14%)

| Coin | Buy-and-Hold | Bitcoin im selben Fenster | Alt schlägt BTC? |
|---|---|---|---|
| tron | +13.8% | -28.1% | ✅ ja |
| monero | -11.6% | -28.1% | ✅ ja |
| maker | -16.0% | -28.1% | ✅ ja |
| uniswap | -34.4% | -28.1% | ❌ nein |
| stellar | -34.5% | -28.1% | ❌ nein |
| algorand | -36.7% | -28.1% | ❌ nein |
| chainlink | -39.6% | -28.1% | ❌ nein |
| ethereum | -39.7% | -28.1% | ❌ nein |
| cosmos | -40.6% | -28.1% | ❌ nein |
| litecoin | -44.7% | -28.1% | ❌ nein |
| solana | -45.0% | -28.1% | ❌ nein |
| aave | -46.7% | -28.1% | ❌ nein |
| cardano | -52.2% | -28.1% | ❌ nein |
| dogecoin | -53.0% | -28.1% | ❌ nein |
| avalanche-2 | -54.2% | -28.1% | ❌ nein |
| ripple | -55.4% | -28.1% | ❌ nein |
| vechain | -62.2% | -28.1% | ❌ nein |
| polkadot | -62.5% | -28.1% | ❌ nein |
| tezos | -63.1% | -28.1% | ❌ nein |
| eos | -64.3% | -28.1% | ❌ nein |
| the-graph | -64.8% | -28.1% | ❌ nein |


## Wichtige Einschränkungen dieses Backtests

- Keine Gebühren, kein Slippage, keine Steuer -- reale Ergebnisse wären schlechter.
- CoinGecko liefert je nach Coin unterschiedlich lange Historie; nicht alle Coins decken den vollen Zeitraum ab.
- Ein Auswertungsraster von alle 3 Tagen ist ein Kompromiss, kein exaktes Live-Verhalten.
- Die Schwellen 65/40 und die Gewichtung 25/20/15/25/15% wurden NICHT anhand dieses Backtests optimiert (das wäre Overfitting auf die Testdaten selbst) -- dieser Lauf prüft die bereits feststehenden Werte, ändert sie nicht automatisch.
- Ein einzelner Lauf über ein bestimmtes Zeitfenster ist immer noch nur eine Stichprobe der Marktgeschichte, kein Beweis für die Zukunft.
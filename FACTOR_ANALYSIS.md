# Signalstation Faktor-Analyse

Basis: 36 abgeschlossene Trades mit vollständigen Faktor-Daten.

**Wichtig:** Dies ist eine einfache Korrelationsanalyse, kein trainiertes Modell und kein Beweis für Kausalität. Bei dieser Stichprobengröße sind auch diese Zahlen mit spürbarem Rauschen behaftet -- als Diagnose lesen, nicht als neue Wahrheit.

| Faktor | Korrelation mit Rendite | Ø-Wert bei Gewinn-Trades | Ø-Wert bei Verlust-Trades |
|---|---|---|---|
| Momentum (20%) | +0.25 | +0.25 | -0.03 |
| Trend (25%) | -0.18 | +0.75 | +1.12 |
| Bollinger-Position (15%) | +0.17 | +0.25 | -0.12 |
| Relative Stärke (25%) | -0.14 | +2.00 | +1.50 |
| Volumen (15%) | +0.01 | +0.25 | +0.69 |

Sortiert nach Stärke des Zusammenhangs (unabhängig von Richtung). Ein Faktor mit Korrelation nahe 0 hatte in dieser Stichprobe keinen erkennbaren Zusammenhang mit dem Ergebnis -- das ist ein Hinweis, sein Gewicht (25/20/15/25/15%) zu hinterfragen, kein automatischer Beleg, es zu ändern.
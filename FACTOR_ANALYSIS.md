# Signalstation Faktor-Analyse

Basis: 44 abgeschlossene Trades mit vollständigen Faktor-Daten.

**Wichtig:** Dies ist eine einfache Korrelationsanalyse, kein trainiertes Modell und kein Beweis für Kausalität. Bei dieser Stichprobengröße sind auch diese Zahlen mit spürbarem Rauschen behaftet -- als Diagnose lesen, nicht als neue Wahrheit.

| Faktor | Korrelation mit Rendite | Ø-Wert bei Gewinn-Trades | Ø-Wert bei Verlust-Trades |
|---|---|---|---|
| Momentum (20%) | +0.26 | +0.00 | +0.00 |
| Bollinger-Position (15%) | +0.25 | +0.00 | -0.22 |
| Relative Stärke (25%) | -0.22 | +2.00 | +1.56 |
| Trend (25%) | -0.21 | +0.67 | +1.27 |
| Volumen (15%) | -0.09 | +0.67 | +0.59 |

Sortiert nach Stärke des Zusammenhangs (unabhängig von Richtung). Ein Faktor mit Korrelation nahe 0 hatte in dieser Stichprobe keinen erkennbaren Zusammenhang mit dem Ergebnis -- das ist ein Hinweis, sein Gewicht (25/20/15/25/15%) zu hinterfragen, kein automatischer Beleg, es zu ändern.
# Signalstation Faktor-Analyse

Basis: 59 abgeschlossene Trades mit vollständigen Faktor-Daten.

**Wichtig:** Dies ist eine einfache Korrelationsanalyse, kein trainiertes Modell und kein Beweis für Kausalität. Bei dieser Stichprobengröße sind auch diese Zahlen mit spürbarem Rauschen behaftet -- als Diagnose lesen, nicht als neue Wahrheit.

| Faktor | Korrelation mit Rendite | Ø-Wert bei Gewinn-Trades | Ø-Wert bei Verlust-Trades |
|---|---|---|---|
| Momentum (20%) | +0.08 | -0.77 | -0.79 |
| Volumen (15%) | +0.05 | +0.32 | +0.39 |
| Bollinger-Position (15%) | +0.04 | -0.55 | -0.54 |
| Trend (25%) | +0.04 | +1.77 | +1.79 |
| Relative Stärke (25%) | +0.03 | +1.97 | +1.96 |

Sortiert nach Stärke des Zusammenhangs (unabhängig von Richtung). Ein Faktor mit Korrelation nahe 0 hatte in dieser Stichprobe keinen erkennbaren Zusammenhang mit dem Ergebnis -- das ist ein Hinweis, sein Gewicht (25/20/15/25/15%) zu hinterfragen, kein automatischer Beleg, es zu ändern.
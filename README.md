# Signalstation Watcher

Läuft alle 30 Minuten in der GitHub-Cloud und prüft deine Krypto- und Aktienkurse mit
**derselben RSI/MACD/Bollinger-Engine wie die Signalstation-App** — nicht nur einfache
Kursschwellen. Zwei Push-Nachrichten, um die es dir geht:

- **"Einstieg sinnvoll"** — sobald der Score eines beobachteten Assets auf ≥65 steigt
- **"Ausstieg sinnvoll"** — sobald der Score eines gehaltenen Assets wieder unter 40 fällt

Beides feuert nur **einmal pro Übergang**, nicht bei jedem Lauf erneut — kein Dauerfeuer,
solange ein Zustand anhält. Läuft komplett unabhängig davon, ob dein Handy an ist.

## Wichtig: CoinGecko-API-Key jetzt erforderlich

CoinGecko hat den komplett schlüssellosen Zugriff stark gedrosselt — bei längeren
Historienabfragen (z. B. im Backtest) kommt sonst `401 Unauthorized`, genau das, was
den ersten Testlauf blockiert hat. Der kostenlose **Demo-Plan** behebt das (100
Anfragen/Min., 10.000/Monat, ein Jahr Historie — kein Zahlungsmittel nötig):

1. [coingecko.com/en/api/pricing](https://www.coingecko.com/en/api/pricing) → **"Create Free Account"**
2. Registrieren/einloggen → **Developer Dashboard** → Reiter **"API Keys"**
3. **"+ Add New Key"** → Key kopieren
4. Repo → **Settings → Secrets and variables → Actions → "New repository secret"**
5. Name: `COINGECKO_API_KEY`, Value: dein Key → **"Add secret"**

Der Key ist im Code technisch optional (kein Absturz ohne ihn), aber praktisch ohne
ihn kaum noch zuverlässig nutzbar — bitte einrichten, bevor du die Workflows erneut
startest.

**Zusätzlich wichtig:** Der Demo-Plan liefert laut CoinGecko nur ein Jahr Historie —
`backtest.py` fragt deshalb `MAX_HISTORY_DAYS = 365` ab, nicht mehr (war vorher 1000,
das wäre selbst mit gültigem Key fehlgeschlagen — zwei getrennte Probleme, die im
ersten Lauf zusammen aufgetreten wären).

## Einrichtung (alles vom iPhone aus machbar)

### 1. Neues **privates** Repository anlegen
- github.com → **"+"** oben rechts → **"New repository"**
- Name z. B. `signalstation-watcher`
- **Private** auswählen (nicht Public)
- **"Create repository"**

### 2. Die sechs Dateien anlegen
Im leeren Repo jeweils auf **"Add file" → "Create new file"** tippen. Beim
`.github/workflows/watch.yml` den kompletten Pfad mit Schrägstrichen ins Namensfeld
tippen — GitHub legt die Ordner automatisch an.

Der Reihe nach (Inhalt jeweils aus der Datei hier kopieren):
1. `config.yml`
2. `watcher.py`
3. `requirements.txt`
4. `state.json` (Inhalt: `{}`)
5. `.github/workflows/watch.yml`

Nach jeder Datei unten **"Commit changes"**.

### 3. ntfy.sh einrichten (kein Account nötig)
- App Store → **"ntfy"** installieren
- App öffnen → **"+"** → eigenen, schwer zu erratenden Themennamen eingeben,
  z. B. `signalstation-<deinname>-8f3k2`
- Abonnieren

### 4. Themennamen als Secret hinterlegen
- Repo → **Settings → Secrets and variables → Actions → "New repository secret"**
- Name: `NTFY_TOPIC`
- Value: genau der Themenname aus Schritt 3
- **"Add secret"**

### 5. Testen
- Reiter **"Actions"** → **"Signalstation Watcher"** → **"Run workflow"**
- Nach ~30–60 Sekunden (die Signal-Engine lädt echte Kurshistorie, dauert etwas länger
  als vorher) auf den Lauf tippen, um die Logs zu sehen — dort steht für jedes Asset der
  aktuelle Score und Status, auch wenn gerade keine Push-Bedingung erfüllt ist
- Ab hier läuft es automatisch alle 30 Minuten

## Wie "Einstieg"/"Ausstieg" konkret funktioniert

Pro Asset wird ein einfacher Status mitgeführt (`none` oder `entered`), gespeichert in
`state.json`:

- Status `none` + Score steigt auf ≥65 → Push **"Einstieg sinnvoll"**, Status wird `entered`
- Status `entered` + Score fällt unter 40 → Push **"Ausstieg sinnvoll"**, Status wird `none`
- Dazwischen: still, egal wie oft geprüft wird

`already_holding: true` in `config.yml` setzt ein Asset direkt auf Status `entered` — für
Dinge, die du schon "hältst" (wie dein AMAT-Test von eben, schon eingetragen mit
Einstieg $547,14) und bei denen du direkt auf das Ausstiegssignal warten willst, ohne
vorher ein neues Einstiegssignal abzuwarten.

Die Schwellen 65/40 sind identisch zu "Kaufsignal" bzw. "Beobachten/Meiden" in der App —
dieselbe Methodik, dieselben Grenzen, kein Extra-Regelwerk.

## Wie ich das geprüft habe

Die komplette Berechnungslogik (SMA, Wilder-RSI, MACD, Bollinger, Divergenz, relative
Stärke, Gewichtung) ist Zeile für Zeile aus der App-JavaScript-Engine nach Python
übertragen und gegen dieselben Referenzwerte getestet — u. a. gegen ein klassisches,
in Lehrbüchern zitiertes RSI-Beispiel, und gegen denselben synthetischen Datensatz wie
in der App, der dort exakt Score 70 / "Kaufsignal" ergab. Die Python-Version liefert auf
identischen Daten denselben Score. Zusätzlich wurde der komplette Einstieg → kein Spam
→ Ausstieg → kein Spam → erneuter Einstieg-Zyklus mit kontrollierten Testdaten
durchgespielt.

## Schwellenwerte / harte Kursmarken zusätzlich

`alert_above` / `alert_below` / `alert_change_24h_above` / `alert_change_24h_below`
funktionieren weiterhin unabhängig von `signal_watch`, falls du zusätzlich eine feste
Marke im Auge behalten willst (z. B. einen konkreten Stop-Loss-Kurs).

## Backtest: prüft die 65/40-Schwellen tatsächlich gegen echte Historie

`backtest.py` läuft die exakt gleiche Engine wie oben, aber rückwirkend über bis zu
1000 Tage echte Kurshistorie für 22 etablierte Coins — streng "point-in-time"
(an jedem Auswertungstag kennt der Algorithmus nur die Vergangenheit, nie die Zukunft;
das wurde explizit gegengetestet, nicht nur behauptet). Ergebnis: Trefferquote, Ø
Rendite pro Trade, Vergleich gegen Buy-and-Hold **und gegen zufällige
Einstiegszeitpunkte** — schlägt die Engine überhaupt den Zufall, oder ist 65/40 nur
eine plausibel klingende Zahl ohne echten Beleg?

**Zum Ausführen:** Reiter **"Actions"** → **"Signalstation Backtest"** → **"Run workflow"**.
Dauert einige Minuten (22 Coins × mehrjährige Historie × CoinGecko-Ratelimit-Pausen).
Danach liegt `REPORT.md` im Repo und ist auch als Download-Artefakt am Workflow-Lauf
verfügbar.

**Wichtig:** Dieser Lauf **verändert die Schwellen nicht automatisch** — er prüft die
bereits feststehenden Werte (65/40, Gewichtung 25/20/15/25/15%). Würde man die Werte
anhand des Backtest-Ergebnisses nachträglich anpassen, wäre das Overfitting auf genau
diese Testdaten. Das Ergebnis ist eine Diagnose, keine automatische Kalibrierung.

## Risiko-Kennzahlen im Backtest (unabhängige Prüfung)

Eine Endrendite allein verschleiert, wie holprig der Weg dorthin war. Der Report zeigt
deshalb zusätzlich:
- **Ø maximaler Rücksetzer während der Position** — der schlechteste Zwischenstand
  *während* eines Trades, nicht nur das Endergebnis. Ein Trade kann am Ende +20% zeigen
  und trotzdem unterwegs -80% durchgemacht haben, bevor er sich erholte — ein
  entscheidender Unterschied für jeden, der die Position tatsächlich hätte halten müssen.
- **Rendite-Risiko-Verhältnis** — Ø Rendite geteilt durch die Streuung der Ergebnisse.
  Kein echter Sharpe-Ratio (dafür fehlen risikofreier Zins und eine gleichmäßige
  Zeitbasis), aber eine grobe Einordnung, ob eine positive Durchschnittsrendite auf
  konsistenten Ergebnissen beruht oder auf ein paar Ausreißern mit viel Streuung drumherum.

## Optional: Gemini-Kontext bei Push-Nachrichten

Rein qualitativer Nachrichtenkontext neben dem technischen Score — bewusst getrennt,
fließt niemals in die Berechnung zurück. Ohne Einrichtung läuft alles wie bisher weiter.

**Einrichtung (optional):**
1. API-Key in [Google AI Studio](https://aistudio.google.com/apikey) erstellen
2. Repo → **Settings → Secrets and variables → Actions → "New repository secret"**
3. Name: `GEMINI_API_KEY`, Value: dein Key
4. Fertig — ab dem nächsten Lauf hängt jede Einstieg/Ausstieg-Push-Nachricht einen
   kurzen, klar als "Gemini-Kontext" markierten Absatz an, wenn das Modell etwas
   Relevantes beisteuern kann

**Ehrliche Einschränkung:** Der Aufruf nutzt Geminis eigenes, antrainiertes Wissen —
kein Such-Grounding, kein Internetzugriff des Modells selbst. "Aktueller Kontext" kann
trotzdem veraltet sein. Das Modell wird im Prompt explizit gebeten, Unwissen zuzugeben
statt zu spekulieren, aber das ist kein Ersatz für eine echte Recherche.

Gemini wird nur aufgerufen, wenn tatsächlich eine Push-Nachricht versendet wird — nicht
bei jedem der 48 täglichen Läufe, um Kosten/Kontingent zu schonen. Das Modell (Standard:
`gemini-3.5-flash`) lässt sich über die `GEMINI_MODEL`-Zeile in `watch.yml` anpassen,
falls Google den Namen wieder ändert.

## Faktor-Analyse: welcher Teil des Scores bringt überhaupt etwas?

`analyze_backtest.py` liest die Rohdaten aus einem Backtest-Lauf (`backtest_trades.json`)
und prüft per einfacher Korrelation, ob die fünf Scoring-Faktoren (Trend, Momentum,
Bollinger-Position, relative Stärke, Volumen) beim Einstieg tatsächlich mit dem späteren
Handelsergebnis zusammenhingen. Läuft automatisch als Teil des Backtest-Workflows direkt
nach `backtest.py`, Ergebnis landet in `FACTOR_ANALYSIS.md`.

**Bewusst kein neuronales Netz oder trainiertes Modell.** Bei ein paar hundert Trades aus
22 Coins würde jedes ML-Modell das Rauschen in den Daten auswendig lernen statt echte
Struktur zu finden — eine einfache Korrelation ist hier die ehrlichere, nicht die
bequemere Wahl. Unter 30 Trades gibt das Skript explizit "zu wenig Daten" aus, statt eine
Zahl mit falscher Präzision zu liefern. **Das Skript ändert nie automatisch Gewichte** —
es liefert eine Diagnose zum Lesen, keine Kalibrierung.

## Briefing statt stiller Alarme (2× täglich)

`briefing.py` durchsucht zweimal täglich (06:00 und 15:00 UTC, in `briefing.yml`
anpassbar) alle Titel aus `briefing_stocks` in `config.yml` (~60 sektorübergreifende
Aktien, selbst erweiterbar — einfach eine Zeile ergänzen) plus die Top-100 Kryptowerte
nach Marktkapitalisierung. Jeder Kandidat mit Score ≥ 65 bekommt eine Begründung, wenn
`GEMINI_API_KEY` gesetzt ist — sonst nur die nackten Kennzahlen, funktioniert aber auch
so vollständig.

**Wichtig, damit klar ist, was hier passiert:** Der Score selbst kommt weiterhin
ausschließlich aus der deterministischen Engine (`compute_conviction`) — exakt dieselbe
wie in Watcher, App und Backtest. Gemini bekommt diese fertige Zahl plus RSI, Trendphase,
Wochentrend und (bei Aktien) Fundamentaldaten und schreibt dazu 3–4 Sätze, warum das
interessant ist, inklusive mindestens einem konkreten Risiko — es erfindet nichts, es
erklärt nur, was bereits berechnet wurde. Der Prompt verbietet dem Modell explizit,
zusätzliche Fakten, Kursziele oder eine Kaufaufforderung zu formulieren.

Ergebnis landet in `BRIEFING.md` im Repo, eine kurze Push-Zusammenfassung kommt zusätzlich
über ntfy. "Wirklich jede Aktie" ist technisch nicht möglich — es gibt weltweit
zehntausende — aber die Liste in `config.yml` ist absichtlich dort und nicht im Code,
damit du sie beliebig erweitern kannst.

**Ehrliche Einschränkung:** Ein voller Lauf braucht mehrere Minuten (~60 Aktien-Abrufe
plus bis zu 12 tiefe Krypto-Analysen) — deshalb zweimal täglich statt alle 30 Minuten.
Für einzelne, schnelle Alarme auf bereits bekannte Titel bleibt der normale Watcher
(`watcher.py` + `watch.yml`) die bessere Wahl; beide laufen unabhängig nebeneinander.

## Bitcoin ist jetzt vollwertig Teil der Analyse

Bitcoin war bisher aus dem Discovery-Scan der App ausgeschlossen, weil die relative-
Stärke-Kennzahl gegen sich selbst immer trivial 0 ergibt. Jetzt wird das erkannt: der
25%-Gewichtsanteil dieses Faktors wird bei Bitcoin proportional auf Trend, Momentum,
Bollinger-Position und Volumen umverteilt (0,25/0,75, 0,20/0,75, 0,15/0,75, 0,15/0,75 —
Summe weiterhin exakt 1,0). `config.yml` enthält jetzt standardmäßig einen Bitcoin-
Eintrag mit `signal_watch: true`. Gilt identisch für Watcher, App und Backtest.

## Grenzen, die du kennen solltest

- GitHub garantiert keine exakte Startzeit bei geplanten Workflows — ein paar Minuten
  Verzug bei hoher Last sind normal.
- Aktienkurse kommen von Yahoo Finance außerhalb der Handelszeiten ggf. verzögert oder
  als letzter Schlusskurs.
- Die Signal-Engine braucht min. 30 Tage Kurshistorie, für den vollen Funktionsumfang
  (MACD, SMA100) idealerweise 100+ Tage — bei sehr neuen Coins/IPOs entsprechend
  eingeschränkt, das Log zeigt das an ("zu wenig Historie").
- ntfy.sh-Themen sind ohne eigenen Server öffentlich einsehbar für jeden, der den
  exakten Namen kennt — daher unbedingt einen langen, zufälligen Namen wählen.
- Score ≥65/<40 ist eine Heuristik, keine Garantie — siehe die Backtests, die wir
  gemeinsam gemacht haben: auch technisch saubere Signale gehen nicht immer auf.

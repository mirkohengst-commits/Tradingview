name: Signalstation Backtest

on:
  workflow_dispatch: {}   # bewusst kein Zeitplan -- ein Backtest ist eine einmalige Analyse,
                          # kein wiederkehrender Job wie der Watcher selbst

permissions:
  contents: write

jobs:
  backtest:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Python einrichten
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Abhängigkeiten installieren
        run: pip install -r requirements.txt

      - name: Backtest ausführen (dauert je nach Universum-Größe mehrere Minuten)
        env:
          VS_CURRENCY: eur
          COINGECKO_API_KEY: ${{ secrets.COINGECKO_API_KEY }}   # kostenloser Demo-Key, siehe README
        run: python backtest.py

      - name: Faktor-Analyse ausführen (Hinton/LeCun-Korrelationscheck, kein ML-Modell)
        run: python analyze_backtest.py

      - name: REPORT.md, FACTOR_ANALYSIS.md und Rohdaten committen
        run: |
          git config user.name "signalstation-backtest-bot"
          git config user.email "actions@users.noreply.github.com"
          git add REPORT.md FACTOR_ANALYSIS.md backtest_trades.json backtest_summary.json
          git commit -m "backtest report $(date -u +%Y-%m-%d) [skip ci]" || echo "Keine Änderung, kein Commit."
          git push

      - name: Report auch als Artefakt hochladen
        uses: actions/upload-artifact@v4
        with:
          name: backtest-report
          path: |
            REPORT.md
            FACTOR_ANALYSIS.md
            backtest_trades.json
            backtest_summary.json

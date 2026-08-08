name: Signalstation Aktien-Backtest

on:
  workflow_dispatch: {}   # bewusst kein Zeitplan -- wie der Krypto-Backtest eine einmalige Analyse

permissions:
  contents: write

jobs:
  stock-backtest:
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

      - name: Aktien/ETF-Backtest ausführen (dauert je nach Universum-Größe mehrere Minuten)
        run: python stock_backtest.py

      - name: Faktor-Analyse ausführen (dieselbe Korrelationslogik wie beim Krypto-Backtest)
        run: python analyze_backtest.py stocks

      - name: STOCK_REPORT.md, STOCK_FACTOR_ANALYSIS.md und Rohdaten committen
        run: |
          git config user.name "signalstation-stock-backtest-bot"
          git config user.email "actions@users.noreply.github.com"
          git add STOCK_REPORT.md STOCK_FACTOR_ANALYSIS.md stock_backtest_trades.json stock_backtest_summary.json
          git commit -m "stock backtest report $(date -u +%Y-%m-%d) [skip ci]" || echo "Keine Änderung, kein Commit."
          git push

      - name: Report auch als Artefakt hochladen
        uses: actions/upload-artifact@v4
        with:
          name: stock-backtest-report
          path: |
            STOCK_REPORT.md
            STOCK_FACTOR_ANALYSIS.md
            stock_backtest_trades.json
            stock_backtest_summary.json

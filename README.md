# Stock Grader

**Live site: https://asegur12.github.io/stock-grader/** (turn on GitHub Pages first: Settings > Pages > Source: GitHub Actions)

The first of three projects for my CSC 299 final project. Stock Grader is a web app for a
new investor. It shows the 10 most valuable companies, what one share costs, how each stock
moved over the past week, the news that could affect it, and an estimate of where its price
might go next week.

## What it shows

| Requirement | Where to find it |
|---|---|
| Top 10 stocks by market cap, with the price of one share | The "Top 10 ranking" grid |
| Graph of current value and past history | Each card has a 1-week sparkline. Click a card for a full chart (1W / 1M / 3M) |
| Company status as of today and relevant news | Click a company to see sector, P/E, 52-week range, analyst view, and 2 news articles |
| Prediction as a % rise or fall | The yellow "Est. next week" box on every card, with a likely range |
| 2 sources per company, shown on hover | Hover a card to see a popup with 2 linked news sources |
| Rising stock in a separate grid | "Rising stock": the biggest 1-week gainer outside the top 10 |
| Past week's values, labeled Rise or Fall | Card badge plus a day-by-day table in the detail view |
| Disclaimer that predictions are only estimates | Banner at the top, plus a note in each estimate box |

Colors: black and white UI. **Green** means a rise, **red** means a fall, **yellow** means an estimate.

## How it works

```
scripts/fetch_data.py  ──(Yahoo Finance via yfinance)──▶  site/data.json
site/index.html + app.js  ──reads──▶  data.json  ──draws──▶  grids, charts, details
```

1. `fetch_data.py` ranks a pool of about 40 very large companies by market cap and keeps the
   top 10. It saves their prices, company facts, news, and a prediction to `site/data.json`.
2. The website (`site/`) is plain HTML, CSS, and JavaScript. It reads `data.json` and uses
   [Chart.js](https://www.chartjs.org/) for the graphs.
3. A GitHub Action (`.github/workflows/deploy.yml`) re-runs the script every weekday after
   U.S. market close and republishes the site to GitHub Pages. You can also run it by hand
   from the **Actions** tab.

### The prediction (and why it is only an estimate)

- It fits a straight trend line to the log of the last ~60 daily closing prices.
- It only trusts half of that trend, because trends rarely continue at full strength.
- It turns daily volatility (how much the price normally swings) into a weekly "likely range".

This is a simple statistical guess from past prices. It cannot know about future news or
events. **It is not financial advice.**

## Run it on your own computer

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
python scripts/fetch_data.py      # refresh site/data.json
python -m http.server 8000 -d site
```

Then open http://localhost:8000. Tip: `http://localhost:8000/#NVDA` opens a stock's details
directly.

## Sources

- Prices, company data, and news come from [Yahoo Finance](https://finance.yahoo.com) through the
  [yfinance](https://github.com/ranaroussi/yfinance) library.
- Each company's news articles are linked in its hover popup and detail view.

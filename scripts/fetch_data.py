"""Fetch stock data for Stock Grader and write it to site/data.json.

What this script does, step by step:
  1. Looks at a pool of very large companies (CANDIDATES).
  2. Ranks them by market cap (total company value) and keeps the top 10.
  3. For each stock, collects price history, company status, and 2 news sources.
  4. Makes a simple 1-week price estimate (see `estimate_next_week`).
  5. Picks one "rising stock": the biggest 1-week gainer outside the top 10.

Data comes from Yahoo Finance through the free `yfinance` library (no API key).
Run it with:  python scripts/fetch_data.py
"""

from __future__ import annotations

import json
import re
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

# A pool of the largest US-listed companies. The script ranks these by market
# cap, so the order here doesn't matter. Only one share class per company.
CANDIDATES = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "AVGO", "TSLA", "BRK-B",
    "TSM", "LLY", "JPM", "WMT", "V", "ORCL", "MA", "XOM", "NFLX", "COST",
    "UNH", "JNJ", "PG", "HD", "ABBV", "BAC", "AMD", "PLTR", "KO", "CRM",
    "CSCO", "IBM", "CVX", "MU", "GE", "WFC", "MS", "GS", "PM", "LIN", "MRK",
]

TOP_N = 10
OUT_FILE = Path(__file__).resolve().parent.parent / "site" / "data.json"


def safe_float(value) -> float | None:
    """Turn a value into a float, or None if it is missing/NaN."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def pct(new: float, old: float) -> float:
    return (new / old - 1.0) * 100.0


def estimate_next_week(closes: list[float]) -> dict:
    """Estimate the % change over the next 5 trading days.

    Method (deliberately simple so it can be explained):
      * Trend: fit a straight line to the log of the last ~60 daily closes.
        The slope is the average daily growth rate.
      * Shrink: real trends rarely continue at full strength, so we only
        trust half of that trend (multiply by 0.5).
      * Range: daily volatility (how much the price normally wiggles) scaled
        to 5 days gives a "typical" range around the estimate (about 68% of
        weeks would land inside it if the past repeats).
    This is an estimate, not a guarantee. The website says so.
    """
    window = closes[-60:]
    n = len(window)
    if n < 10:
        return {"expected_pct": 0.0, "low_pct": 0.0, "high_pct": 0.0, "confidence": "low"}

    logs = [math.log(c) for c in window]
    xs = list(range(n))
    x_mean = sum(xs) / n
    y_mean = sum(logs) / n
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, logs)) / sum(
        (x - x_mean) ** 2 for x in xs
    )

    daily_returns = [logs[i] - logs[i - 1] for i in range(1, n)]
    r_mean = sum(daily_returns) / len(daily_returns)
    daily_vol = math.sqrt(sum((r - r_mean) ** 2 for r in daily_returns) / (len(daily_returns) - 1))

    horizon = 5
    expected_log = 0.5 * slope * horizon
    spread = daily_vol * math.sqrt(horizon)

    expected = (math.exp(expected_log) - 1) * 100
    low = (math.exp(expected_log - spread) - 1) * 100
    high = (math.exp(expected_log + spread) - 1) * 100

    # How strong is the trend compared with the noise? Bigger = more confident.
    signal_to_noise = abs(expected_log) / spread if spread else 0
    confidence = "medium" if signal_to_noise > 0.35 else "low"

    return {
        "expected_pct": round(expected, 2),
        "low_pct": round(low, 2),
        "high_pct": round(high, 2),
        "confidence": confidence,
    }


# Extra names people use in headlines that the official name doesn't contain.
ALIASES = {
    "GOOGL": ["Google", "Alphabet"],
    "META": ["Meta", "Facebook", "Instagram"],
    "TSM": ["TSMC", "Taiwan Semiconductor"],
    "LLY": ["Lilly"],
    "BRK-B": ["Berkshire"],
    "PG": ["P&G", "Procter"],
    "JPM": ["JPMorgan"],
    "UNH": ["UnitedHealth"],
    "TSLA": ["Tesla"],
    "AVGO": ["Broadcom"],
}
# Endings to strip so "Apple Inc." -> "Apple", "NVIDIA Corporation" -> "NVIDIA".
NAME_SUFFIXES = re.compile(
    r"[,.]?\s+(inc|corp|corporation|company|co|ltd|limited|plc|holdings|group|"
    r"platforms|incorporated|manufacturing company)\.?$", re.IGNORECASE)


def company_keywords(symbol: str, name: str) -> list[str]:
    """Words that show an article is really about this company."""
    short = re.sub(r"^the\s+", "", name, flags=re.IGNORECASE)
    while True:  # strip suffixes repeatedly ("Meta Platforms, Inc." -> "Meta")
        trimmed = NAME_SUFFIXES.sub("", short).strip()
        trimmed = re.sub(r"\s+(and|&)$", "", trimmed)  # "Eli Lilly and" -> "Eli Lilly"
        if trimmed == short:
            break
        short = trimmed
    # Short company name first: get_news uses it as the search query.
    words = [short, symbol.split("-")[0], *ALIASES.get(symbol, [])]
    return list(dict.fromkeys(w for w in words if len(w) >= 2))  # drop duplicates, keep order


def mentions(text: str, keywords: list[str]) -> bool:
    """True if any keyword appears as a whole word (case-insensitive)."""
    return any(re.search(r"(?<!\w)" + re.escape(k) + r"(?!\w)", text, re.IGNORECASE)
               for k in keywords)


def parse_article(item: dict) -> dict | None:
    content = item.get("content", item)  # newer yfinance nests under "content"
    title = content.get("title")
    url = (
        (content.get("canonicalUrl") or {}).get("url")
        or (content.get("clickThroughUrl") or {}).get("url")
        or content.get("link")
    )
    if not (title and url):
        return None
    date = content.get("pubDate") or content.get("displayTime")
    if not date and content.get("providerPublishTime"):
        date = datetime.fromtimestamp(content["providerPublishTime"], timezone.utc).isoformat()
    return {
        "title": title,
        "url": url,
        "publisher": (content.get("provider") or {}).get("displayName")
                     or content.get("publisher") or "Unknown",
        "date": date,
        "summary": (content.get("summary") or "")[:300],
    }


def get_news(ticker: yf.Ticker, symbol: str, name: str, limit: int = 2) -> list[dict]:
    """Return up to `limit` recent articles that actually mention the company.

    Yahoo's news feed for a ticker often includes general market stories, so we
    pull ~30 articles and keep only ones naming the company. Headline mentions
    rank above summary-only mentions. If that isn't enough, we also try a
    Yahoo news search for the company name (filtered the same way).
    """
    keywords = company_keywords(symbol, name)
    raw = []
    try:
        raw += ticker.get_news(count=30) or []
    except Exception:
        pass
    try:
        raw += yf.Search(keywords[0] if keywords else symbol, news_count=10).news or []
    except Exception:
        pass

    in_title, in_summary, seen = [], [], set()
    for item in raw:
        art = parse_article(item)
        if not art or art["url"] in seen:
            continue
        seen.add(art["url"])
        if mentions(art["title"], keywords):
            in_title.append(art)
        elif mentions(art["summary"], keywords):
            in_summary.append(art)
    return (in_title + in_summary)[:limit]


def build_stock(symbol: str, ticker: yf.Ticker, history) -> dict:
    """Collect everything the website shows for one stock."""
    closes = [float(c) for c in history["Close"].dropna()]
    dates = [d.strftime("%Y-%m-%d") for d in history["Close"].dropna().index]

    try:
        info = ticker.info or {}
    except Exception:
        info = {}

    price = closes[-1]
    prev = closes[-2]
    week_ago = closes[-6] if len(closes) >= 6 else closes[0]
    month_ago = closes[-22] if len(closes) >= 22 else closes[0]

    week_change = pct(price, week_ago)
    week_daily = []
    for i in range(-5, 0):  # last 5 trading days, each labelled Rise or Fall
        change = pct(closes[i], closes[i - 1])
        week_daily.append({
            "date": dates[i],
            "close": round(closes[i], 2),
            "change_pct": round(change, 2),
            "direction": "Rise" if change >= 0 else "Fall",
        })

    return {
        "symbol": symbol,
        "name": info.get("longName") or info.get("shortName") or symbol,
        "price": round(price, 2),
        "currency": info.get("currency", "USD"),
        "market_cap": safe_float(ticker.fast_info.get("marketCap")),
        "day_change_pct": round(pct(price, prev), 2),
        "week_change_pct": round(week_change, 2),
        "week_direction": "Rise" if week_change >= 0 else "Fall",
        "month_change_pct": round(pct(price, month_ago), 2),
        "week_daily": week_daily,
        "history": [{"date": d, "close": round(c, 2)} for d, c in zip(dates, closes)],
        "status": {
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "pe_ratio": safe_float(info.get("trailingPE")),
            "fifty_two_week_high": safe_float(info.get("fiftyTwoWeekHigh")),
            "fifty_two_week_low": safe_float(info.get("fiftyTwoWeekLow")),
            "analyst_rating": info.get("recommendationKey"),
            "analyst_target": safe_float(info.get("targetMeanPrice")),
            "website": info.get("website"),
            "summary": (info.get("longBusinessSummary") or "")[:600],
        },
        "prediction": estimate_next_week(closes),
        "sources": get_news(ticker, symbol, info.get("longName") or info.get("shortName") or symbol),
        "quote_url": f"https://finance.yahoo.com/quote/{symbol}",
    }


def main() -> int:
    print(f"Downloading 3 months of prices for {len(CANDIDATES)} candidates...")
    prices = yf.download(CANDIDATES, period="3mo", interval="1d",
                         group_by="ticker", auto_adjust=True, progress=False)

    tickers = {s: yf.Ticker(s) for s in CANDIDATES}
    caps = {}
    for symbol, t in tickers.items():
        try:
            caps[symbol] = safe_float(t.fast_info["marketCap"]) or 0
        except Exception as exc:
            print(f"  skip {symbol}: {exc}")

    ranked = sorted(caps, key=caps.get, reverse=True)
    top = ranked[:TOP_N]
    print("Top 10 by market cap:", ", ".join(top))

    stocks = []
    for rank, symbol in enumerate(top, start=1):
        stock = build_stock(symbol, tickers[symbol], prices[symbol])
        stock["rank"] = rank
        stocks.append(stock)
        print(f"  #{rank} {symbol}: ${stock['price']}")

    # Rising stock: biggest 1-week gain among the rest of the pool.
    best, best_gain = None, -math.inf
    for symbol in ranked[TOP_N:]:
        closes = prices[symbol]["Close"].dropna()
        if len(closes) >= 6:
            gain = pct(float(closes.iloc[-1]), float(closes.iloc[-6]))
            if gain > best_gain:
                best, best_gain = symbol, gain
    rising = build_stock(best, tickers[best], prices[best]) if best else None
    if rising:
        print(f"Rising stock: {best} ({best_gain:+.2f}% this week)")

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "data_source": {"name": "Yahoo Finance (via yfinance)", "url": "https://finance.yahoo.com"},
        "stocks": stocks,
        "rising": rising,
    }
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"Wrote {OUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

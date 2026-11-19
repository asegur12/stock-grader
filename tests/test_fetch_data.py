"""Tests for scripts/fetch_data.py (the part that builds site/data.json).

Every test name starts with the requirement it checks (r1 = R1 in problem.md).
No test uses the internet: Yahoo Finance is replaced by fake objects with
made-up prices, market caps and news, so we know what the result should be.

Run from the repository folder:
    python -m unittest discover -s tests -v
"""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fetch_data as fd  # noqa: E402


# ------------------------------------------------------------ fake data --

def history(closes, end="2026-11-18"):
    """A price table like the one yfinance returns: one 'Close' per trading day."""
    days = pd.bdate_range(end=end, periods=len(closes))
    return pd.DataFrame({"Close": closes}, index=days)


def trending(start, daily_pct, n=30):
    """n closing prices that move about daily_pct % per day, with a small wiggle."""
    closes, price = [], start
    for i in range(n):
        price *= 1 + daily_pct / 100 + (0.003 if i % 2 else -0.003)
        closes.append(round(price, 2))
    return closes


def article(title, url, summary="", publisher="Reuters"):
    """A news item shaped like yfinance's news feed."""
    return {"content": {"title": title, "canonicalUrl": {"url": url},
                        "provider": {"displayName": publisher},
                        "pubDate": "2026-11-18T10:00:00Z", "summary": summary}}


class FakeTicker:
    """Stands in for yf.Ticker: market cap, company info and news."""

    def __init__(self, cap, info=None, news=None):
        self.fast_info = {"marketCap": cap}
        self.info = info or {}
        self.news = news or []

    def get_news(self, count=30):
        return self.news


def no_search(*args, **kwargs):
    """Stands in for yf.Search: pretend the search finds nothing."""
    return mock.Mock(news=[])


def company(symbol, cap):
    """A fake company whose news always has 2 articles naming it."""
    name = f"{symbol} Corp"
    return FakeTicker(cap, info={"longName": name, "sector": "Technology"}, news=[
        article(f"{symbol} reports record sales", f"https://news.example/{symbol}/1"),
        article(f"Analysts upgrade {symbol}", f"https://news.example/{symbol}/2"),
    ])


def run_main():
    """Run fetch_data.main() against 12 fake companies; return the data.json it writes.

    Market caps are deliberately out of order, so main() has to sort them.
    C11 and C12 are outside the top 10; C12 gained the most this week.
    """
    caps = {"C01": 3.0e12, "C02": 4.5e12, "C03": 1.0e12, "C04": 2.2e12, "C05": 0.9e12,
            "C06": 4.0e12, "C07": 1.5e12, "C08": 0.8e12, "C09": 2.0e12, "C10": 0.7e12,
            "C11": 0.5e12, "C12": 0.4e12}
    tickers = {s: company(s, cap) for s, cap in caps.items()}
    prices = {s: history(trending(100, 0.2)) for s in caps}
    prices["C11"] = history(trending(100, -1.0))   # falling: not the rising stock
    prices["C12"] = history(trending(100, 2.0))    # rising fastest outside the top 10

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "data.json"
        with mock.patch.object(fd, "CANDIDATES", list(caps)), \
                mock.patch.object(fd, "OUT_FILE", out), \
                mock.patch.object(fd.yf, "download", lambda *a, **k: prices), \
                mock.patch.object(fd.yf, "Ticker", lambda s: tickers[s]), \
                mock.patch.object(fd.yf, "Search", no_search), \
                redirect_stdout(io.StringIO()):
            fd.main()
        return json.loads(out.read_text(encoding="utf-8")), prices


# ----------------------------------------------------------------- tests --

class TopTenTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data, cls.prices = run_main()

    def test_r1_keeps_the_10_most_valuable_ranked_by_market_cap(self):
        """R1: exactly 10 companies, highest market cap first, ranked 1-10."""
        stocks = self.data["stocks"]
        self.assertEqual([s["symbol"] for s in stocks],
                         ["C02", "C06", "C01", "C04", "C09", "C07", "C03", "C05", "C08", "C10"])
        self.assertEqual([s["rank"] for s in stocks], list(range(1, 11)))

    def test_r1_price_is_the_latest_close(self):
        """R1: the price shown is what one share costs now (the latest close)."""
        for s in self.data["stocks"]:
            self.assertEqual(s["price"], round(self.prices[s["symbol"]]["Close"].iloc[-1], 2))

    def test_r2_history_has_every_past_close(self):
        """R2: the full price history is saved for the graphs."""
        s = self.data["stocks"][0]
        closes = list(self.prices[s["symbol"]]["Close"])
        self.assertEqual([h["close"] for h in s["history"]], closes)
        self.assertEqual(s["history"][-1]["close"], s["price"])

    def test_r7_every_company_has_2_sources(self):
        """R7: each company comes with 2 linked news sources."""
        for s in self.data["stocks"] + [self.data["rising"]]:
            self.assertEqual(len(s["sources"]), 2, s["symbol"])
            for src in s["sources"]:
                self.assertTrue(src["url"].startswith("https://"))

    def test_r8_rising_stock_is_the_biggest_weekly_gainer_outside_the_top_10(self):
        """R8: one rising stock, chosen from outside the top 10."""
        rising = self.data["rising"]
        self.assertEqual(rising["symbol"], "C12")
        self.assertNotIn("C12", [s["symbol"] for s in self.data["stocks"]])
        self.assertGreater(rising["week_change_pct"], 0)

    def test_r11_data_file_names_its_source(self):
        """R11: the data says where it came from, and each stock links its Yahoo page."""
        self.assertEqual(self.data["data_source"]["url"], "https://finance.yahoo.com")
        self.assertIn("Yahoo Finance", self.data["data_source"]["name"])
        for s in self.data["stocks"]:
            self.assertEqual(s["quote_url"], f"https://finance.yahoo.com/quote/{s['symbol']}")
            for src in s["sources"]:
                self.assertTrue(src["publisher"])


class StockDetailTests(unittest.TestCase):

    def test_r3_company_status_comes_from_todays_company_info(self):
        """R3: sector, industry, P/E, 52-week range and analyst view are saved."""
        info = {"longName": "Apple Inc.", "sector": "Technology",
                "industry": "Consumer Electronics", "trailingPE": 31.2,
                "fiftyTwoWeekHigh": 260.1, "fiftyTwoWeekLow": 164.08,
                "recommendationKey": "buy", "targetMeanPrice": 250.0}
        ticker = FakeTicker(3.9e12, info=info)
        with mock.patch.object(fd.yf, "Search", no_search):
            stock = fd.build_stock("AAPL", ticker, history(trending(200, 0.1)))
        self.assertEqual(stock["name"], "Apple Inc.")
        self.assertEqual(stock["status"]["sector"], "Technology")
        self.assertEqual(stock["status"]["industry"], "Consumer Electronics")
        self.assertEqual(stock["status"]["pe_ratio"], 31.2)
        self.assertEqual(stock["status"]["fifty_two_week_low"], 164.08)
        self.assertEqual(stock["status"]["analyst_rating"], "buy")

    def test_r3_missing_values_become_empty_not_errors(self):
        """R3: a company with no info still works (missing facts are left out)."""
        with mock.patch.object(fd.yf, "Search", no_search):
            stock = fd.build_stock("XYZ", FakeTicker(1e9), history(trending(50, 0.1)))
        self.assertEqual(stock["name"], "XYZ")
        self.assertIsNone(stock["status"]["pe_ratio"])
        self.assertIsNone(fd.safe_float(float("nan")))

    def test_r4_news_must_mention_the_company_headlines_first(self):
        """R4: general market stories are dropped; headline mentions come first."""
        ticker = FakeTicker(3.9e12, news=[
            article("Stocks drift as investors await jobs data", "https://n.example/1"),
            article("Tech shares climb", "https://n.example/2",
                    summary="Apple led gains after strong iPhone demand."),
            article("Apple unveils new chip", "https://n.example/3"),
            article("Apple unveils new chip", "https://n.example/3"),   # duplicate
        ])
        with mock.patch.object(fd.yf, "Search", no_search):
            news = fd.get_news(ticker, "AAPL", "Apple Inc.")
        self.assertEqual([a["url"] for a in news], ["https://n.example/3", "https://n.example/2"])

    def test_r4_company_names_match_whole_words_only(self):
        """R4: 'Apple' matches 'Apple shares', not 'Pineapple'; nicknames count too."""
        self.assertEqual(fd.company_keywords("AAPL", "Apple Inc."), ["Apple", "AAPL"])
        self.assertIn("Google", fd.company_keywords("GOOGL", "Alphabet Inc."))
        self.assertTrue(fd.mentions("Apple shares rise", ["Apple"]))
        self.assertFalse(fd.mentions("Pineapple prices rise", ["Apple"]))


class PredictionTests(unittest.TestCase):

    def test_r5_rising_prices_predict_a_rise(self):
        """R5: a steady climb gives a positive % estimate."""
        p = fd.estimate_next_week(trending(100, 0.5, n=60))
        self.assertGreater(p["expected_pct"], 0)

    def test_r5_falling_prices_predict_a_fall(self):
        """R5: a steady drop gives a negative % estimate."""
        p = fd.estimate_next_week(trending(100, -0.5, n=60))
        self.assertLess(p["expected_pct"], 0)

    def test_r5_estimate_sits_inside_its_likely_range(self):
        """R5: low <= estimate <= high, all as percentages."""
        p = fd.estimate_next_week(trending(100, 0.3, n=60))
        self.assertLessEqual(p["low_pct"], p["expected_pct"])
        self.assertLessEqual(p["expected_pct"], p["high_pct"])

    def test_r9_too_little_history_gives_no_guess(self):
        """R9: with under 10 days of past prices, the estimate is 0% and low confidence."""
        p = fd.estimate_next_week([100, 101, 102])
        self.assertEqual(p, {"expected_pct": 0.0, "low_pct": 0.0, "high_pct": 0.0,
                             "confidence": "low"})

    def test_r9_estimate_only_uses_the_last_60_days(self):
        """R9: prices older than 60 days don't change the estimate."""
        recent = trending(100, 0.4, n=60)
        self.assertEqual(fd.estimate_next_week(recent),
                         fd.estimate_next_week([1.0] * 40 + recent))


class PastWeekTests(unittest.TestCase):

    def test_r10_past_week_has_5_days_each_labeled_rise_or_fall(self):
        """R10: the last 5 trading days, each labeled by its own change."""
        closes = trending(100, 0.1, n=20)[:-5] + [101.0, 99.0, 99.5, 102.0, 100.0]
        with mock.patch.object(fd.yf, "Search", no_search):
            stock = fd.build_stock("XYZ", FakeTicker(1e9), history(closes))
        days = stock["week_daily"]
        self.assertEqual([d["close"] for d in days], [101.0, 99.0, 99.5, 102.0, 100.0])
        self.assertEqual([d["direction"] for d in days][1:], ["Fall", "Rise", "Rise", "Fall"])
        for d in days:
            self.assertEqual(d["direction"], "Rise" if d["change_pct"] >= 0 else "Fall")

    def test_r10_weekly_label_matches_the_weekly_change(self):
        """R10: the card's weekly Rise/Fall label agrees with the % change."""
        with mock.patch.object(fd.yf, "Search", no_search):
            up = fd.build_stock("UP", FakeTicker(1e9), history(trending(100, 1.0)))
            down = fd.build_stock("DN", FakeTicker(1e9), history(trending(100, -1.0)))
        self.assertEqual((up["week_direction"], down["week_direction"]), ("Rise", "Fall"))
        self.assertGreater(up["week_change_pct"], 0)
        self.assertLess(down["week_change_pct"], 0)


if __name__ == "__main__":
    unittest.main()

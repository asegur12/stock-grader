"""Tests for the website files in site/ (index.html, style.css, app.js).

These read the files as text and check that they contain what each requirement
needs. They do not open a real browser, so they can't click or hover; they check
that the click handler, hover rule, colors and text are there.

Every test name starts with the requirement it checks (r1 = R1 in problem.md).
"""

import re
import unittest
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"
HTML = (SITE / "index.html").read_text(encoding="utf-8")
CSS = (SITE / "style.css").read_text(encoding="utf-8")
JS = (SITE / "app.js").read_text(encoding="utf-8")


def rgb(hex_color):
    """'#12813a' or '#fff' -> (18, 129, 58)."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def css_var(name):
    return re.search(rf"--{name}:\s*(#[0-9a-fA-F]{{3,6}})", CSS).group(1)


class LayoutTests(unittest.TestCase):

    def test_r1_top_10_grid_comes_first_and_shows_share_price(self):
        """R1: the ranking grid is at the top of the page, with the price of 1 share."""
        self.assertLess(HTML.index('id="top-grid"'), HTML.index('id="rising-grid"'))
        self.assertIn("Top 10 ranking", HTML)
        self.assertIn("to buy 1 share", JS)
        self.assertIn('card(s, "#" + s.rank)', JS)

    def test_r2_cards_and_details_draw_price_charts(self):
        """R2: Chart.js is loaded; each card has a chart, and details offer 1W/1M/3M."""
        self.assertRegex(HTML, r'<script src="https://[^"]*chart\.umd\.min\.js">')
        self.assertIn('<canvas></canvas>', JS)
        self.assertEqual(JS.count("new Chart("), 2)          # card sparkline + detail chart
        for label in (">1W<", ">1M<", ">3M<"):
            self.assertIn(label, JS)

    def test_r3_clicking_a_card_opens_its_status(self):
        """R3: a click (or Enter key) opens the detail view with today's status."""
        self.assertIn('addEventListener("click"', JS)
        self.assertIn("openDetail(s)", JS)
        self.assertIn("Status as of", JS)
        self.assertIn("Company status", JS)

    def test_r4_detail_view_lists_news(self):
        """R4: the detail view has a news section built from each stock's sources."""
        self.assertIn("News that could affect the price", JS)
        self.assertIn("s.sources.map", JS)

    def test_r5_every_card_shows_a_percent_estimate(self):
        """R5: each card shows 'Est. next week' as a signed percentage."""
        self.assertIn("${predictionHtml(s.prediction)}", JS)
        self.assertIn("Est. next week: <b>${signed(p.expected_pct)}</b>", JS)
        self.assertIn('n.toFixed(2) + "%"', JS)

    def test_r8_rising_stock_has_its_own_grid_below_the_top_10(self):
        """R8: a separate 'Rising stock' grid after the top 10 grid."""
        self.assertIn("Rising stock", HTML)
        self.assertIn('rising.appendChild(card(DATA.rising, "Rising"))', JS)


class ColorTests(unittest.TestCase):

    def test_r6_page_is_black_on_white(self):
        """R6: white background, black text."""
        self.assertEqual(rgb(css_var("bg")), (255, 255, 255))
        self.assertEqual(rgb(css_var("fg")), (0, 0, 0))

    def test_r6_green_means_rise_red_means_fall_yellow_means_estimate(self):
        """R6: --up is green, --down is red, --est is yellow, and they are used that way."""
        r, g, b = rgb(css_var("up"))
        self.assertTrue(g > r and g > b, "--up should be green")
        r, g, b = rgb(css_var("down"))
        self.assertTrue(r > g and r > b, "--down should be red")
        r, g, b = rgb(css_var("est"))
        self.assertTrue(r > 200 and g > 150 and b < 80, "--est should be yellow")
        self.assertRegex(CSS, r"\.up\s*\{\s*color:\s*var\(--up\)")
        self.assertRegex(CSS, r"\.down\s*\{\s*color:\s*var\(--down\)")
        self.assertIn('const cls = (n) => (n >= 0 ? "up" : "down");', JS)

    def test_r6_no_other_colors_are_used(self):
        """R6: every color is gray-scale, or the green / red / yellow that carry meaning."""
        meaning = {css_var("up").lower(), css_var("down").lower()}
        for color in re.findall(r"#[0-9a-fA-F]{3,6}\b", CSS + JS):
            r, g, b = rgb(color)
            gray = r == g == b
            yellow = r > 100 and g > 80 and b < g and r >= g     # yellow shades only
            self.assertTrue(gray or yellow or color.lower() in meaning,
                            f"unexpected color {color}")

    def test_r6_chart_lines_use_the_same_green_and_red(self):
        """R6: the charts' rise/fall colors match the stylesheet."""
        self.assertIn(f'const UP = "{css_var("up")}", DOWN = "{css_var("down")}"', JS)


class SourcesTests(unittest.TestCase):

    def test_r7_sources_appear_only_on_hover(self):
        """R7: the sources popup is hidden until the card is hovered (or focused)."""
        self.assertRegex(CSS, r"\.sources-pop\s*\{\s*display:\s*none")
        self.assertRegex(CSS, r"\.card:hover \.sources-pop[^{]*\{\s*display:\s*block")
        self.assertIn('<div class="sources-pop"><b>Sources for', JS)

    def test_r9_disclaimer_says_the_estimate_is_not_proof(self):
        """R9: a page-wide disclaimer, plus a note in every estimate box."""
        self.assertIn("Estimate disclaimer", HTML)
        self.assertIn("not</em> concrete proof", HTML)
        self.assertIn("Estimate only, not concrete proof.", JS)

    def test_r10_detail_view_has_a_day_by_day_rise_fall_table(self):
        """R10: the past week's closes, each with its Rise/Fall label."""
        self.assertIn("Past week, day by day", JS)
        self.assertIn("<b>${d.direction}</b>", JS)

    def test_r11_page_credits_yahoo_finance(self):
        """R11: the footer names and links the data source; details link each stock's page."""
        self.assertIn('href="https://finance.yahoo.com"', HTML)
        self.assertIn("Prices, company data and news", HTML)
        self.assertIn("Source: <a href=\"${esc(s.quote_url)}\"", JS)


if __name__ == "__main__":
    unittest.main()

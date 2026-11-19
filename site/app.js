// Stock Grader front end: reads data.json and draws the grids, charts and detail view.

const UP = "#12813a", DOWN = "#c8102e";
const money = (n) => "$" + Number(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const signed = (n) => (n >= 0 ? "+" : "") + n.toFixed(2) + "%";
const cls = (n) => (n >= 0 ? "up" : "down");
const bigMoney = (n) => {
  if (!n) return "n/a";
  if (n >= 1e12) return "$" + (n / 1e12).toFixed(2) + "T";
  if (n >= 1e9) return "$" + (n / 1e9).toFixed(1) + "B";
  return money(n);
};
// Escape text from the data file before putting it into HTML.
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtDate = (iso) => (iso ? new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "");

let DATA = null;

async function main() {
  try {
    const res = await fetch("data.json", { cache: "no-store" });
    DATA = await res.json();
  } catch (e) {
    document.getElementById("top-grid").innerHTML =
      "<p>Could not load data.json. If you opened index.html directly from disk, run a local server instead (see README).</p>";
    return;
  }
  document.getElementById("asof").textContent = "Data as of " + new Date(DATA.generated_at).toLocaleString();

  const top = document.getElementById("top-grid");
  DATA.stocks.forEach((s) => top.appendChild(card(s, "#" + s.rank)));

  const rising = document.getElementById("rising-grid");
  if (DATA.rising) rising.appendChild(card(DATA.rising, "Rising"));
  else rising.textContent = "No rising stock found this week.";

  // A link like index.html#NVDA opens that stock's details directly.
  const wanted = decodeURIComponent(location.hash.slice(1)).toUpperCase();
  const match = [...DATA.stocks, DATA.rising].find((s) => s && s.symbol === wanted);
  if (match) openDetail(match);
}

function predictionHtml(p) {
  return `<div class="estimate">
      Est. next week: <b>${signed(p.expected_pct)}</b>
      <span class="fine">Likely range ${signed(p.low_pct)} to ${signed(p.high_pct)}.
      Estimate only, not concrete proof.</span>
    </div>`;
}

function sourcesHtml(s) {
  if (!s.sources.length) return "<p>No recent news found.</p>";
  return "<ol>" + s.sources.map((a) =>
    `<li><a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.title)}</a> (${esc(a.publisher)})</li>`
  ).join("") + "</ol>";
}

function card(s, label) {
  const el = document.createElement("div");
  el.className = "card";
  el.tabIndex = 0;
  el.setAttribute("role", "button");
  el.setAttribute("aria-label", `${s.name}: open details`);
  el.innerHTML = `
    <div class="row"><span class="rank">${esc(label)}</span>
      <span class="tag ${cls(s.week_change_pct)}">${s.week_direction} ${signed(s.week_change_pct)} 1W</span></div>
    <div class="row" style="margin-top:6px"><span class="symbol">${esc(s.symbol)}</span></div>
    <div class="name" title="${esc(s.name)}">${esc(s.name)}</div>
    <div class="price">${money(s.price)} <small>to buy 1 share</small></div>
    <div class="spark"><canvas></canvas></div>
    <div class="row" style="font-size:13px">
      <span>Today <b class="${cls(s.day_change_pct)}">${signed(s.day_change_pct)}</b></span>
      <span>Mkt cap ${bigMoney(s.market_cap)}</span></div>
    ${predictionHtml(s.prediction)}
    <div class="sources-pop"><b>Sources for ${esc(s.symbol)}</b>${sourcesHtml(s)}</div>`;

  // Clicking a link in the popover should open the link, not the dialog.
  el.addEventListener("click", (e) => { if (!e.target.closest("a")) openDetail(s); });
  el.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openDetail(s); } });

  // Sparkline: last 6 closes = the past week (5 changes).
  const week = s.history.slice(-6);
  requestAnimationFrame(() => new Chart(el.querySelector("canvas"), {
    type: "line",
    data: { labels: week.map((h) => h.date), datasets: [{ data: week.map((h) => h.close),
      borderColor: s.week_change_pct >= 0 ? UP : DOWN, borderWidth: 2, pointRadius: 0, tension: 0.25 }] },
    options: { responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: { x: { display: false }, y: { display: false } } },
  }));
  return el;
}

let detailChart = null;

function drawDetailChart(s, days) {
  const hist = s.history.slice(-days);
  const first = hist[0].close, last = hist[hist.length - 1].close;
  const color = last >= first ? UP : DOWN;
  if (detailChart) detailChart.destroy();
  detailChart = new Chart(document.getElementById("d-chart"), {
    type: "line",
    data: { labels: hist.map((h) => h.date), datasets: [{ label: s.symbol, data: hist.map((h) => h.close),
      borderColor: color, backgroundColor: color + "22", fill: true, borderWidth: 2,
      pointRadius: days <= 6 ? 4 : 0, tension: 0.2 }] },
    options: { responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => money(c.parsed.y) } } },
      scales: { x: { ticks: { color: "#000", maxTicksLimit: 8 }, grid: { display: false } },
        y: { ticks: { color: "#000", callback: (v) => "$" + v }, grid: { color: "#e5e5e5" } } } },
  });
}

function openDetail(s) {
  const st = s.status, p = s.prediction;
  const fact = (k, v) => (v === null || v === undefined || v === "" ? "" : `<dt>${k}</dt><dd>${v}</dd>`);
  const weekRows = s.week_daily.map((d) =>
    `<tr><td>${d.date}</td><td class="num">${money(d.close)}</td>
     <td class="num ${cls(d.change_pct)}">${signed(d.change_pct)}</td>
     <td class="${cls(d.change_pct)}"><b>${d.direction}</b></td></tr>`).join("");
  const news = s.sources.length
    ? s.sources.map((a) => `<li><a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.title)}</a>
        <div class="meta">${esc(a.publisher)} · ${fmtDate(a.date)}</div>
        ${a.summary ? `<div class="summary">${esc(a.summary)}</div>` : ""}</li>`).join("")
    : "<li>No recent news found.</li>";

  document.getElementById("detail-body").innerHTML = `
    <div class="d-head">
      <h3 id="d-title">${esc(s.name)} (${esc(s.symbol)})</h3>
      <p>Status as of ${new Date(DATA.generated_at).toLocaleDateString("en-US", { dateStyle: "long" })}
        · ${esc(st.sector ?? "")}${st.industry ? " / " + esc(st.industry) : ""}</p>
    </div>
    <div class="row" style="display:flex;gap:16px;flex-wrap:wrap;align-items:baseline;margin-top:10px">
      <span class="price">${money(s.price)} <small>per share</small></span>
      <span class="tag ${cls(s.week_change_pct)}">Past week: ${s.week_direction} ${signed(s.week_change_pct)}</span>
      <span class="tag ${cls(s.month_change_pct)}">Past month: ${signed(s.month_change_pct)}</span>
    </div>
    <div class="ranges" role="group" aria-label="Chart range">
      <button data-days="6" aria-pressed="true">1W</button>
      <button data-days="22" aria-pressed="false">1M</button>
      <button data-days="9999" aria-pressed="false">3M</button>
    </div>
    <div class="chart-box"><canvas id="d-chart"></canvas></div>
    ${predictionHtml(p)}
    <div class="cols">
      <div>
        <h4>Past week, day by day</h4>
        <table><thead><tr><th>Date</th><th class="num">Close</th><th class="num">Change</th><th>Move</th></tr></thead>
        <tbody>${weekRows}</tbody></table>
        <h4>Company status</h4>
        <dl class="facts">
          ${fact("Market cap", bigMoney(s.market_cap))}
          ${fact("P/E ratio", st.pe_ratio ? st.pe_ratio.toFixed(1) : null)}
          ${fact("52-week range", st.fifty_two_week_low && st.fifty_two_week_high ? money(st.fifty_two_week_low) + " to " + money(st.fifty_two_week_high) : null)}
          ${fact("Analyst view", st.analyst_rating ? esc(st.analyst_rating.replace(/_/g, " ")) : null)}
          ${fact("Analyst target", st.analyst_target ? money(st.analyst_target) : null)}
          ${fact("Website", st.website ? `<a href="${esc(st.website)}" target="_blank" rel="noopener">${esc(st.website.replace(/^https?:\/\//, ""))}</a>` : null)}
        </dl>
      </div>
      <div>
        <h4>News that could affect the price</h4>
        <ol class="news">${news}</ol>
        <h4>About</h4>
        <p class="summary">${esc(st.summary)}${st.summary.length >= 600 ? "…" : ""}</p>
        <p class="summary">Source: <a href="${esc(s.quote_url)}" target="_blank" rel="noopener">Yahoo Finance: ${esc(s.symbol)}</a></p>
      </div>
    </div>`;

  const dlg = document.getElementById("detail");
  dlg.showModal();
  drawDetailChart(s, 6);
  dlg.querySelectorAll(".ranges button").forEach((b) => b.addEventListener("click", () => {
    dlg.querySelectorAll(".ranges button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    drawDetailChart(s, Number(b.dataset.days));
  }));
}

// Close the dialog when clicking the dark backdrop.
document.getElementById("detail").addEventListener("click", (e) => { if (e.target.id === "detail") e.target.close(); });

main();

/**
 * KE/OZ Flight Price Monitor
 * Vanilla JS dashboard. Reads data/prices.json and renders:
 *   - Latest price cards (KE vs OZ, with day-over-day delta)
 *   - 90-day Chart.js line chart with toggleable airlines
 *   - Stats panel (min, max, avg, 30d avg, recommendation)
 *   - Recent snapshots table (last 14 entries)
 */

(() => {
  "use strict";

  // ---------------------------------------------------------------- state
  let DATA = null;
  let currentRouteIdx = 0;
  let chart = null;

  const KE_COLOR = "#00256C";
  const OZ_COLOR = "#C8102E";

  const els = {
    headerUpdated: document.getElementById("meta-updated"),
    headerCurrency: document.getElementById("meta-currency"),
    dataNote: document.getElementById("data-note"),
    routeTabs: document.getElementById("route-tabs"),
    cardsGrid: document.getElementById("cards-grid"),
    chartCanvas: document.getElementById("price-chart"),
    showKe: document.getElementById("show-ke"),
    showOz: document.getElementById("show-oz"),
    statsGrid: document.getElementById("stats-grid"),
    snapshotTbody: document.getElementById("snapshot-tbody"),
  };

  // ---------------------------------------------------------------- utils
  const fmtMoney = (n) => {
    const sym = (DATA && DATA.meta && DATA.meta.currency) || "USD";
    const symbols = { USD: "$", EUR: "€", GBP: "£", KRW: "₩", JPY: "¥" };
    const sym_str = symbols[sym] || sym + " ";
    const rounded = Math.round(Math.abs(n)).toLocaleString("en-US");
    const sign = n < 0 ? "−" : "";
    return sign + sym_str + rounded;
  };
  const fmtDate = (iso) => {
    const d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  };
  const fmtDateShort = (iso) => {
    const d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  };

  const pctChange = (prev, curr) => {
    if (!prev) return 0;
    return ((curr - prev) / prev) * 100;
  };

  const stats = (series) => {
    if (!series.length) return null;
    const prices = series.map((s) => s.price);
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const avg = prices.reduce((a, b) => a + b, 0) / prices.length;
    const last30 = prices.slice(-30);
    const avg30 = last30.reduce((a, b) => a + b, 0) / last30.length;
    const min30 = Math.min(...last30);
    return { min, max, avg, avg30, min30, latest: prices[prices.length - 1] };
  };

  // ---------------------------------------------------------------- init
  async function init() {
    try {
      const res = await fetch("data/prices.json", { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      DATA = await res.json();
    } catch (err) {
      document.querySelector("main").innerHTML =
        `<div class="state-msg error">Failed to load price data.<br><small>${err.message}</small></div>`;
      return;
    }

    renderHeader();
    renderTabs();
    renderRoute();
  }

  // ---------------------------------------------------------------- header
  function renderHeader() {
    const genDate = fmtDate(DATA.meta.generated_at);
    els.headerUpdated.textContent = `Updated: ${genDate}`;
    els.headerCurrency.textContent =
      `${DATA.meta.currency} · ${DATA.meta.cabin.replace(/-/g, " ")}`;
    if (DATA.meta.note) {
      els.dataNote.textContent = "· " + DATA.meta.note;
    }
  }

  // ---------------------------------------------------------------- tabs
  function renderTabs() {
    els.routeTabs.innerHTML = "";
    DATA.routes.forEach((r, i) => {
      const btn = document.createElement("button");
      btn.className = "route-tab" + (i === currentRouteIdx ? " active" : "");
      btn.textContent = `${r.origin} ↔ ${r.destination}`;
      btn.addEventListener("click", () => {
        currentRouteIdx = i;
        document.querySelectorAll(".route-tab").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        renderRoute();
      });
      els.routeTabs.appendChild(btn);
    });
  }

  // ---------------------------------------------------------------- route
  function renderRoute() {
    const r = DATA.routes[currentRouteIdx];
    renderCards(r);
    renderChart(r);
    renderStats(r);
    renderTable(r);
  }

  // ---------------------------------------------------------------- cards
  function renderCards(r) {
    const keSeries = r.ke;
    const ozSeries = r.oz;
    const keLatest = keSeries[keSeries.length - 1];
    const ozLatest = ozSeries[ozSeries.length - 1];
    const kePrev = keSeries[keSeries.length - 2] || keLatest;
    const ozPrev = ozSeries[ozSeries.length - 2] || ozLatest;

    const kePct = pctChange(kePrev.price, keLatest.price);
    const ozPct = pctChange(ozPrev.price, ozLatest.price);

    const cheaper = keLatest.price < ozLatest.price ? "ke" :
                    keLatest.price > ozLatest.price ? "oz" : "tie";

    const routeLabel = `${r.origin_city} ↔ ${r.destination_city}`;
    const cur = (DATA && DATA.meta && DATA.meta.currency) || "USD";

    const card = (airline, latest, pct, isRecommend) => `
      <article class="price-card ${airline} ${isRecommend ? "recommend" : ""}">
        ${isRecommend ? `<span class="card-badge">Better deal</span>` : ""}
        <div class="card-airline">
          <span class="airline-dot"></span>
          ${airline === "ke" ? "Korean Air (KE)" : "Asiana Airlines (OZ)"}
        </div>
        <div class="card-price"><span class="currency">${cur}</span>${Math.round(latest.price).toLocaleString()}</div>
        <div class="card-delta ${pct > 0.3 ? "up" : pct < -0.3 ? "down" : "flat"}">
          ${pct > 0.3 ? "▲" : pct < -0.3 ? "▼" : "→"}
          ${pct > 0 ? "+" : ""}${pct.toFixed(1)}% vs yesterday
        </div>
        <div class="card-footnote">${routeLabel} · ${fmtDate(latest.date)}</div>
      </article>
    `;

    els.cardsGrid.innerHTML =
      card("ke", keLatest, kePct, cheaper === "ke") +
      card("oz", ozLatest, ozPct, cheaper === "oz") +
      `
      <article class="price-card">
        <div class="card-airline">Difference</div>
        <div class="card-price">
          ${keLatest.price > ozLatest.price
            ? `<span style="color:var(--oz-red)">${fmtMoney(keLatest.price - ozLatest.price)}</span>`
            : keLatest.price < ozLatest.price
              ? `<span style="color:var(--ke-blue)">${fmtMoney(ozLatest.price - keLatest.price)}</span>`
              : `<span style="color:var(--text-soft)">$0</span>`}
        </div>
        <div class="card-footnote">
          ${cheaper === "ke" ? "Korean Air is cheaper today" :
            cheaper === "oz" ? "Asiana is cheaper today" :
            "Same price today"}
        </div>
      </article>`;
  }

  // ---------------------------------------------------------------- chart
  function renderChart(r) {
    const labels = r.ke.map((s) => fmtDateShort(s.date));
    const kePrices = r.ke.map((s) => s.price);
    const ozPrices = r.oz.map((s) => s.price);

    const datasets = [
      {
        label: "Korean Air (KE)",
        data: kePrices,
        borderColor: KE_COLOR,
        backgroundColor: "rgba(0, 37, 108, 0.08)",
        borderWidth: 2,
        pointRadius: 0,
        pointHoverRadius: 4,
        tension: 0.25,
        fill: false,
        hidden: !els.showKe.checked,
      },
      {
        label: "Asiana (OZ)",
        data: ozPrices,
        borderColor: OZ_COLOR,
        backgroundColor: "rgba(200, 16, 46, 0.08)",
        borderWidth: 2,
        pointRadius: 0,
        pointHoverRadius: 4,
        tension: 0.25,
        fill: false,
        hidden: !els.showOz.checked,
      },
    ];

    if (chart) chart.destroy();
    chart = new Chart(els.chartCanvas, {
      type: "line",
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: {
            position: "bottom",
            labels: { boxWidth: 10, boxHeight: 10, padding: 14, usePointStyle: true, pointStyle: "rectRounded" },
          },
          tooltip: {
            backgroundColor: "rgba(15, 27, 45, 0.92)",
            padding: 10,
            cornerRadius: 6,
            titleFont: { weight: "600" },
            callbacks: {
              label: (ctx) => `${ctx.dataset.label}: ${fmtMoney(ctx.parsed.y)}`,
            },
          },
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { maxTicksLimit: 8, color: "#8793a4", font: { size: 11 } },
          },
          y: {
            grid: { color: "rgba(0,0,0,0.05)" },
            ticks: {
              color: "#8793a4",
              font: { size: 11 },
              callback: (v) => fmtMoney(v),
            },
            title: { display: true, text: `${(DATA && DATA.meta && DATA.meta.currency) || "USD"} round-trip economy`, color: "#8793a4", font: { size: 11 } },
          },
        },
      },
    });
  }

  // ---------------------------------------------------------------- stats
  function renderStats(r) {
    const keS = stats(r.ke);
    const ozS = stats(r.oz);

    const cheaperOverall = keS.avg < ozS.avg ? "Korean Air" : "Asiana Airlines";
    const cheaperAvg = Math.min(keS.avg, ozS.avg);
    const pricierAvg = Math.max(keS.avg, ozS.avg);
    const savingsPct = ((pricierAvg - cheaperAvg) / pricierAvg) * 100;

    // Buy recommendation: is current price within 5% of 30-day min?
    const keBuyScore = ((keS.latest - keS.min30) / keS.min30) * 100;
    const ozBuyScore = ((ozS.latest - ozS.min30) / ozS.min30) * 100;

    let recommendation;
    if (keBuyScore < 5 && ozBuyScore < 5) {
      recommendation = `Both airlines are near 30-day lows — good time to book either. KE at ${fmtMoney(keS.latest)} (avg30 ${fmtMoney(keS.avg30)}), OZ at ${fmtMoney(ozS.latest)} (avg30 ${fmtMoney(ozS.avg30)}).`;
    } else if (keBuyScore < ozBuyScore) {
      recommendation = `Korean Air is closer to its 30-day low (+${keBuyScore.toFixed(1)}% above min). Consider booking KE if dates work.`;
    } else if (ozBuyScore < keBuyScore) {
      recommendation = `Asiana is closer to its 30-day low (+${ozBuyScore.toFixed(1)}% above min). Consider booking OZ if dates work.`;
    } else {
      recommendation = `Both are well above recent lows (KE +${keBuyScore.toFixed(1)}%, OZ +${ozBuyScore.toFixed(1)}%). Waiting may pay off.`;
    }

    els.statsGrid.innerHTML = `
      <div class="stat">
        <div class="stat-label">KE 90-day low</div>
        <div class="stat-value good">${fmtMoney(keS.min)}</div>
        <div class="stat-hint">Avg ${fmtMoney(keS.avg)} · High ${fmtMoney(keS.max)}</div>
      </div>
      <div class="stat">
        <div class="stat-label">OZ 90-day low</div>
        <div class="stat-value good">${fmtMoney(ozS.min)}</div>
        <div class="stat-hint">Avg ${fmtMoney(ozS.avg)} · High ${fmtMoney(ozS.max)}</div>
      </div>
      <div class="stat">
        <div class="stat-label">KE 30-day avg</div>
        <div class="stat-value">${fmtMoney(keS.avg30)}</div>
        <div class="stat-hint">Latest ${fmtMoney(keS.latest)}</div>
      </div>
      <div class="stat">
        <div class="stat-label">OZ 30-day avg</div>
        <div class="stat-value">${fmtMoney(ozS.avg30)}</div>
        <div class="stat-hint">Latest ${fmtMoney(ozS.latest)}</div>
      </div>
      <div class="stat">
        <div class="stat-label">Cheaper on average</div>
        <div class="stat-value">${cheaperOverall}</div>
        <div class="stat-hint">~${savingsPct.toFixed(1)}% lower over 90 days</div>
      </div>
      <div class="recommend-box">
        <div class="stat-label">Recommendation</div>
        <div class="stat-value">${recommendation}</div>
      </div>
    `;
  }

  // ---------------------------------------------------------------- table
  function renderTable(r) {
    const n = Math.min(14, r.ke.length);
    const rows = [];
    for (let i = r.ke.length - 1; i >= r.ke.length - n; i--) {
      const ke = r.ke[i];
      const oz = r.oz[i];
      const diff = ke.price - oz.price;
      let cheaperCell;
      if (diff > 0) {
        cheaperCell = `<td class="cheaper-oz">Asiana</td>`;
      } else if (diff < 0) {
        cheaperCell = `<td class="cheaper-ke">Korean Air</td>`;
      } else {
        cheaperCell = `<td class="cheaper-tie">Tie</td>`;
      }
      const diffClass = diff > 0 ? "cheaper-oz" : diff < 0 ? "cheaper-ke" : "cheaper-tie";
      const diffSign = diff > 0 ? "+" : "";
      rows.push(`
        <tr>
          <td>${fmtDate(ke.date)}</td>
          <td class="num">${fmtMoney(ke.price)}</td>
          <td class="num">${fmtMoney(oz.price)}</td>
          <td class="num ${diffClass}">${diffSign}${fmtMoney(Math.abs(diff))}</td>
          ${cheaperCell}
        </tr>
      `);
    }
    els.snapshotTbody.innerHTML = rows.join("");
  }

  // ---------------------------------------------------------------- events
  els.showKe.addEventListener("change", () => {
    if (chart) {
      chart.data.datasets[0].hidden = !els.showKe.checked;
      chart.update();
    }
  });
  els.showOz.addEventListener("change", () => {
    if (chart) {
      chart.data.datasets[1].hidden = !els.showOz.checked;
      chart.update();
    }
  });

  // ---------------------------------------------------------------- go
  document.addEventListener("DOMContentLoaded", init);
})();

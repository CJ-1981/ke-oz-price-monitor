# KE / OZ Flight Price Monitor

A static web app for monitoring **Korean Air (KE)** and **Asiana Airlines (OZ)**
flight prices from Seoul Incheon (ICN) to the United States.

Built for **GitHub Pages** — no backend required. Price snapshots are fetched
daily by a GitHub Actions cron job and committed to `data/prices.json`, which
the frontend reads at load time.

---

## Features

- **Three routes** out of the box: ICN ↔ LAX, ICN ↔ JFK, ICN ↔ SFO
- **Side-by-side cards** showing latest KE and OZ prices with day-over-day delta
- **90-day line chart** (Chart.js) with toggleable airlines
- **Stats panel**: 90-day low/high/avg, 30-day avg, average cheaper airline,
  plus a plain-English booking recommendation
- **Recent snapshots table** (last 14 days) with cheaper-airline highlight
- **Mobile-responsive** layout
- **Brand-colored theme**: KE blue `#00256C`, OZ red `#C8102E`
- **No build step, no framework** — just HTML/CSS/vanilla JS

---

## File structure

```
flight-price-monitor/
├── index.html                  # Dashboard markup
├── css/styles.css              # All styling
├── js/app.js                   # Dashboard logic (vanilla JS + Chart.js)
├── data/prices.json            # 90-day snapshots (mock data initially)
├── scripts/
│   └── fetch_prices.py         # Amadeus API fetcher (run by GitHub Actions)
├── .github/workflows/
│   ├── fetch-prices.yml        # Daily cron: fetch prices, commit JSON
│   └── deploy.yml              # Deploy static site to GitHub Pages
└── README.md
```

---

## Quick start (local preview)

The site is static — any HTTP server works. Pick one:

```bash
# Option 1: Python
cd flight-price-monitor
python3 -m http.server 8000
# open http://localhost:8000

# Option 2: Node
npx serve flight-price-monitor
```

The repo ships with **mock data** in `data/prices.json` so you can see the
dashboard working immediately without setting up any API keys.

---

## Deploying to GitHub Pages

### Option A — Branch-based (simplest)

1. Create a new GitHub repo, e.g. `ke-oz-price-monitor`.
2. Push this folder's contents to the `main` branch:
   ```bash
   cd flight-price-monitor
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin git@github.com:YOUR_USERNAME/ke-oz-price-monitor.git
   git push -u origin main
   ```
3. In the repo: **Settings → Pages → Build and deployment → Source = Deploy from a branch**, then pick `main` / `/ (root)`.
4. Wait ~1 minute. Your site will be live at:
   ```
   https://YOUR_USERNAME.github.io/ke-oz-price-monitor/
   ```

### Option B — Actions-based (recommended if you want CI control)

1. Follow step 1–2 above.
2. In **Settings → Pages → Source**, choose **GitHub Actions**.
3. The included `.github/workflows/deploy.yml` will build & deploy on every
   push to `main`.

---

## Enabling live prices (Amadeus API)

The default `data/prices.json` contains mock data. To switch to live snapshots:

### 1. Get Amadeus API credentials

1. Sign up at <https://developers.amadeus.com/> (free).
2. Create a self-service app.
3. Copy your **API key** (`client_id`) and **API secret** (`client_secret`).

The free tier allows ~2,000 calls/month — plenty for 3 routes × 1 daily run
(~90 calls/month).

### 2. Add credentials as repo secrets

In your GitHub repo: **Settings → Secrets and variables → Actions → New repository secret**

| Name | Value |
|------|-------|
| `AMADEUS_CLIENT_ID` | your client_id |
| `AMADEUS_CLIENT_SECRET` | your client_secret |

### 3. Enable the workflow

`.github/workflows/fetch-prices.yml` runs daily at 09:00 UTC (~6 PM KST).
You can also trigger it manually from the **Actions** tab → "Fetch flight
prices" → "Run workflow".

The workflow:
1. Calls `scripts/fetch_prices.py`, which queries Amadeus for each route.
2. Picks the cheapest KE and OZ economy round-trip offer.
3. Appends today's snapshot to `data/prices.json` (preserving history).
4. Commits the file back to `main`, which triggers a Pages redeploy.

### 4. Switch from test to production API (optional)

By default the script uses `test.api.amadeus.com`. To use the production
endpoint (higher rate limits), set the `AMADEUS_HOST` env var in the workflow
to `api.amadeus.com`.

---

## Customizing routes

Edit the `ROUTES` list in **two** places:

- `scripts/generate_mock_prices.py` (mock data baseline prices)
- `scripts/fetch_prices.py` (live API calls)

Then regenerate mock data:
```bash
python3 scripts/generate_mock_prices.py
```

Common IATA codes you may want:
- **Asia hubs**: ICN (Seoul Incheon), NRT (Tokyo Narita), KIX (Osaka),
  BKK (Bangkok), SIN (Singapore), TPE (Taipei), HKG (Hong Kong)
- **US hubs**: LAX, JFK, SFO, ORD (Chicago), SEA (Seattle), ATL (Atlanta),
  DFW (Dallas), IAD (Washington Dulles), EWR (Newark)

---

## How it works

```
GitHub Actions (daily cron)
        ↓
  Amadeus Flight Offers API
        ↓
  fetch_prices.py picks cheapest KE + OZ per route
        ↓
  data/prices.json committed to repo
        ↓
  GitHub Pages serves the static site
        ↓
  app.js fetches prices.json → renders chart + cards + table
```

API keys live **only** in GitHub Actions secrets — they never appear in the
browser bundle, so they're safe.

---

## Limitations

- **Prices are snapshots, not live quotes.** A snapshot taken at 09:00 UTC may
  not match what you see on the airline site at 21:00 UTC. Use the dashboard
  for trend tracking, then verify before booking.
- **Amadeus test environment** doesn't always return real-time inventory for
  every airline on every route. Korean Air (KE) and Asiana (OZ) are both
  covered, but if a route returns 0 offers, the snapshot is simply skipped
  for that day.
- **No alerts in this version.** If you want email/push notifications, the
  easiest path is to extend `fetch_prices.py` to call EmailJS or SendGrid
  when a price drops below your threshold.

---

## Tech stack

- HTML5 + CSS3 (custom properties, grid, flexbox)
- Vanilla JavaScript (no framework, no bundler)
- [Chart.js 4](https://www.chartjs.org/) via CDN
- Python 3 stdlib only (no pip dependencies) for the fetcher
- GitHub Actions for cron + deploy

---

## License

MIT — do whatever you want.

# KE / OZ Flight Price Monitor

A static web app for monitoring **Korean Air (KE)** and **Asiana Airlines (OZ)**
flight prices on popular long-haul routes (FRA↔ICN, ICN↔LAX/JFK/SFO).

Built for **GitHub Pages** — no backend required. Price snapshots are fetched
daily by a GitHub Actions cron job using the **Duffel API** and committed to
`data/prices.json`, which the frontend reads at load time.

---

## Features

- **Four routes** out of the box: FRA ↔ ICN (default), ICN ↔ LAX, ICN ↔ JFK, ICN ↔ SFO
- **Side-by-side cards** showing latest KE and OZ prices with day-over-day delta + booking links
- **90-day line chart** (Chart.js) with toggleable airlines
- **Stats panel**: 90-day low/high/avg, 30-day avg, average cheaper airline,
  plus a plain-English booking recommendation
- **Recent snapshots table** (last 14 days) with cheaper-airline highlight
- **Mobile-responsive** layout with iOS PWA support (apple-touch-icon, manifest)
- **Brand-colored theme**: KE blue `#00256C`, OZ red `#C8102E`
- **EUR as default currency** (configurable in `fetch_prices.py`)
- **Friendly empty state** when no snapshots exist yet (until the first fetch runs)
- **No build step, no framework** — just HTML/CSS/vanilla JS

---

## File structure

```
flight-price-monitor/
├── index.html                  # Dashboard markup
├── css/styles.css              # All styling
├── js/app.js                   # Dashboard logic (vanilla JS + Chart.js)
├── data/prices.json            # Snapshot history (skeleton until first fetch)
├── manifest.json               # PWA manifest
├── icons/                      # Apple-touch-icon, PWA icons, favicons
├── scripts/
│   └── fetch_prices.py         # Duffel API fetcher (run by GitHub Actions)
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

The repo ships with a **skeleton `data/prices.json`** (4 routes defined, empty
price arrays). The dashboard renders a friendly empty state with booking
links until the first fetch populates real prices.

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

## Enabling live prices (Duffel API)

The default `data/prices.json` is a skeleton with no snapshots. To populate
real prices:

### 1. Get a Duffel API key

1. Sign up at <https://app.duffel.com/> (free, email only — no business
   verification required for the sandbox).
2. Go to **Dashboard → Access tokens → Create new token**.
3. Copy the token. It starts with `test_` (sandbox) or `live_` (production).

**Sandbox vs live:**
- `test_*` tokens: unlimited calls, real airlines, **shuffled/dummy prices**.
  Great for wiring up the pipeline — you'll see prices populate, just not the
  real numbers.
- `live_*` tokens: real prices, but require Duffel account verification (a
  short form + ID check). Use this once you've confirmed the pipeline works.

### 2. Add the token as a repo secret

In your GitHub repo: **Settings → Secrets and variables → Actions → New repository secret**

| Name | Value |
|------|-------|
| `DUFFEL_ACCESS_TOKEN` | your `test_...` or `live_...` token |

### 3. Trigger the first fetch

`.github/workflows/fetch-prices.yml` runs daily at 09:00 UTC. For the first
run, trigger it manually:

1. Go to **Actions → Fetch flight prices → Run workflow → Run workflow**.
2. Wait ~1 minute, then refresh the dashboard.

The workflow:
1. Calls `scripts/fetch_prices.py`, which queries Duffel for each route.
2. Picks the cheapest KE and OZ economy round-trip offer per route.
3. Appends today's snapshot to `data/prices.json` (preserving history).
4. Commits the file back to `main`, which triggers a Pages redeploy.

### 4. Switch from sandbox to live (optional)

Once your Duffel account is verified for live access, generate a `live_*`
token and replace the `DUFFEL_ACCESS_TOKEN` secret. No code changes needed.

---

## Customizing routes

Edit the `ROUTES` list in **two** places:

- `scripts/fetch_prices.py` — controls which routes the Duffel fetcher queries
- `data/prices.json` — controls which tabs appear in the dashboard
  (regenerate via `scripts/generate_skeleton_prices.py` after editing)

Common IATA codes you may want:
- **Asia hubs**: ICN (Seoul Incheon), NRT (Tokyo Narita), KIX (Osaka),
  BKK (Bangkok), SIN (Singapore), TPE (Taipei), HKG (Hong Kong)
- **Europe hubs**: FRA (Frankfurt), CDG (Paris), LHR (London Heathrow),
  AMS (Amsterdam), MUC (Munich), ZRH (Zurich), VIE (Vienna)
- **US hubs**: LAX, JFK, SFO, ORD (Chicago), SEA (Seattle), ATL (Atlanta),
  DFW (Dallas), IAD (Washington Dulles), EWR (Newark)

---

## How it works

```
GitHub Actions (daily cron)
        ↓
  Duffel Air Offer Requests API
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
- **Duffel sandbox returns shuffled prices** with `test_*` tokens. Use a
  `live_*` token once your account is verified to see real prices.
- **Codeshares may double-count.** Duffel sometimes returns the same physical
  flight marketed under both KE and a partner (e.g. Delta). The fetcher uses
  `owner.iata_code` (the ticketing carrier) as the source of truth.
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

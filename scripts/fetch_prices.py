"""
Fetch Korean Air (KE) and Asiana (OZ) flight prices from the Duffel API
and merge them into data/prices.json.

Duffel API docs: https://duffel.com/docs/api

Key differences from Amadeus:
  - Single API key (Bearer token) — no OAuth dance
  - Test key (test_*) returns real airlines with shuffled prices
  - Live key (live_*) returns real prices (requires account verification)
  - Round-trip search = two slices (outbound + return) in one request

Setup:
  1. Sign up at https://app.duffel.com/ (email only)
  2. Grab your API key from the dashboard
  3. Add it as repo secret: DUFFEL_ACCESS_TOKEN

If run without credentials (e.g. local dev), it exits gracefully.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import date, timedelta
from pathlib import Path

# Local helper module (same folder)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import notify  # noqa: E402

# ---------------------------------------------------------------- config
ROUTES = [
    {"id": "FRA-ICN", "origin": "FRA", "destination": "ICN"},
    {"id": "ICN-LAX", "origin": "ICN", "destination": "LAX"},
    {"id": "ICN-JFK", "origin": "ICN", "destination": "JFK"},
    {"id": "ICN-SFO", "origin": "ICN", "destination": "SFO"},
]

# Booking window: ~60 days out, 7-day trip
DAYS_OUT = 60
TRIP_DAYS = 7
ADULTS = 1
CABIN_CLASS = "economy"  # economy | premium_economy | business | first
CURRENCY = "EUR"

DUFFEL_API = "https://api.duffel.com/air/offer_requests?return_offers=true"
DUFFEL_VERSION = "v1"  # bump if Duffel releases a new API version

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "prices.json"


# ---------------------------------------------------------------- http
def http_post_json(url: str, body: dict, headers: dict) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", "ignore")[:500]
        raise RuntimeError(f"HTTP {e.code}: {err_body}") from e


# ---------------------------------------------------------------- duffel
def search_offers(token: str, origin: str, dest: str) -> list[dict]:
    """Create an offer request for a round-trip and return the offers list."""
    dep_date = (date.today() + timedelta(days=DAYS_OUT)).strftime("%Y-%m-%d")
    ret_date = (date.today() + timedelta(days=DAYS_OUT + TRIP_DAYS)).strftime("%Y-%m-%d")

    body = {
        "data": {
            "slices": [
                {"origin": origin, "destination": dest, "departure_date": dep_date},
                {"origin": dest, "destination": origin, "departure_date": ret_date},
            ],
            "passengers": [{"type": "adult"} for _ in range(ADULTS)],
            "cabin_class": CABIN_CLASS,
        }
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Duffel-Version": DUFFEL_VERSION,
        "Accept-Encoding": "gzip",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    resp = http_post_json(DUFFEL_API, body, headers)
    return resp.get("data", {}).get("offers", [])


def cheapest_per_carrier(offers: list[dict]) -> dict[str, float]:
    """Return {carrier_code: lowest_price} for KE / OZ offers.

    Duffel may return offers where KE/OZ is the marketing carrier but not the
    operating carrier (codeshare). We use owner.iata_code as the source of
    truth — that's the airline whose ticket you'd actually buy.
    """
    out: dict[str, float] = {}
    for offer in offers:
        owner = offer.get("owner", {})
        carrier = owner.get("iata_code", "")
        if carrier not in ("KE", "OZ"):
            continue
        try:
            price = float(offer.get("total_amount", "0"))
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        if carrier not in out or price < out[carrier]:
            out[carrier] = price
    return out


# ---------------------------------------------------------------- main
def main() -> int:
    token = os.environ.get("DUFFEL_ACCESS_TOKEN", "")
    if not token:
        print("DUFFEL_ACCESS_TOKEN not set. Skipping fetch.")
        print("Get a key at https://app.duffel.com/tokens")
        return 0

    if not DATA_PATH.exists():
        print(f"ERROR: {DATA_PATH} not found.")
        return 1

    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    today_iso = date.today().isoformat()
    route_by_id = {r["id"]: r for r in data["routes"]}

    # Keep currency in sync with this script's CURRENCY setting
    data["meta"]["currency"] = CURRENCY.upper()

    print(f"Fetching {len(ROUTES)} routes via Duffel API (version {DUFFEL_VERSION})...")
    print(f"  departure: T+{DAYS_OUT}d, return: T+{DAYS_OUT + TRIP_DAYS}d, cabin: {CABIN_CLASS}")

    # Track per-route prev/curr so we can detect drops for the alert email
    snapshots_for_alerts = []

    for r in ROUTES:
        rid = r["id"]
        if rid not in route_by_id:
            print(f"  - {rid}: route not in prices.json, skipping")
            continue
        try:
            print(f"  - Fetching {rid} ({r['origin']} -> {r['destination']})...")
            offers = search_offers(token, r["origin"], r["destination"])
            print(f"    got {len(offers)} offers")
            per_carrier = cheapest_per_carrier(offers)
            print(f"    cheapest per carrier: {per_carrier}")
        except Exception as e:
            print(f"    error: {e}")
            continue

        # Capture prev (before today's snapshot) for alert detection
        route_obj = route_by_id[rid]
        ke_prev = route_obj["ke"][-1] if route_obj["ke"] else None
        oz_prev = route_obj["oz"][-1] if route_obj["oz"] else None

        # append (or update) today's snapshot per carrier
        for carrier, key in [("KE", "ke"), ("OZ", "oz")]:
            if carrier not in per_carrier:
                continue
            arr = route_obj[key]
            if arr and arr[-1]["date"] == today_iso:
                arr[-1]["price"] = per_carrier[carrier]
            else:
                arr.append({"date": today_iso, "price": round(per_carrier[carrier], 2)})

        ke_curr = route_obj["ke"][-1] if route_obj["ke"] else None
        oz_curr = route_obj["oz"][-1] if route_obj["oz"] else None

        snapshots_for_alerts.append({
            "id": rid,
            "origin": r["origin"],
            "destination": r["destination"],
            "origin_city": route_obj["origin_city"],
            "destination_city": route_obj["destination_city"],
            "ke_prev": ke_prev,
            "ke_curr": ke_curr,
            "oz_prev": oz_prev,
            "oz_curr": oz_curr,
            "ke_series": route_obj["ke"],
            "oz_series": route_obj["oz"],
        })

    # update meta
    data["meta"]["generated_at"] = today_iso
    data["meta"]["note"] = "Live data via Duffel API, refreshed by GitHub Actions."

    DATA_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"Wrote {DATA_PATH}")

    # ---------------------------------------------------------------- alerts
    print("\nChecking for price drops...")
    drops = notify.detect_drops(snapshots_for_alerts)
    if drops:
        print(f"  Detected {len(drops)} drop(s) >= {notify.DROP_PCT_THRESHOLD:.0f}%:")
        for d in drops:
            tag = " (30-day low!)" if d["is_30d_low"] else ""
            print(f"    - {d['carrier_code']} {d['route_id']}: "
                  f"{d['prev_price']} -> {d['curr_price']} (-{d['drop_pct']:.1f}%){tag}")
        notify.send_alerts(drops, CURRENCY.upper())
    else:
        print(f"  No drops >= {notify.DROP_PCT_THRESHOLD:.0f}% today. No alert sent.")

    return 0


if __name__ == "__main__":
    sys.exit(main())

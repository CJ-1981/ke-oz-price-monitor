"""
Fetch Korean Air (KE) and Asiana (OZ) flight prices from the Amadeus
Self-Service API and merge them into data/prices.json.

Designed to run inside GitHub Actions. API credentials come from env vars
 AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET (configured as repo secrets).

The script:
  1. Reads the existing data/prices.json (preserves history)
  2. Calls Amadeus Flight Offers Search for each route, filtered to KE and OZ
  3. Picks the cheapest economy round-trip offer per airline per route
  4. Appends today's snapshot to the ke/oz arrays
  5. Writes back to data/prices.json

If run without credentials (e.g. local dev), it exits gracefully with a note.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import date, datetime, timedelta
from pathlib import Path

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
CURRENCY = "USD"
MAX_OFFERS = 50

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "prices.json"


# ---------------------------------------------------------------- http
def http_post(url: str, body: dict | str, headers: dict, form: bool = False) -> dict:
    data = body if isinstance(body, str) else json.dumps(body)
    if form:
        data = body  # already urlencoded string
        headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    else:
        headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data.encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get(url: str, headers: dict) -> dict:
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------- amadeus
def get_access_token(client_id: str, client_secret: str) -> str:
    # Use the test environment by default; switch to api.amadeus.com for production
    host = os.environ.get("AMADEUS_HOST", "test.api.amadeus.com")
    body = (
        f"grant_type=client_credentials"
        f"&client_id={client_id}"
        f"&client_secret={client_secret}"
    )
    resp = http_post(
        f"https://{host}/v1/security/oauth2/token",
        body,
        headers={},
        form=True,
    )
    return resp["access_token"]


def search_offers(token: str, origin: str, dest: str) -> dict:
    host = os.environ.get("AMADEUS_HOST", "test.api.amadeus.com")
    dep = (date.today() + timedelta(days=DAYS_OUT)).strftime("%Y-%m-%d")
    ret = (date.today() + timedelta(days=DAYS_OUT + TRIP_DAYS)).strftime("%Y-%m-%d")
    qs = (
        f"?originLocationCode={origin}"
        f"&destinationLocationCode={dest}"
        f"&departureDate={dep}"
        f"&returnDate={ret}"
        f"&adults={ADULTS}"
        f"&currencyCode={CURRENCY}"
        f"&max={MAX_OFFERS}"
        f"&nonStop=false"
    )
    url = f"https://{host}/v2/shopping/flight-offers{qs}"
    return http_get(url, headers={"Authorization": f"Bearer {token}"})


def cheapest_per_carrier(offers: list[dict]) -> dict[str, float]:
    """Return {carrier_code: lowest_price} for economy round-trip offers."""
    out: dict[str, float] = {}
    for o in offers:
        price = float(o.get("price", {}).get("total", "0"))
        if price <= 0:
            continue
        # walk all segments, collect carrier codes
        carriers = set()
        for seg in o.get("itineraries", []):
            for s in seg.get("segments", []):
                carriers.add(s.get("carrierCode", ""))
        # only keep KE / OZ
        for c in carriers & {"KE", "OZ"}:
            if c not in out or price < out[c]:
                out[c] = price
    return out


# ---------------------------------------------------------------- main
def main() -> int:
    client_id = os.environ.get("AMADEUS_CLIENT_ID", "")
    client_secret = os.environ.get("AMADEUS_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        print("AMADEUS_CLIENT_ID / AMADEUS_CLIENT_SECRET not set. Skipping fetch.")
        return 0

    if not DATA_PATH.exists():
        print(f"ERROR: {DATA_PATH} not found. Run generate_mock_prices.py first.")
        return 1

    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    today_iso = date.today().isoformat()

    print(f"Authenticating with Amadeus...")
    token = get_access_token(client_id, client_secret)

    route_by_id = {r["id"]: r for r in data["routes"]}

    for r in ROUTES:
        rid = r["id"]
        if rid not in route_by_id:
            print(f"  - {rid}: route not in prices.json, skipping")
            continue
        try:
            print(f"  - Fetching {rid}...")
            resp = search_offers(token, r["origin"], r["destination"])
            offers = resp.get("data", [])
            print(f"    got {len(offers)} offers")
            per_carrier = cheapest_per_carrier(offers)
            print(f"    cheapest per carrier: {per_carrier}")
        except urllib.error.HTTPError as e:
            print(f"    HTTP error {e.code}: {e.read().decode('utf-8', 'ignore')[:200]}")
            continue
        except Exception as e:
            print(f"    error: {e}")
            continue

        # append today's snapshot (only if not already present)
        for carrier, key in [("KE", "ke"), ("OZ", "oz")]:
            if carrier not in per_carrier:
                continue
            arr = route_by_id[rid][key]
            if arr and arr[-1]["date"] == today_iso:
                arr[-1]["price"] = per_carrier[carrier]
            else:
                arr.append({"date": today_iso, "price": round(per_carrier[carrier], 2)})

    # update meta
    data["meta"]["generated_at"] = today_iso
    data["meta"]["note"] = "Live data via Amadeus API, refreshed by GitHub Actions."

    DATA_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"Wrote {DATA_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
Email alert notifier for the KE/OZ price monitor.

Sends an HTML email via Gmail SMTP when a price drop is detected.

Trigger conditions (any of):
  - Day-over-day drop >= ALERT_DROP_PCT (default 5%)
  - New 30-day low

Credentials come from environment variables (set as GitHub Actions secrets):
  GMAIL_USER           e.g. you@gmail.com  (also used as sender)
  GMAIL_APP_PASSWORD   16-char app password (NOT your regular Gmail password)
  ALERT_RECIPIENT      (optional) defaults to GMAIL_USER

Configuration (also env vars, with sensible defaults):
  ALERT_DROP_PCT       default 5.0  -- alert if price dropped >=X% vs yesterday
  ALERT_MIN_INTERVAL_H default 24   -- minimum hours between alerts (anti-spam)

The last-sent timestamp is persisted to data/last_alert.json so we don't
spam the inbox on every daily run if the price stays low.
"""
from __future__ import annotations

import json
import os
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# ---------------------------------------------------------------- config
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LAST_ALERT_PATH = DATA_DIR / "last_alert.json"

DROP_PCT_THRESHOLD = float(os.environ.get("ALERT_DROP_PCT", "5"))
MIN_INTERVAL_HOURS = float(os.environ.get("ALERT_MIN_INTERVAL_H", "24"))

GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587


# ---------------------------------------------------------------- trigger logic
def detect_drops(route_snapshots: list[dict]) -> list[dict]:
    """Identify routes that should trigger an alert.

    `route_snapshots` is a list of dicts with:
        id, origin, destination, origin_city, destination_city,
        ke_prev, ke_curr, oz_prev, oz_curr, ke_series, oz_series
    """
    drops = []
    for r in route_snapshots:
        ke_drop = _drop_info("KE", "Korean Air", r.get("ke_prev"),
                             r.get("ke_curr"), r.get("ke_series"))
        oz_drop = _drop_info("OZ", "Asiana", r.get("oz_prev"),
                             r.get("oz_curr"), r.get("oz_series"))
        if ke_drop:
            drops.append({**ke_drop, "route_id": r["id"],
                          "route_label": f"{r['origin_city']} ↔ {r['destination_city']}"})
        if oz_drop:
            drops.append({**oz_drop, "route_id": r["id"],
                          "route_label": f"{r['origin_city']} ↔ {r['destination_city']}"})
    return drops


def _drop_info(code: str, name: str, prev, curr, series) -> dict | None:
    """Return drop info if curr is a notable drop, else None."""
    if not curr or not prev:
        return None
    pct = ((prev["price"] - curr["price"]) / prev["price"]) * 100
    if pct < DROP_PCT_THRESHOLD:
        return None
    # also check 30-day low
    last30 = [s["price"] for s in (series or [])[-30:]]
    is_30d_low = bool(last30) and curr["price"] <= min(last30)
    return {
        "carrier_code": code,
        "carrier_name": name,
        "prev_price": prev["price"],
        "curr_price": curr["price"],
        "drop_pct": pct,
        "is_30d_low": is_30d_low,
        "date": curr["date"],
    }


# ---------------------------------------------------------------- rate limit
def _should_send() -> bool:
    """True if enough time has passed since the last alert."""
    if not LAST_ALERT_PATH.exists():
        return True
    try:
        data = json.loads(LAST_ALERT_PATH.read_text(encoding="utf-8"))
        last_sent = datetime.fromisoformat(data["sent_at"])
        elapsed_h = (datetime.now(timezone.utc) - last_sent).total_seconds() / 3600
        return elapsed_h >= MIN_INTERVAL_HOURS
    except Exception:
        return True


def _mark_sent() -> None:
    LAST_ALERT_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_ALERT_PATH.write_text(json.dumps({
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2), encoding="utf-8")


# ---------------------------------------------------------------- email content
def _build_email(drops: list[dict], currency: str) -> tuple[str, str]:
    """Return (subject, html_body)."""
    sym = {"USD": "$", "EUR": "€", "GBP": "£", "KRW": "₩", "JPY": "¥"}.get(currency, currency + " ")
    total = len(drops)
    top = drops[0]
    subject = (
        f"✈️ Price drop alert: {top['carrier_name']} {top['route_label']} "
        f"{sym}{int(top['curr_price'])} (-{top['drop_pct']:.1f}%)"
    )
    if total > 1:
        subject += f"  +{total - 1} more"

    rows_html = []
    for d in drops:
        badge_30d = ' <span style="color:#1b873f;font-weight:600;font-size:11px;background:#e6f4ea;padding:2px 6px;border-radius:999px;">30-DAY LOW</span>' if d["is_30d_low"] else ""
        rows_html.append(f"""
          <tr>
            <td style="padding:8px 12px;border-bottom:1px solid #eef1f6;">
              <strong>{d['carrier_name']} ({d['carrier_code']})</strong>{badge_30d}<br>
              <span style="color:#5a6678;font-size:12px;">{d['route_label']}</span>
            </td>
            <td style="padding:8px 12px;border-bottom:1px solid #eef1f6;text-align:right;color:#8793a4;text-decoration:line-through;">
              {sym}{int(d['prev_price'])}
            </td>
            <td style="padding:8px 12px;border-bottom:1px solid #eef1f6;text-align:right;font-weight:700;color:#1b873f;">
              {sym}{int(d['curr_price'])}
            </td>
            <td style="padding:8px 12px;border-bottom:1px solid #eef1f6;text-align:right;color:#1b873f;font-weight:700;">
              -{d['drop_pct']:.1f}%
            </td>
          </tr>""")

    html = f"""\
<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#f6f8fb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#0f1b2d;">
  <div style="max-width:600px;margin:0 auto;padding:24px 16px;">
    <div style="background:linear-gradient(135deg,#0a1f44 0%,#00256C 60%,#1d3a7a 100%);color:#fff;padding:18px 22px;border-radius:12px 12px 0 0;">
      <div style="font-size:22px;line-height:1;">✈️ Price Drop Alert</div>
      <div style="font-size:13px;opacity:0.8;margin-top:6px;">KE / OZ Flight Price Monitor · {datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M UTC')}</div>
    </div>
    <div style="background:#fff;border:1px solid #e3e8ef;border-top:none;border-radius:0 0 12px 12px;padding:18px 22px;">
      <p style="margin:0 0 14px;font-size:15px;line-height:1.5;">
        {total} price drop{('s' if total != 1 else '')} detected in today's snapshot
        (≥{DROP_PCT_THRESHOLD:.0f}% day-over-day decrease):
      </p>
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <thead>
          <tr style="background:#fafbfd;">
            <th style="padding:8px 12px;text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:0.04em;color:#5a6678;border-bottom:1px solid #e3e8ef;">Airline / Route</th>
            <th style="padding:8px 12px;text-align:right;font-size:11px;text-transform:uppercase;letter-spacing:0.04em;color:#5a6678;border-bottom:1px solid #e3e8ef;">Yesterday</th>
            <th style="padding:8px 12px;text-align:right;font-size:11px;text-transform:uppercase;letter-spacing:0.04em;color:#5a6678;border-bottom:1px solid #e3e8ef;">Today</th>
            <th style="padding:8px 12px;text-align:right;font-size:11px;text-transform:uppercase;letter-spacing:0.04em;color:#5a6678;border-bottom:1px solid #e3e8ef;">Δ</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows_html)}
        </tbody>
      </table>
      <p style="margin:18px 0 4px;font-size:13px;color:#5a6678;">
        <a href="https://cj-1981.github.io/ke-oz-price-monitor/" style="color:#00256C;font-weight:600;">Open dashboard ↗</a>
        &nbsp;·&nbsp;
        <a href="https://www.koreanair.com/global/en_us/booking/booking-search" style="color:#00256C;">Book Korean Air ↗</a>
        &nbsp;·&nbsp;
        <a href="https://www.flyasiana.com/C/US/EN/index?fp=booking" style="color:#C8102E;">Book Asiana ↗</a>
      </p>
      <p style="margin:14px 0 0;font-size:11px;color:#8793a4;line-height:1.5;">
        Snapshot prices may differ from live inventory at booking time. Always verify on the airline website.
        To stop these alerts, remove the <code>GMAIL_APP_PASSWORD</code> secret or set <code>ALERT_DROP_PCT=100</code>.
      </p>
    </div>
  </div>
</body></html>"""
    return subject, html


# ---------------------------------------------------------------- SMTP send
def send_alerts(drops: list[dict], currency: str) -> bool:
    """Send an alert email. Returns True if sent, False if skipped."""
    if not drops:
        return False

    gmail_user = os.environ.get("GMAIL_USER", "")
    gmail_pw = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not gmail_user or not gmail_pw:
        print("  GMAIL_USER / GMAIL_APP_PASSWORD not set — skipping email alert.")
        return False

    if not _should_send():
        print(f"  Skipping alert: less than {MIN_INTERVAL_HOURS:.0f}h since last send (anti-spam).")
        return False

    recipient = os.environ.get("ALERT_RECIPIENT") or gmail_user
    subject, html = _build_email(drops, currency)

    msg = MIMEMultipart("alternative")
    msg["From"] = f"KE/OZ Monitor <{gmail_user}>"
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        print(f"  Sending alert to {recipient}...")
        with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT, timeout=30) as s:
            s.ehlo()
            s.starttls()
            s.ehlo()
            s.login(gmail_user, gmail_pw)
            s.sendmail(gmail_user, [recipient], msg.as_string())
        _mark_sent()
        print(f"  ✓ Sent: {subject}")
        return True
    except Exception as e:
        print(f"  ✗ SMTP error: {e}", file=sys.stderr)
        return False

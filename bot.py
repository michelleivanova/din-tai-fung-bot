#!/usr/bin/env python3
"""
Din Tai Fung Fashion Square (Scottsdale) reservation bot.
Runs at midnight AZ time (07:00 UTC) on Sundays via GitHub Actions.
Targets: party of 5, 5–7 PM, Saturday or Sunday.

Yelp reservation page structure (discovered via Chrome inspection):
  - URL params: ?date=YYYY-MM-DD&time=HHMM&covers=N
  - Availability API: GET /reservations/{biz}/search_availability
  - Time slots: <button type="submit"> with time text like "5:00 pm"
  - Clicking a slot navigates to /reservations/{biz}/checkout/{date}/{time}/{covers}
  - Checkout form: First Name, Last Name, Mobile Number, Email, Requests
  - Confirm button: <button type="submit"> with text "Confirm"
"""

import os
import sys
import json
import logging
import random
import time
from datetime import datetime, timedelta

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

BUSINESS_ALIAS = "din-tai-fung-scottsdale-5"
RESERVATION_URL = f"https://www.yelp.com/reservations/{BUSINESS_ALIAS}"

# Reservation preferences (overridable via env vars)
PARTY_SIZE     = int(os.getenv("PARTY_SIZE", "5"))
EARLIEST_HOUR  = int(os.getenv("EARLIEST_HOUR", "17"))
LATEST_HOUR    = int(os.getenv("LATEST_HOUR", "19"))
_days_env      = os.getenv("TARGET_DAYS", "Saturday,Sunday")
TARGET_DAYS    = set(d.strip() for d in _days_env.split(","))

# Contact info (stored as GitHub secrets)
CONTACT_NAME   = os.getenv("CONTACT_NAME", "")
CONTACT_EMAIL  = os.getenv("CONTACT_EMAIL", "")
CONTACT_PHONE  = os.getenv("CONTACT_PHONE", "")

# Yelp session (JSON string from YELP_SESSION secret)
YELP_SESSION   = os.getenv("YELP_SESSION", "")
SESSION_FILE   = "yelp_session.json"

SCREENSHOT_DIR = "screenshots"

# Preferred times to search, in order of preference (24h format for URL)
_times_env = os.getenv("PREFERRED_TIMES", "1700,1730,1800,1830,1900")
PREFERRED_TIMES = [t.strip() for t in _times_env.split(",")]


def run_bot():
    if YELP_SESSION:
        with open(SESSION_FILE, "w") as f:
            f.write(YELP_SESSION)
        log.info("Loaded Yelp session from YELP_SESSION secret.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        ctx_kwargs = dict(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        if os.path.exists(SESSION_FILE):
            ctx_kwargs["storage_state"] = SESSION_FILE

        context = browser.new_context(**ctx_kwargs)
        page = context.new_page()

        try:
            booked = False
            for target_date in upcoming_target_dates():
                day_name = target_date.strftime("%A")
                date_str = target_date.strftime("%Y-%m-%d")
                log.info(f"Trying {day_name} {date_str}...")

                # Load once per date — Yelp shows nearby slots automatically.
                # Use middle of preferred window so nearby slots span the range.
                mid_time = PREFERRED_TIMES[len(PREFERRED_TIMES) // 2]
                url = (
                    f"{RESERVATION_URL}"
                    f"?date={date_str}&time={mid_time}&covers={PARTY_SIZE}"
                )
                log.info(f"Loading {url}")
                human_delay()
                page.goto(url, wait_until="networkidle", timeout=30_000)
                page.wait_for_timeout(random.randint(2000, 4000))
                screenshot(page, f"01_{date_str}")

                # Check if we got blocked
                if "you have been blocked" in (page.content() or "").lower():
                    log.error("Yelp blocked us! Waiting before retry...")
                    page.wait_for_timeout(random.randint(10_000, 20_000))
                    page.goto(url, wait_until="networkidle", timeout=30_000)
                    page.wait_for_timeout(random.randint(3000, 5000))
                    screenshot(page, f"01_{date_str}_retry")

                slot = find_preferred_slot(page)
                if slot is None:
                    log.info(f"No preferred slots on {date_str}.")
                    continue

                log.info(f"Clicking slot: {slot.inner_text()}")
                human_delay()
                slot.click()
                page.wait_for_timeout(random.randint(3000, 5000))
                screenshot(page, f"02_checkout_{date_str}")

                if "/checkout/" not in page.url:
                    log.warning("Did not navigate to checkout page, trying next date.")
                    continue

                fill_checkout_form(page)
                screenshot(page, f"03_filled_{date_str}")

                click_confirm(page)
                page.wait_for_timeout(5_000)
                screenshot(page, "04_confirmed")

                log.info(f"Reservation booked for {day_name} {date_str}!")
                booked = True
                break

            if not booked:
                raise RuntimeError(
                    f"No preferred slots found on {', '.join(TARGET_DAYS)}."
                )

        except Exception as exc:
            log.error(f"Bot failed: {exc}")
            screenshot(page, "fatal_error")
            raise
        finally:
            context.close()
            browser.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def upcoming_target_dates():
    """Return the next Saturday and Sunday as datetime.date objects."""
    today = datetime.utcnow().date()
    dates = []
    for offset in range(1, 8):
        d = today + timedelta(days=offset)
        if d.strftime("%A") in TARGET_DAYS:
            dates.append(d)
        if len(dates) == 2:
            break
    dates.sort(key=lambda d: 0 if d.strftime("%A") == "Saturday" else 1)
    return dates


def is_preferred_time(text: str) -> bool:
    """Return True if a time string (e.g. '5:30 pm') falls in 5–7 PM window."""
    text = text.strip().upper()
    for fmt in ("%I:%M %p", "%I %p"):
        try:
            t = datetime.strptime(text, fmt)
            return EARLIEST_HOUR <= t.hour < LATEST_HOUR
        except ValueError:
            continue
    return False


def human_delay():
    """Sleep for a random human-like duration to avoid bot detection."""
    delay = random.uniform(1.5, 4.0)
    log.info(f"Waiting {delay:.1f}s...")
    time.sleep(delay)


def screenshot(page, name):
    path = f"{SCREENSHOT_DIR}/{name}.png"
    try:
        page.screenshot(path=path)
        log.info(f"Screenshot: {path}")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def find_preferred_slot(page):
    """Return the first available time button in the 5–7 PM window, or None."""
    log.info("Looking for 5–7 PM slots...")

    # Check for "No Availability" message first
    no_avail = page.query_selector('text="No Availability"')
    if no_avail:
        log.info("Page shows 'No Availability'.")
        return None

    # Yelp renders time slots as <button type="submit"> with text like "5:00 pm"
    # They appear under a "What's available" section
    buttons = page.query_selector_all('button[type="submit"]')
    for btn in buttons:
        text = (btn.inner_text() or "").strip()
        if is_preferred_time(text) and btn.is_enabled():
            log.info(f"Found preferred slot: '{text}'")
            return btn

    # Fallback: scan all buttons for time-like text
    all_buttons = page.query_selector_all("button:not([disabled])")
    for btn in all_buttons:
        text = (btn.inner_text() or "").strip()
        if ":" in text and ("am" in text.lower() or "pm" in text.lower()):
            if is_preferred_time(text):
                log.info(f"Found preferred slot (fallback): '{text}'")
                return btn

    log.info("No preferred slots found.")
    return None


def fill_checkout_form(page):
    """Fill the checkout form with contact details."""
    log.info("Filling checkout form...")
    page.wait_for_timeout(2_000)

    # Split name into first/last (checkout has separate fields)
    parts = CONTACT_NAME.split(None, 1) if CONTACT_NAME else ["", ""]
    first_name = parts[0] if len(parts) > 0 else ""
    last_name = parts[1] if len(parts) > 1 else ""

    # First Name field
    _clear_and_fill(page, 'input[placeholder=" "]:near(:text("First Name"))', first_name)
    # Last Name field
    _clear_and_fill(page, 'input[placeholder=" "]:near(:text("Last Name"))', last_name)
    # Email field
    _clear_and_fill(page, 'input[type="email"]', CONTACT_EMAIL)
    # Phone field
    _clear_and_fill(page, 'input[type="tel"]', CONTACT_PHONE)

    log.info("Checkout form filled.")


def _clear_and_fill(page, selector, value):
    """Clear an input field and fill it with a value."""
    if not value:
        return
    try:
        el = page.query_selector(selector)
        if el:
            el.click()
            page.keyboard.press("Meta+a")
            el.fill(value)
            log.info(f"Filled '{selector}' with value.")
            return
    except Exception as exc:
        log.warning(f"Primary selector failed for '{selector}': {exc}")

    # Fallback: try by label text
    label_map = {
        "email": CONTACT_EMAIL,
        "tel": CONTACT_PHONE,
    }
    for input_type, val in label_map.items():
        if value == val:
            try:
                el = page.query_selector(f'input[type="{input_type}"]')
                if el:
                    el.fill(value)
                    return
            except Exception:
                pass


def click_confirm(page):
    """Click the Confirm reservation button."""
    log.info("Clicking Confirm...")

    selectors = [
        'button:has-text("Confirm")',
        'button[type="submit"]:has-text("Confirm")',
        'button:has-text("Complete Reservation")',
        'button:has-text("Reserve")',
    ]
    for sel in selectors:
        try:
            page.click(sel, timeout=5_000)
            log.info(f"Confirmed via: {sel}")
            page.wait_for_load_state("networkidle", timeout=15_000)
            return
        except Exception:
            continue

    raise RuntimeError("Could not find a Confirm button on checkout page.")


if __name__ == "__main__":
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    run_bot()

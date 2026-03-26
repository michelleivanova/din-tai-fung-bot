#!/usr/bin/env python3
"""
Din Tai Fung Fashion Square (Scottsdale) reservation bot.
Runs at midnight AZ time (07:00 UTC) on Sundays via GitHub Actions.
Targets: party of 5, 5–7 PM, Saturday or Sunday.
"""

import os
import sys
import logging
from datetime import datetime, timedelta

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

RESERVATION_URL = "https://www.yelp.com/reservations/din-tai-fung-scottsdale-5"

# Reservation preferences
PARTY_SIZE     = int(os.getenv("PARTY_SIZE", "5"))
EARLIEST_HOUR  = 17   # 5:00 PM (24h)
LATEST_HOUR    = 19   # 7:00 PM (slots before 7 PM, i.e. 5:00–6:45)
TARGET_DAYS    = {"Saturday", "Sunday"}   # Day names to accept

# Contact info (stored as GitHub secrets)
CONTACT_NAME   = os.getenv("CONTACT_NAME", "")
CONTACT_EMAIL  = os.getenv("CONTACT_EMAIL", "")
CONTACT_PHONE  = os.getenv("CONTACT_PHONE", "")
YELP_EMAIL     = os.getenv("YELP_EMAIL", "")
YELP_PASSWORD  = os.getenv("YELP_PASSWORD", "")

SCREENSHOT_DIR = "screenshots"


def run_bot():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        try:
            if YELP_EMAIL and YELP_PASSWORD:
                yelp_login(page)

            log.info("Navigating to reservation page...")
            page.goto(RESERVATION_URL, wait_until="networkidle", timeout=30_000)
            screenshot(page, "01_loaded")

            # Try Saturday first, then Sunday
            booked = False
            for target_date in upcoming_target_dates():
                day_name = target_date.strftime("%A")
                date_str = target_date.strftime("%Y-%m-%d")
                log.info(f"Trying {day_name} {date_str}...")

                try:
                    set_party_size(page)
                    select_date(page, target_date)
                    screenshot(page, f"02_date_{date_str}")

                    slot = find_preferred_slot(page)
                    if slot is None:
                        log.info(f"No 5–7 PM slots on {date_str}, trying next day.")
                        continue

                    slot.click()
                    page.wait_for_timeout(1_500)
                    screenshot(page, f"03_slot_selected_{date_str}")

                    confirm_reservation(page)
                    screenshot(page, "04_confirmed")
                    log.info(f"Reservation booked for {day_name} {date_str}!")
                    booked = True
                    break

                except Exception as exc:
                    log.warning(f"Failed for {date_str}: {exc}")
                    screenshot(page, f"error_{date_str}")
                    # Reload and try next date
                    page.goto(RESERVATION_URL, wait_until="networkidle", timeout=30_000)

            if not booked:
                raise RuntimeError("No 5–7 PM slots found on Saturday or Sunday this week.")

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
    # Put Saturday first
    dates.sort(key=lambda d: 0 if d.strftime("%A") == "Saturday" else 1)
    return dates


def is_preferred_time(text: str) -> bool:
    """Return True if a time string (e.g. '5:30 PM') falls in 5–7 PM window."""
    text = text.strip().upper()
    for fmt in ("%I:%M %p", "%I %p"):
        try:
            t = datetime.strptime(text, fmt)
            return EARLIEST_HOUR <= t.hour < LATEST_HOUR
        except ValueError:
            continue
    return False


def screenshot(page, name):
    path = f"{SCREENSHOT_DIR}/{name}.png"
    page.screenshot(path=path)
    log.info(f"Screenshot: {path}")


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def yelp_login(page):
    log.info("Logging in to Yelp...")
    page.goto("https://www.yelp.com/login", wait_until="networkidle", timeout=30_000)
    page.fill('input[name="email"]', YELP_EMAIL)
    page.fill('input[name="password"]', YELP_PASSWORD)
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle", timeout=15_000)
    log.info("Yelp login done.")


def set_party_size(page):
    log.info(f"Setting party size to {PARTY_SIZE}...")
    candidates = [
        f'button[aria-label="{PARTY_SIZE} people"]',
        f'button[aria-label="{PARTY_SIZE} guest"]',
        f'[data-testid="covers-{PARTY_SIZE}"]',
        f'button[value="{PARTY_SIZE}"]',
    ]
    for sel in candidates:
        try:
            page.click(sel, timeout=4_000)
            log.info(f"Party size set via: {sel}")
            return
        except PlaywrightTimeout:
            continue

    for sel in ['select[name="covers"]', 'select[id*="covers"]', 'select[id*="party"]']:
        try:
            page.select_option(sel, str(PARTY_SIZE), timeout=4_000)
            log.info(f"Party size set via select: {sel}")
            return
        except PlaywrightTimeout:
            continue

    try:
        page.get_by_role("button", name=str(PARTY_SIZE)).first.click(timeout=4_000)
        log.info("Party size set via role button.")
        return
    except Exception:
        pass

    log.warning("Could not explicitly set party size — using page default.")


def select_date(page, target_date):
    """Attempt to click the target date in the date picker."""
    log.info(f"Selecting date {target_date}...")
    # Try aria-label like "Sunday, April 13, 2025"
    label = target_date.strftime("%A, %B %-d, %Y")
    label_alt = target_date.strftime("%B %-d, %Y")

    for sel in [
        f'button[aria-label="{label}"]',
        f'td[aria-label="{label}"]',
        f'[data-date="{target_date.isoformat()}"]',
        f'button[data-testid="{target_date.isoformat()}"]',
    ]:
        try:
            page.click(sel, timeout=4_000)
            log.info(f"Date selected via: {sel}")
            page.wait_for_timeout(1_500)
            return
        except PlaywrightTimeout:
            continue

    # Fallback: find a cell whose text is the day number and matches the month
    day_num = str(target_date.day)
    try:
        cells = page.query_selector_all('td[role="gridcell"] button, td.rdp-day button, [class*="day"]:not([disabled])')
        for cell in cells:
            if (cell.inner_text() or "").strip() == day_num:
                cell.click()
                page.wait_for_timeout(1_500)
                log.info(f"Date selected via day number cell: {day_num}")
                return
    except Exception:
        pass

    log.warning(f"Could not select date {target_date} — widget may auto-select next available.")


def find_preferred_slot(page):
    """Return the first available time button in the 5–7 PM window, or None."""
    log.info("Looking for 5–7 PM slots...")
    page.wait_for_timeout(3_000)

    slot_selectors = [
        'button[data-testid="reservation-time"]',
        'button[data-testid*="time-slot"]',
        '[class*="TimeSlot"]:not([disabled]):not([class*="unavailable"])',
        '[class*="time-slot"]:not(.unavailable):not([disabled])',
        'button[class*="time"]:not([disabled])',
        '.reservation-time-slot:not(.disabled)',
    ]

    for sel in slot_selectors:
        try:
            page.wait_for_selector(sel, timeout=5_000)
            slots = page.query_selector_all(sel)
            if not slots:
                continue
            log.info(f"Found {len(slots)} total slot(s) via '{sel}'.")
            for slot in slots:
                text = (slot.inner_text() or "").strip()
                if is_preferred_time(text):
                    log.info(f"Preferred slot: '{text}'")
                    return slot
            log.info("No slots in 5–7 PM window via this selector.")
            return None  # Found slots but none in window
        except PlaywrightTimeout:
            continue

    # Last-resort: scan all enabled buttons for time-like text
    buttons = page.query_selector_all("button:not([disabled])")
    preferred = []
    for btn in buttons:
        text = (btn.inner_text() or "").strip()
        if ":" in text and ("AM" in text.upper() or "PM" in text.upper()):
            if is_preferred_time(text):
                preferred.append(btn)

    if preferred:
        log.info(f"Found {len(preferred)} preferred slot(s) via fallback scan.")
        return preferred[0]

    log.info("No preferred slots found.")
    return None


def confirm_reservation(page):
    log.info("Filling contact details and confirming...")
    page.wait_for_timeout(2_000)

    _fill_field(page, ['input[name="name"]', 'input[placeholder*="name" i]', 'input[id*="name" i]'], CONTACT_NAME)
    _fill_field(page, ['input[type="email"]', 'input[name="email"]', 'input[placeholder*="email" i]'], CONTACT_EMAIL)
    _fill_field(page, ['input[type="tel"]', 'input[name="phone"]', 'input[placeholder*="phone" i]'], CONTACT_PHONE)

    confirm_selectors = [
        'button[type="submit"]',
        'button[data-testid="confirm-reservation"]',
        'button:text-is("Confirm")',
        'button:text-is("Reserve")',
        'button:text-is("Book")',
        'button:has-text("Confirm")',
        'button:has-text("Reserve")',
    ]
    for sel in confirm_selectors:
        try:
            page.click(sel, timeout=5_000)
            log.info(f"Confirmed via: {sel}")
            page.wait_for_load_state("networkidle", timeout=15_000)
            return
        except Exception:
            continue

    raise RuntimeError("Could not find a confirm/submit button.")


def _fill_field(page, selectors, value):
    if not value:
        return
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el:
                el.fill(value)
                return
        except Exception:
            continue


if __name__ == "__main__":
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    run_bot()

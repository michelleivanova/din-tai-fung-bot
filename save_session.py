#!/usr/bin/env python3
"""
One-time setup: opens a real browser so you can log in to Yelp via Google.
Saves the authenticated session to yelp_session.json, which you then upload
as a GitHub secret so the bot can reuse it without ever needing your password.

Usage:
  pip install playwright
  playwright install chromium
  python save_session.py
  # log in via Google in the browser that opens, then close it
  # upload the session:
  gh secret set YELP_SESSION --body "$(cat yelp_session.json)" -R michelleivanova/din-tai-fung-bot
"""

from playwright.sync_api import sync_playwright

YELP_URL = "https://www.yelp.com/login"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)   # visible browser
        context = browser.new_context()
        page = context.new_page()

        print("Opening Yelp login page...")
        page.goto(YELP_URL)

        print("\n>>> Log in with Google in the browser window.")
        print(">>> Once you're fully logged in and can see your Yelp account, come back here.")
        input(">>> Press ENTER when done to save the session...\n")

        context.storage_state(path="yelp_session.json")
        print("Session saved to yelp_session.json")
        print("\nNow run:")
        print('  gh secret set YELP_SESSION --body "$(cat yelp_session.json)" -R michelleivanova/din-tai-fung-bot')

        browser.close()

if __name__ == "__main__":
    main()

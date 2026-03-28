# Din Tai Fung Reservation Bot

Automated reservation bot for **Din Tai Fung — Fashion Square (Scottsdale)** via Yelp. Runs every Sunday at midnight AZ time through GitHub Actions to grab weekend dinner slots the moment they open.

## How It Works

1. **GitHub Actions** triggers the workflow at **midnight MST every Sunday** (07:00 UTC).
2. A headless Chromium browser (Playwright) opens the [Yelp reservation page](https://www.yelp.com/reservations/din-tai-fung-scottsdale-5).
3. The bot selects a party size of **5**, then looks for available **5:00–7:00 PM** slots on the upcoming **Saturday** and **Sunday**.
4. When a slot is found, it fills in contact details and confirms the reservation.
5. Screenshots are saved as artifacts on every run for debugging.

## Setup

### Prerequisites

- Python 3.12+
- A GitHub account with this repo pushed
- A Yelp account (Google SSO supported)

### 1. Clone & install locally

```bash
git clone https://github.com/michelleivanova/din-tai-fung-bot.git
cd din-tai-fung-bot
pip3 install -r requirements.txt
python3 -m playwright install chromium
```

### 2. Save your Yelp session (one-time)

Since the bot uses Google Sign-In for Yelp, you need to log in once locally and save the session cookies:

```bash
python3 save_session.py
```

This opens a real browser window. Log in to Yelp via Google, then **close the browser window**. The script saves your session to `yelp_session.json`.

### 3. Upload secrets to GitHub

```bash
gh secret set YELP_SESSION --body "$(cat yelp_session.json)" -R michelleivanova/din-tai-fung-bot
gh secret set CONTACT_NAME  --body "Your Name"                -R michelleivanova/din-tai-fung-bot
gh secret set CONTACT_EMAIL --body "you@email.com"            -R michelleivanova/din-tai-fung-bot
gh secret set CONTACT_PHONE --body "1234567890"               -R michelleivanova/din-tai-fung-bot
gh variable set PARTY_SIZE  --body "5"                        -R michelleivanova/din-tai-fung-bot
```

### 4. Test it

Trigger a manual run from the **Actions** tab or via CLI:

```bash
gh workflow run reserve.yml -R michelleivanova/din-tai-fung-bot
```

Check the run's **screenshots** artifact to verify it worked.

## Configuration

| Variable | Type | Default | Description |
|---|---|---|---|
| `PARTY_SIZE` | GitHub Variable | `5` | Number of guests |
| `CONTACT_NAME` | Secret | — | Name for the reservation |
| `CONTACT_EMAIL` | Secret | — | Confirmation email address |
| `CONTACT_PHONE` | Secret | — | Phone number |
| `YELP_SESSION` | Secret | — | Yelp session cookies (from `save_session.py`) |

Time preferences are set in `bot.py`:
- **`EARLIEST_HOUR`** — 17 (5:00 PM)
- **`LATEST_HOUR`** — 19 (7:00 PM)
- **`TARGET_DAYS`** — Saturday, Sunday

## File Structure

```
├── bot.py                  # Main reservation bot
├── save_session.py         # One-time Yelp login session saver
├── requirements.txt        # Python dependencies
├── .github/workflows/
│   └── reserve.yml         # GitHub Actions workflow (Sunday midnight AZ)
├── .env.example            # Template for local testing
└── .gitignore
```

## Troubleshooting

- **Session expired?** Yelp cookies last a few weeks. Re-run `save_session.py` and re-upload the `YELP_SESSION` secret.
- **No slots found?** Check the screenshots artifact — the page layout may have changed, or slots may genuinely be sold out.
- **Wrong time zone?** The cron runs at 07:00 UTC = midnight MST (Arizona doesn't observe DST).

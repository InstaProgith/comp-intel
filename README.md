# Real Estate Development Intelligence Tool (BLDGBIT)

Flask web app that analyzes LA single-family home development projects by scraping Redfin listings, LADBS permits, and CSLB contractor licenses.

## Overview

Generates development analysis reports for residential properties:
- Property snapshot (address, beds/baths/SF, lot size, year built, sale status)
- Transaction analysis (purchase/exit price, hold period, spread, ROI)
- ZIMAS parcel profile (parcel identity, zoning, planning context, environmental and hazard context)
- Development timeline (construction stages from permits to completion)
- Construction summary (existing SF, added SF, scope level)
- Cost model (estimated construction costs using industry rates)
- Permit overview (building, demolition, MEP permits)
- LADBS records/documents lookup with auditable summary links and public PDF viewer links when available
- Team info (general contractor, architect, engineer with license data)

## Quick Start

**Prerequisites:** Python 3.11+, Git, and optional Chrome + ChromeDriver for LADBS browser fallback

**Run locally:**
```bash
git clone https://github.com/InstaProgith/comp-intel.git
cd comp-intel
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.ui_server
# Open http://localhost:5000
# Password: APP_ACCESS_PASSWORD, local access_password.txt, or CHANGE_ME_DEV in local debug-style runs
```

**Local config:**
- Set `FLASK_SECRET_KEY` and `APP_ACCESS_PASSWORD` in your environment or `.env`
- Optional local-only fallback: create an untracked `access_password.txt`
- Safe examples live in `.env.example` and `access_password.example.txt`

## Environment Variables

**Production (required):**
- `FLASK_SECRET_KEY` - Session encryption key (generate random string)
- `APP_ACCESS_PASSWORD` - Login password (preferred over local file)
- `APP_ENV=production` - Enables fail-closed production config behavior

**Optional:**
- `ONE_MIN_AI_API_KEY` - For AI-generated summaries
- `FLASK_DEBUG` - Set to "1" for debug mode (never in production)
- `LADBS_CHROME_BINARY` - Explicit Chrome binary path if Chrome is not on PATH
- `LADBS_CHROMEDRIVER_PATH` - Explicit ChromeDriver path if needed
- `SE_CACHE_PATH` - Writable Selenium Manager cache directory
- `LADBS_SELENIUM_PROFILE_DIR` - Writable browser profile root for LADBS sessions
- `LADBS_BROWSER_ENV_DIR` - Writable browser env directory used for LOCALAPPDATA/TEMP overrides
- `LADBS_DRIVER_START_RETRIES` - Chrome startup retry count
- `LADBS_PAGE_LOAD_TIMEOUT` - LADBS page-load timeout in seconds
- `LADBS_HEADLESS` - Set to "0" to force headed LADBS fallback browser runs
- `LADBS_RECORDS_MAX_PDF_RESOLUTIONS` - Limit the number of LADBS record rows that resolve PDF viewer links during a single request

**Password priority:** `APP_ACCESS_PASSWORD` > local `access_password.txt` > fallback `CHANGE_ME_DEV` outside production-like environments only

## Deployment (Render/Heroku)

- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app.ui_server:app`
- Set environment variables in platform dashboard
- Runs on port assigned by `PORT` env var (or 5000 default)
- Python version: see `runtime.txt`
- VPS guide: see `VPS_DEPLOYMENT.md`

## Usage

1. Paste Redfin URL(s) into home page (one per line)
2. Click "Run Analysis" (standard) or "Run Analysis AI" (with AI summary)
3. View generated report with metrics and timeline

**Test URLs:**
```
https://www.redfin.com/CA/Culver-City/3440-Cattaraugus-Ave-90232/home/6721247
https://www.redfin.com/CA/Los-Angeles/540-N-Gardner-St-90036/home/198348544
```

## Project Structure

- `app/` - Python modules (scrapers, orchestrator, Flask server, AI)
- `app/ladbs_smoke.py` - Repeatable LADBS smoke entrypoint for Redfin URL or direct-address checks
- `app/property_data_smoke.py` - Repeatable Lucerne-style smoke for Redfin + ZIMAS + LADBS permits + LADBS records
- `app/qa_harness.py` - Real-property QA harness with Lucerne expectations and report-render checks
- `app/zimas_pin_client.py` - Browserless ZIMAS PIN resolver used by the new LADBS pin-first path
- `app/zimas_client.py` - Browserless ZIMAS parcel-profile client
- `app/ladbs_records_client.py` - Browserless LADBS records/document search client with PDF-link resolution
- `templates/` - HTML templates (home, report, history pages)
- `static/` - CSS styles
- `data/raw/` - Cached HTML (gitignored)
- `requirements.txt` - Python dependencies
- `runtime.txt` - Python version for deployment
- `.env.example` - Safe environment variable template
- `access_password.example.txt` - Safe local password-file example
- `tests/` - Stdlib smoke tests for config, Flask routes, and parser logic

## Data Pipeline

1. `redfin_scraper.py` - Extracts property data from Redfin HTML
2. `zimas_pin_client.py` - Resolves parcel/PIN from ZIMAS address search
3. `zimas_client.py` - Fetches the browserless ZIMAS parcel profile
4. `ladbs_scraper.py` - Fetches LADBS permits by PIN over HTTP first, with Selenium PLR fallback if needed
5. `ladbs_records_client.py` - Fetches LADBS records/documents and resolves public PDF viewer links when available
6. `cslb_lookup.py` - Validates contractor licenses
7. `orchestrator.py` - Combines all sources, computes metrics, and builds the report payload
8. `ai_summarizer.py` - Generates AI analysis (optional)
9. `ui_server.py` - Flask routes and web interface

## Cost Model Rates

- New construction: $350/SF
- Remodel: $150/SF
- Addition: $300/SF
- Garage: $200/SF
- Landscape: $30K flat
- Pool: $70K (if permits exist)
- Soft costs: 6% of hard costs
- Financing: 10% interest, 15mo, 1pt

## Troubleshooting

- Missing modules: activate venv (`source .venv/bin/activate`), reinstall (`pip install -r requirements.txt`)
- Full Lucerne data smoke: run `python -m app.property_data_smoke --redfin-url https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003`
- LADBS scraping fails: first try the default `pin-first` smoke path, then verify Chrome/ChromeDriver and review `data/logs/ladbs/` only if browser fallback is still needed
- LADBS on Windows/Codex: if Chromium cannot lock a profile under the repo path, point `LADBS_SELENIUM_PROFILE_DIR`, `LADBS_BROWSER_ENV_DIR`, and `SE_CACHE_PATH` to a writable `%LOCALAPPDATA%` location before re-running the smoke command
- No AI summary: set `ONE_MIN_AI_API_KEY` in environment
- Empty permits: property may have no permit history or LADBS temporarily unavailable
- Empty LADBS records: verify the APN is present, then rerun the property-data smoke to inspect the selected address candidates and records metadata
- Production startup fails: set `APP_ENV=production`, `FLASK_SECRET_KEY`, and `APP_ACCESS_PASSWORD`

## Tests

Run the smoke suite with:

```bash
python -m unittest discover -s tests -v
python -m compileall app tests
```

Repeatable LADBS smoke commands:

```bash
python -m app.ladbs_smoke --redfin-url https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003 --json
python -m app.ladbs_smoke --address "1120 S Lucerne Blvd, Los Angeles, CA 90019" --json
python -m app.ladbs_smoke --strategy plr --address "1120 S Lucerne Blvd, Los Angeles, CA 90019" --json
```

The default smoke strategy is now `pin-first`, which resolves ZIMAS PIN data and fetches LADBS permits over HTTP before any browser fallback is attempted.

Repeatable Lucerne full-data smoke command:

```bash
python -m app.property_data_smoke --redfin-url https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003
python -m app.property_data_smoke --redfin-url https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003 --json
python -m app.qa_harness
python -m app.qa_harness --json
python -m app.qa_harness --property-file validation/los_angeles_five_property_pack.json
python -m app.qa_harness --property-file validation/los_angeles_five_property_pack.json --json
```

The property-data smoke validates the browserless ZIMAS parcel profile, the browserless LADBS records/documents search, and the existing LADBS permit flow together. It prints record counts plus public PDF viewer links when LADBS exposes digital images. Downloaded PDFs and generated artifacts remain out of git.

The QA harness layers Lucerne-specific expectations on top of the orchestrated payload and rendered report. It checks schema warnings, key source states, representative permit/document IDs, core ZIMAS values, and basic report cleanliness (`Review Flags`, `Data Notes`, no raw `None`/`null`).

The five-property validation pack in `validation/los_angeles_five_property_pack.json` extends that same harness across a small real Los Angeles property set for broader live QA without adding new providers.

Exact Windows PowerShell env vars that produced the earlier PLR browser fallback green path in this repo:

```powershell
$env:LADBS_SELENIUM_PROFILE_DIR = Join-Path $env:LOCALAPPDATA 'comp-intel-ladbs\profiles'
$env:LADBS_BROWSER_ENV_DIR = Join-Path $env:LOCALAPPDATA 'comp-intel-ladbs\browser-env'
$env:SE_CACHE_PATH = Join-Path $env:LOCALAPPDATA 'comp-intel-ladbs\selenium-cache'
python -m app.ladbs_smoke --strategy plr --show-diagnostics --json
```

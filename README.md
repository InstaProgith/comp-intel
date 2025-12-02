# Real Estate Development Intelligence Tool (BLDGBIT)

Flask web app that analyzes LA single-family home development projects by scraping Redfin listings, LADBS permits, and CSLB contractor licenses.

## Overview

Generates development analysis reports for residential properties:
- Property snapshot (address, beds/baths/SF, lot size, year built, sale status)
- Transaction analysis (purchase/exit price, hold period, spread, ROI)
- Development timeline (construction stages from permits to completion)
- Construction summary (existing SF, added SF, scope level)
- Cost model (estimated construction costs using industry rates)
- Permit overview (building, demolition, MEP permits)
- Team info (general contractor, architect, engineer with license data)

## Quick Start

**Prerequisites:** Python 3.11+, Git, Chrome + ChromeDriver

**Run locally:**
```bash
git clone https://github.com/InstaProgith/comp-intel.git
cd comp-intel
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.ui_server
# Open http://localhost:5000
# Password: see access_password.txt
```

## Environment Variables

**Production (required):**
- `FLASK_SECRET_KEY` - Session encryption key (generate random string)
- `APP_ACCESS_PASSWORD` - Login password (overrides access_password.txt)

**Optional:**
- `ONE_MIN_AI_API_KEY` - For AI-generated summaries
- `FLASK_DEBUG` - Set to "1" for debug mode (never in production)

**Password priority:** Environment var `APP_ACCESS_PASSWORD` > `access_password.txt` > fallback "CHANGE_ME_DEV"

## Deployment (Render/Heroku)

- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app.ui_server:app`
- Set environment variables in platform dashboard
- Runs on port assigned by `PORT` env var (or 5000 default)
- Python version: see `runtime.txt`

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
- `templates/` - HTML templates (home, report, history pages)
- `static/` - CSS styles
- `data/raw/` - Cached HTML (gitignored)
- `requirements.txt` - Python dependencies
- `runtime.txt` - Python version for deployment
- `access_password.txt` - Default password (dev/internal use only)

## Data Pipeline

1. `redfin_scraper.py` - Extracts property data from Redfin HTML
2. `ladbs_scraper.py` - Scrapes LA building permits via Selenium
3. `cslb_lookup.py` - Validates contractor licenses
4. `orchestrator.py` - Combines all sources, computes metrics, builds timeline
5. `ai_summarizer.py` - Generates AI analysis (optional)
6. `ui_server.py` - Flask routes and web interface

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
- LADBS scraping fails: verify Chrome/ChromeDriver installed
- No AI summary: set `ONE_MIN_AI_API_KEY` in environment
- Empty permits: property may have no permit history or LADBS temporarily unavailable

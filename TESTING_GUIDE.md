# Comp-Intel App Testing & Architecture Guide

## Quick Start: Testing in Browser

### 1. Install Dependencies

```bash
cd /workspaces/comp-intel
pip install -r requirements.txt
```

### 2. Start the Flask Server

```bash
python3 -m app.ui_server
```

You should see output like:
```
 * Serving Flask app 'ui_server'
 * Debug mode: on
 * Running on http://127.0.0.1:5000
Press CTRL+C to quit
```

### 3. Open in Browser

**Local Development:**
- Open: `http://127.0.0.1:5000`
- Or: `http://localhost:5000`

**GitHub Codespaces:**
- The terminal will show a forwarded port URL
- Click the "Ports" tab in VS Code
- Find port 5000 and click the globe icon
- Or use the auto-generated URL like: `https://username-comp-intel-xxxxxx.github.dev`

### 4. Test the App

1. **Paste Redfin URLs** (1-5 URLs, one per line):
   ```
   https://www.redfin.com/CA/Los-Angeles/7841-Stewart-Ave-90045/home/6618580
   https://www.redfin.com/CA/Los-Angeles/1393-Casiano-Rd-90049/home/6829339
   https://www.redfin.com/CA/Los-Angeles/3024-Midvale-Ave-90034/home/6752669
   ```

2. **Click "Analyze Properties"**

3. **Wait for Results** (can take 30-60 seconds per property)
   - Redfin scraping: ~5-10 seconds
   - LADBS permit scraping: ~20-40 seconds (if Selenium works)
   - AI summary generation: ~5-10 seconds

4. **Review the Report** for each property

---

## Full App Architecture

### Overview

**Comp-Intel** is a Flask web application that analyzes real estate investment deals by:
1. Scraping property data from Redfin
2. Fetching permit history from LA Department of Building & Safety (LADBS)
3. Looking up contractor licenses (CSLB)
4. Generating an AI-powered investment analysis report

### Data Flow Diagram

```
User Input (Redfin URLs)
    ↓
[ui_server.py] Flask web interface
    ↓
[orchestrator.py] Coordinates all scrapers
    ↓
    ├──→ [redfin_scraper.py] → Property details, sale history, lot size
    ├──→ [ladbs_scraper.py] → Building permits via Selenium
    └──→ [cslb_lookup.py] → Contractor license validation
    ↓
[ai_summarizer.py] → OpenAI GPT analysis
    ↓
[comp_intel.html] → Final report rendering
```

---

## Component Breakdown

### 1. **UI Server** (`app/ui_server.py`)

**Purpose:** Flask web server that handles HTTP requests

**Key Functions:**
- `comp_intel()` - Main route handler for GET/POST requests
- Input validation (max 5 URLs)
- Calls `run_multiple()` from orchestrator
- Renders results using Jinja2 template

**Endpoints:**
- `GET /` - Shows empty form
- `POST /` - Processes URLs and returns results

---

### 2. **Orchestrator** (`app/orchestrator.py`)

**Purpose:** Central coordinator that runs all scrapers and builds the final dataset

**Key Functions:**

#### `run_full_comp_pipeline(redfin_url)`
- Orchestrates the full analysis for a single property
- Calls all scrapers in sequence
- Builds `combined` dict with all data
- Returns complete property analysis

#### `run_multiple(urls)`
- Processes multiple URLs (max 5)
- Calls `run_full_comp_pipeline()` for each
- Returns list of results

#### `_build_headline_metrics(combined)`
- **CRITICAL FUNCTION** - Calculates deal metrics
- Extracts from `redfin.timeline`:
  - `purchase_price` - First "sold" event
  - `exit_price` - Last "sold" event OR current list price
  - `spread` - exit_price - purchase_price
  - `roi_pct` - (spread / purchase_price) × 100
  - `hold_days` - Days between purchase and exit

**Anti-Hallucination Rules:**
- NEVER uses tax-assessed values as prices
- Returns `None` for metrics when data is missing
- Only uses real "sold" or "listed" events

---

### 3. **Redfin Scraper** (`app/redfin_scraper.py`)

**Purpose:** Extracts property data from Redfin HTML pages

**Key Functions:**

#### `fetch_redfin_html(url)`
- Downloads HTML using `requests`
- Saves raw HTML to `data/raw/` for debugging

#### `parse_redfin_html(html, url)`
- Parses BeautifulSoup tree
- Calls specialized parsers

#### `_parse_header(soup)`
- Extracts address, status (Active/Off-market)
- Parses current list price from `[data-rf-test-id="abp-price"]`

#### `_parse_sale_history(soup)`
- **CRITICAL** - Builds `timeline` list
- Only captures real events:
  - `"sold"` - From "Sold" rows with real prices
  - `"listed"` - From "Listed" / "Price changed" rows
- **Filters out:**
  - Tax history rows (contains "tax", "assessment", etc.)
  - Rows without real prices
  - Property tax amounts

**Timeline Structure:**
```python
[
  {
    "event": "sold",
    "date": "2022-07-11",
    "price": 1358000,
    "description": "Sold (Public Records)"
  },
  {
    "event": "listed",
    "date": "2025-11-13",
    "price": 3849000,
    "description": "Listed for sale"
  }
]
```

#### `_parse_public_records(soup)`
- Extracts lot size, year built, bedrooms, bathrooms
- Parses from "Public Facts" section
- **NEVER** pulls lot size from tax tables

#### `_parse_tax_history(soup)`
- Stores tax/assessment data separately
- **NEVER** used for price calculations

---

### 4. **LADBS Scraper** (`app/ladbs_scraper.py`)

**Purpose:** Fetches building permit data from LA city website using Selenium

**Key Functions:**

#### `get_ladbs_data(apn, address, redfin_url)`
- Main entry point
- Returns dict with permits or error stub

#### `setup_driver()`
- Initializes Chrome WebDriver with headless options
- Returns `None` if Selenium/ChromeDriver unavailable

#### `search_plr(driver, street_number, street_name)`
- Navigates to LADBS PLR (Public Land Records) search
- Fills in address form
- Submits search
- Saves raw HTML to `data/raw/`

#### `get_permit_list(driver)`
- Expands accordions to reveal permit table
- Filters permits by year (≥ 2020)
- Extracts permit numbers and URLs

#### `get_permit_details(driver, permit_url)`
- Visits each permit detail page
- Extracts:
  - Permit number, type, status
  - Work description
  - Issue/approval dates
  - Contractor, architect, engineer names & license numbers
  - Status history timeline

**Error Handling:**
- If Selenium not installed → `"ladbs_stub_no_selenium"`
- If ChromeDriver fails → `"ladbs_stub_driver_error"`
- If no permits found → `"ladbs_no_permits_found"`

**Permit Output Structure:**
```python
{
  "source": "ladbs_plr_v5",
  "permits": [
    {
      "permit_number": "22016-10000-12345",
      "permit_type": "Bldg-Addition",
      "Status": "Issued",
      "Work_Description": "NEW 2-STORY SFD",
      "Issued_Date": "12/01/2022",
      "contractor": "ABC Construction Inc.",
      "contractor_license": "123456",
      "architect": "John Doe AIA",
      "architect_license": "C12345",
      "status_history": [...]
    }
  ]
}
```

---

### 5. **CSLB Lookup** (`app/cslb_lookup.py`)

**Purpose:** Validates contractor licenses via California CSLB API

**Key Functions:**

#### `validate_cslb_license(license_number)`
- Calls CSLB public API
- Returns contractor name, status, classifications
- Cached to avoid rate limits

---

### 6. **AI Summarizer** (`app/ai_summarizer.py`)

**Purpose:** Generates written investment analysis using OpenAI GPT

**Key Functions:**

#### `summarize_comp(combined_data)`
- Takes full `combined` dict as input
- Sends structured prompt to GPT-4
- Returns markdown-formatted report

**Prompt Structure:**

The prompt includes:
1. **Deal Snapshot** - Purchase price, exit price, spread, ROI, hold period
2. **Property Details** - Bedrooms, bathrooms, lot size, year built
3. **Permit Timeline** - What was built, when, by whom
4. **Team Analysis** - Contractor/architect experience
5. **Value-Add Summary** - Sources of value creation

**Anti-Hallucination Rules in Prompt:**
- "Use ONLY the data in the JSON"
- "If LADBS source starts with 'ladbs_stub_' or contains 'error', treat permits as UNKNOWN due to technical error"
- "DO NOT say 'no permits exist' if LADBS failed"
- "DO NOT interpret tax-assessed values as prices"
- "DO NOT fabricate ROI or spread beyond computed metrics"

---

### 7. **Template** (`templates/comp_intel.html`)

**Purpose:** Renders final HTML report

**Key Sections:**

#### Deal Metrics Cards
- Purchase price & date
- Exit price & date (or "—" if none)
- Current list price (if active listing)
- Spread, ROI %, hold days
- Lot size

#### Permit Summary
- Total permit count
- Key permits filtered by type (Building, Addition, etc.)
- Timeline visualization
- Contractor/architect info with CSLB validation

#### AI-Generated Analysis
- Rendered from markdown to HTML
- Structured sections with clear headings

#### Error Handling
- Shows "—" for missing data
- Friendly placeholders for LADBS errors
- No blank/null values displayed

---

## Data Integrity Rules

### NEVER Use Tax Values as Prices

**Bad Sources (ALWAYS IGNORED):**
- Property tax amounts (e.g., $15,403/year)
- Tax-assessed land value
- Tax-assessed improvement value
- Total assessed value

**Good Sources (ONLY THESE):**
- "Sold" rows in sale history with real transaction prices
- "Listed" / "Price changed" rows with real listing prices
- Current listing price from `[data-rf-test-id="abp-price"]`

### Sale vs. Listing Logic

**For Properties with NO Sale:**
```python
purchase_price = None
exit_price = None
spread = None
roi_pct = None
hold_days = None
list_price = <current listing price>  # Shown separately
```

**For Properties with Sale but No Exit:**
```python
purchase_price = <first sold event>
exit_price = None
spread = None
roi_pct = None
hold_days = None or days_since_purchase
```

---

## Testing Different Property Types

### Test Case 1: Active Listing (No Sales)
**URL:** `https://www.redfin.com/CA/Los-Angeles/7841-Stewart-Ave-90045/home/6618580`

**Expected Output:**
- Purchase: —
- Exit: —
- List Price: $3,849,000
- Timeline: Single "listed" event
- Lot: 6,001 SF (0.14 acres)

---

### Test Case 2: Sold Property (No Current Listing)
**URL:** `https://www.redfin.com/CA/Los-Angeles/1393-Casiano-Rd-90049/home/6829339`

**Expected Output:**
- Purchase: $1,150,000 on 2019-11-27
- Exit: — (or last sale if multiple)
- List Price: — (off-market)
- Lot: 21,084 SF (0.48 acres)

---

### Test Case 3: Development Project
**URL:** `https://www.redfin.com/CA/Los-Angeles/3024-Midvale-Ave-90034/home/6752669`

**Expected Output:**
- Purchase: $1,358,000 on 2022-07-11
- Exit: (current sale price if listed)
- Permits: Building addition, plan check timeline
- Contractor: Owner Builder
- Engineer: Jesus Eduardo Carrillo (NA77737)
- Build timeline calculated from permit dates

---

## Debugging Tips

### View Raw HTML
Check `data/raw/` folder for saved HTML files:
- `YYYYMMDD-HHMMSS_redfin_*.html` - Redfin pages
- `YYYYMMDD-HHMMSS_ladbs_*.html` - LADBS search results

### Check Logs
Logs are saved to `data/logs/`:
- Scraper errors
- Timeline parsing issues
- LADBS permit extraction

### Test Individual Components

**Test Redfin Scraper:**
```bash
python3 -c "
from app.redfin_scraper import fetch_and_parse_redfin
data = fetch_and_parse_redfin('https://www.redfin.com/...')
print(data)
"
```

**Test LADBS Scraper:**
```bash
python3 -m app.ladbs_scraper
```

**Test Orchestrator:**
```bash
python3 -m app.orchestrator --url "https://www.redfin.com/..."
```

### Common Issues

**LADBS Shows "Failed to start Chrome driver"**
- Install Chrome: `sudo apt-get install google-chrome-stable`
- Install ChromeDriver: Match Chrome version
- Check PATH: `which chromedriver`

**"No test named 'match'" Error**
- Ensure `app/ui_server.py` has `@app.template_test("match")` decorator
- Import `re` at top of file

**Timeline Shows Tax Values**
- Check `_parse_sale_history()` filters
- Verify tax rows are excluded
- Test with verbose logging

---

## Environment Variables

Create `.env` file:
```bash
# OpenAI API Key (required for AI summaries)
OPENAI_API_KEY=sk-...

# Optional: Custom model
OPENAI_MODEL=gpt-4-turbo-preview
```

---

## Production Considerations

**DO NOT use in production as-is:**
- No authentication
- No rate limiting
- Debug mode enabled
- Scraping may violate ToS
- Use caching for CSLB lookups
- Add error monitoring (Sentry)
- Deploy with gunicorn/uwsgi

**Recommended for:**
- Personal analysis tool
- Local market research
- Learning Selenium/scraping
- Prototyping RE investment workflows

---

## File Structure Summary

```
comp-intel/
├── app/
│   ├── ui_server.py          # Flask web server
│   ├── orchestrator.py       # Main coordinator
│   ├── redfin_scraper.py     # Redfin HTML parser
│   ├── ladbs_scraper.py      # LADBS Selenium scraper
│   ├── cslb_lookup.py        # Contractor license lookup
│   └── ai_summarizer.py      # GPT analysis generator
├── templates/
│   └── comp_intel.html       # Jinja2 report template
├── static/
│   ├── styles.css            # Custom styles
│   └── script.js             # Client-side JS
├── data/
│   ├── raw/                  # Saved HTML files
│   └── logs/                 # Error logs
├── requirements.txt          # Python dependencies
└── .env                      # API keys (not in git)
```

---

## Contributing

When modifying the app, always:
1. Test with all 3 test cases above
2. Verify no tax values leak into prices
3. Check LADBS error handling
4. Validate timeline parsing logic
5. Run: `python3 -m py_compile app/*.py`

---

## Support

For issues:
1. Check `data/logs/` for errors
2. Verify dependencies: `pip install -r requirements.txt`
3. Test individual scrapers
4. Review raw HTML in `data/raw/`

---

**Last Updated:** 2025-11-18

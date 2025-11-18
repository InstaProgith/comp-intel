# Comp-Intel App - Complete Technical Overview

## Architecture

This is a Flask-based web application that analyzes Los Angeles real estate development projects by combining Redfin listing data with LADBS permit records and AI-powered summarization.

---

## Data Flow

```
User Input (Redfin URLs)
         ↓
[UI Server] app/ui_server.py
         ↓
[Orchestrator] app/orchestrator.py
         ├→ [Redfin Scraper] app/redfin_scraper.py
         ├→ [LADBS Scraper] app/ladbs_scraper.py (Selenium)
         ├→ [CSLB Lookup] app/cslb_lookup.py (optional)
         └→ [AI Summarizer] app/ai_summarizer.py (1min.ai API)
         ↓
[Template Rendering] templates/comp_intel.html
         ↓
User Browser (formatted report)
```

---

## Core Modules

### 1. app/ui_server.py
**Purpose**: Flask web server and request handler

**Key Functions**:
- `comp_intel()` - Main route handler for GET/POST requests
- Input validation (max 5 URLs, Redfin domain check)
- Calls `run_multiple()` from orchestrator
- Renders results via Jinja2 template
- Registers custom `match` test for Jinja filtering

**Configuration**:
- Runs on `127.0.0.1:5000`
- Debug mode enabled
- Template folder: `/templates`
- Static folder: `/static`

---

### 2. app/orchestrator.py
**Purpose**: Coordinates all data collection and processing

**Key Functions**:

#### `run_full_comp_pipeline(url: str) -> Dict`
Main pipeline orchestrator:
1. Fetches Redfin data
2. Fetches LADBS data
3. Builds headline metrics
4. Parses permit timeline
5. Calculates project durations
6. Optionally looks up contractor CSLB license
7. Generates AI summary
8. Saves combined JSON output

#### `_build_headline_metrics(redfin: Dict) -> Dict`
Calculates core deal metrics:
- **Purchase**: First sold event from timeline
- **Exit**: Last sold event (NOT listing price)
- **Spread**: exit_price - purchase_price
- **ROI**: (spread / purchase_price) × 100
- **Hold Days**: exit_date - purchase_date
- **SF Changes**: new_sf - original_sf

**Critical Rule**: Listing prices are stored separately and NEVER used as purchase/exit prices.

#### `_parse_permit_timeline(permits: List) -> Dict`
Extracts permit milestones from LADBS status history:
- **Plans submitted**: Earliest "APPLICATION" event
- **Plans approved**: Earliest "PLAN CHECK APPROV" event
- **Construction completed**: Earliest "FINAL" or "CERTIFICATE OF OCCUPANCY" event

#### `_calculate_project_durations(purchase_date: str, permit_timeline: Dict) -> Dict`
Calculates durations:
- `days_to_submit`: purchase → plans submitted
- `days_to_approve`: submitted → approved
- `days_to_complete`: approved → completed
- `total_project_days`: purchase → completed

#### `run_multiple(urls: List[str]) -> List[Dict]`
Batch processor with error isolation per URL

**Error Handling**:
- Per-component error logging to `data/logs/`
- Graceful degradation (missing data → `None` instead of crash)
- Stub responses when services unavailable

---

### 3. app/redfin_scraper.py
**Purpose**: Scrapes and parses Redfin property pages

**Key Functions**:

#### `fetch_redfin_html(url: str) -> Path`
- Downloads Redfin page HTML
- Saves to `data/raw/{timestamp}_redfin_{address}.html`
- Uses realistic User-Agent headers
- 30-second timeout

#### `parse_redfin_html_listing(soup, html_text) -> Dict`
Parses current listing data:
- **Address**: `[data-rf-test-id="abp-streetLine"]`
- **Beds/Baths/SF**: `[data-rf-test-id="abp-beds/baths/sqFt"]`
- **List Price**: `[data-rf-test-id="abp-price"]` ONLY (never tax amounts)
- **Year Built**: Regex match from property details

**CRITICAL RULE**: `list_price` comes ONLY from the active listing price banner. Never from:
- Property tax amounts
- Assessed values
- Tax table numbers
- HOA fees

#### `parse_public_facts_and_apn(html_text) -> Dict`
Parses public records section:
- Beds, baths, SF (original configuration)
- **Lot size**: Multiple regex patterns for robustness
  - "Lot Size (Sq. Ft.): 21,084"
  - "Lot Size: 6,001 square feet"
  - "Lot Size: 0.48 acres"
- Year built
- APN (Assessor Parcel Number)

**CRITICAL RULE**: Lot size comes ONLY from Property Details section, never from tax tables.

#### `parse_sale_history(html_text, soup) -> List[Dict]`
Parses sale/listing timeline:

**Strategy 1** - PropertyHistoryEventRow divs:
- Extracts date, event type (Sold/Listed/Price changed), price
- **Filters OUT tax rows** containing keywords:
  - "tax", "assessment", "assessed", "property tax"
- **Price validation**: Must be >= $100,000 (filters out tax amounts)
- Skips events with "*" price

**Strategy 2** - Fallback to meta tags:
- Extracts from meta description: "sold for $1,150,000 on Nov 27, 2019"

**Returns**: List of timeline events:
```python
{
  "date": "2019-11-27",
  "event": "sold",  # or "listed", "price_changed"
  "price": 1150000,
  "raw_status": "Sold (Public Records)"
}
```

#### `get_redfin_data(url: str) -> Dict`
Main entry point that combines all parsing:
```python
{
  "source": "redfin_parsed_v3",
  "url": "...",
  "address": "...",
  "listing_beds": 5,
  "listing_baths": 4.5,
  "listing_building_sf": 3890,
  "list_price": 4088255,  # PRICE: from listing banner only
  "timeline": [...],  # Real sale/list events only
  "public_records": {
    "building_sf": 1379,  # Original size
    "lot_sf": 5896,
    ...
  },
  "tax": {
    "apn": "...",
    # Tax amounts kept separate, never used as prices
  },
  "lot_summary": "Lot: 5,896 SF (0.14 acres)",
  ...
}
```

---

### 4. app/ladbs_scraper.py
**Purpose**: Scrapes Los Angeles LADBS permit records via Selenium

**Configuration**:
- Target: `https://www.ladbsservices2.lacity.org/OnlineServices/...`
- Cutoff year: 2018 (configurable)
- Headless Chrome with optimized options

**Key Functions**:

#### `extract_address_from_redfin_url(url) -> (street_num, street_name)`
Parses Redfin URL to extract search terms:
- Input: `https://www.redfin.com/CA/Los-Angeles/3025-Midvale-Ave-90034/home/6752642`
- Output: `("3025", "Midvale")`
- Removes directionals (N/S/E/W) and suffixes (Ave/St/Blvd)

#### `setup_driver() -> ChromeDriver`
Configures headless Chrome:
```python
options = [
  "--headless=new",
  "--no-sandbox",
  "--disable-dev-shm-usage",
  "--window-size=1920,1080",
  ...
]
```

#### `search_plr(driver, street_number, street_name) -> str`
Automated search workflow:
1. Navigate to PLR page
2. Fill "Street Number" field
3. Fill "Street Name" field
4. Click "Search" button
5. Save results HTML to `data/raw/{timestamp}_ladbs_{address}.html`
6. Return results URL

#### `get_permit_list(driver) -> List[Dict]`
Extracts permit list from results:
1. Expands permit accordion (#pcis)
2. Expands address accordions
3. Parses permit table rows
4. Filters by status date >= cutoff year

Returns:
```python
[
  {
    "permit_number": "22014-10000-04385",
    "url": "https://...",
    "status_text": "CofO issued 9/8/2023",
    "status_date": "9/8/2023"
  },
  ...
]
```

#### `get_permit_details(driver, permit_url) -> Dict`
Clicks into individual permit and extracts:
- General Info: permit number, job number, group, type, sub-type, work description
- Status: current status, permit issued, CO date
- **Contact Information**: Contractor, Architect, Engineer with license numbers
- **Status History**: List of events with dates

```python
{
  "permit_number": "22014-10000-04385",
  "job_number": "B22LA17480",
  "type": "Bldg-Addition",
  "work_description": "Two-story addition and major remodel...",
  "current_status": "CofO issued",
  "certificate_of_occupancy": "9/8/2023",
  "contact_information": {
    "Contractor": "Owner Builder",
    "Structural Engineer": "Carrillo, Jesus Eduardo - Lic. No.: NA77737"
  },
  "status_history": [
    {"event": "Application", "date": "9/1/2022", "person": "..."},
    {"event": "Plan Check Approved", "date": "12/1/2022", "person": "..."},
    {"event": "Permit Issued", "date": "12/2/2022", "person": "..."},
    {"event": "CofO issued", "date": "9/8/2023", "person": "..."}
  ]
}
```

#### `get_ladbs_data(apn, address, redfin_url) -> Dict`
Main entry point:

**Success case**:
```python
{
  "source": "ladbs_plr_v5",
  "apn": "...",
  "address": "...",
  "fetched_at": "2025-11-18 06:47:09",
  "permits": [...],  # List of summarized permits
  "note": "Found 8 permits with status date >= 2018 via PLR."
}
```

**Error cases** (graceful degradation):
```python
# Selenium not installed
{"source": "ladbs_stub_no_selenium", "permits": [], "note": "..."}

# ChromeDriver failed
{"source": "ladbs_stub_driver_error", "permits": [], "note": "..."}

# No permits found
{"source": "ladbs_no_permits_found", "permits": [], "note": "..."}
```

---

### 5. app/ai_summarizer.py
**Purpose**: Generates developer-oriented written summaries via 1min.ai API

**Configuration**:
- API Key: `ONE_MIN_API_KEY` environment variable (.env file)
- Endpoint: `https://api.1min.ai/api/features`

**Key Function**:

#### `summarize_comp(combined_data: dict) -> str`
Sends combined JSON to AI with structured prompt requesting:

1. **Deal Snapshot**:
   - Address, configuration, purchase/exit, hold, spread, ROI
   - Size changes (original SF → new SF)

2. **Scope of Work (Permits)**:
   - Categorized by type (building, demo, MEP)
   - Work descriptions
   - Status (active/finaled)

3. **Team (Competitor Network)**:
   - Contractor (flag owner-builder)
   - Architect
   - Structural engineer
   - Repeated players

4. **Permit Timing (Durations)**:
   - Submitted → Approved
   - Approved → Issued
   - Issued → Finaled

5. **Value-Add Summary**:
   - What they bought, what they built, how long it took

**Anti-Hallucination Rules**:
- Only use numbers present in JSON
- Never interpret missing data as "no permits" or "no work done"
- If LADBS source starts with "ladbs_stub_" or "ladbs_error", state that permit data is unavailable

---

### 6. templates/comp_intel.html
**Purpose**: Renders the developer-focused web interface

**Structure**:

#### Header Section
- BLDGBIT AI branding
- "Comp Intelligence" title
- Input form (1-5 Redfin URLs)

#### Results Loop (for each property)
```jinja
{% for r in results %}
  <article class="comp-card">
    <!-- Property header with address + stats -->
    <header class="comp-header">
      <div class="stat-grid">
        <div class="stat-pill">CURRENT: {{ r.current_summary }}</div>
        <div class="stat-pill">PUBLIC RECORD: {{ r.public_record_summary }}</div>
        <div class="stat-pill">LOT: {{ r.lot_summary }}</div>
        <div class="stat-pill">LADBS PERMITS: {{ r.permit_summary }}</div>
      </div>
    </header>

    <!-- Project Snapshot -->
    <section class="comp-body">
      <div class="deal-snapshot">
        <h3>Project Snapshot</h3>
        
        <!-- Purchase -->
        Purchased: {{ r.metrics.purchase_date }} for ${{ r.metrics.purchase_price }}
        
        <!-- Size Change -->
        Size change: {{ r.metrics.original_sf }} SF → {{ r.metrics.new_sf }} SF
        (+{{ r.metrics.sf_added }} SF / +{{ r.metrics.sf_pct_change }}%)
        
        <!-- Permit Timeline -->
        Plans submitted: {{ r.permit_timeline.plans_submitted_date }}
          ({{ r.project_durations.days_to_submit }} days after purchase)
        
        Plans approved: {{ r.permit_timeline.plans_approved_date }}
          ({{ r.project_durations.days_to_approve }} days after submission)
        
        Construction completed: {{ r.permit_timeline.construction_completed_date }}
          ({{ r.project_durations.days_to_complete }} days after approval)
        
        Total project time: {{ r.project_durations.total_project_days }} days
      </div>
      
      <!-- Team -->
      <div class="deal-snapshot">
        <h3>Team</h3>
        Contractor: {{ contractors[0] }}
        Architect: {{ architects[0] or "None on record" }}
        Engineer: {{ engineers[0] or "None on record" }}
      </div>
      
      <!-- Deal Metrics -->
      <div class="deal-snapshot">
        <h3>Deal Metrics</h3>
        Purchase price: ${{ r.metrics.purchase_price }}
        Exit/List price: ${{ r.metrics.exit_price or r.metrics.list_price }}
        Gross spread: ${{ r.metrics.spread }}
        ROI: {{ r.metrics.roi_pct }}%
        Hold period: {{ r.metrics.hold_days }} days
      </div>
    </section>
  </article>
{% endfor %}
```

**Key Display Logic**:
- `{% if r.metrics.purchase_price %}` - Show purchase data only if exists
- `{% if r.metrics.exit_price %}` - Show exit only if sold again
- `{% elif r.metrics.list_price %}` - Otherwise show listing price
- `{% else %}—{% endif %}` - Fallback to "—" for missing data

**Jinja Filters**:
- `"${:,.0f}".format(price)` - Format currency with commas
- `selectattr('permit_type', 'match', 'regex')` - Filter permits by regex
- Custom `match` test registered in ui_server.py

---

### 7. static/css/comp.css
**Purpose**: Styling for the web interface

**Key Styles**:

#### Layout
```css
.shell { max-width: 900px; margin: 0 auto; }
.comp-card { background: #fff; border-radius: 16px; margin-bottom: 32px; }
```

#### Developer-Focused Report Styles
```css
.snapshot-item-wide {
  display: flex; 
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid #f0f0f0;
}

.snapshot-label {
  min-width: 180px; 
  font-weight: 600; 
  color: #666;
}

.snapshot-value {
  flex: 1; 
  font-size: 15px;
}

.snapshot-success {
  color: #059669;  /* Green for positive metrics */
  font-weight: 600;
}

.muted {
  color: #999;
  font-size: 13px;
}
```

#### Section Headers
```css
.section-header {
  margin: 24px 0 16px;
  padding-bottom: 8px;
  border-bottom: 2px solid #111;
}

.section-title {
  font-size: 18px;
  font-weight: 700;
  text-transform: uppercase;
}
```

---

## Data Storage

All data is saved locally in the `data/` directory:

### data/raw/
Snapshots of fetched HTML pages:
```
20251118-065039_redfin_3025_Midvale_Ave_90034.html
20251118-065121_ladbs_3025_Midvale.html
```

### data/summaries/
Combined JSON output with all metrics:
```json
{
  "url": "...",
  "address": "...",
  "headline_metrics": {...},
  "permit_timeline": {...},
  "project_durations": {...},
  "redfin": {...},
  "ladbs": {...},
  "summary_markdown": "..."
}
```

### data/logs/
Error logs for debugging:
```
redfin_error_20251118_065500.log
ladbs_error_20251118_065500.log
```

---

## Key Anti-Hallucination Safeguards

### Price Data
1. **List price** comes ONLY from `[data-rf-test-id="abp-price"]`
2. **Timeline prices** come ONLY from PropertyHistoryEventRow with:
   - Event type: "Sold", "Listed", or "Price changed"
   - Price validation: >= $100,000
   - Tax row filtering: Skip rows with keywords "tax", "assessment", etc.
3. **Purchase/Exit** come ONLY from actual "sold" events in timeline
4. **Listing prices** are stored separately, never used as purchase/exit

### Metrics Calculation
1. If no sold events exist:
   - purchase_price = None
   - exit_price = None
   - spread = None
   - roi_pct = None
   - hold_days = None
2. list_price is displayed separately in UI

### LADBS Error Handling
1. If Selenium unavailable: `{"source": "ladbs_stub_no_selenium", "permits": []}`
2. If ChromeDriver fails: `{"source": "ladbs_stub_driver_error", "permits": []}`
3. AI prompt explicitly checks for stub sources and treats as "data unavailable"

---

## Testing

### Command Line
```bash
# Single URL
python3 -m app.orchestrator --url "https://www.redfin.com/CA/Los-Angeles/..."

# View output
cat data/summaries/comp_*.json | python3 -m json.tool
```

### Web Interface
```bash
# Start server
python3 -m app.ui_server

# Access at http://127.0.0.1:5000
```

### Validation
```bash
# Syntax check
python3 -m py_compile app/*.py

# Template syntax (runs server briefly)
python3 -c "from app.ui_server import app; app.run(debug=False, use_reloader=False)" &
sleep 2
curl http://127.0.0.1:5000 > /dev/null
kill %1
```

---

## Dependencies

### Python Packages (requirements.txt)
```
requests       # HTTP client for Redfin fetching
beautifulsoup4 # HTML parsing
lxml           # BeautifulSoup parser
selenium       # Browser automation for LADBS
flask          # Web framework
python-dotenv  # Environment variable loading
```

### System Requirements
- **ChromeDriver**: For Selenium automation
- **Google Chrome**: Headless browser
- **Python 3.8+**: For type hints and modern syntax

### Optional
- **ONE_MIN_API_KEY**: For AI summarization (app works without it, just no markdown summary)

---

## Environment Variables (.env)

```bash
ONE_MIN_API_KEY=your_api_key_here
```

If missing, summarizer returns stub message instead of crashing.

---

## Error Recovery Patterns

The app uses graceful degradation throughout:

1. **Redfin fetch fails** → Return stub with empty timeline
2. **LADBS Selenium fails** → Return stub with no permits
3. **AI API fails** → Return error message, but show raw data
4. **Permit parsing fails** → Continue with next permit
5. **Metric calculation fails** → Set to None, don't crash

This ensures that partial data is always returned and displayed.

---

## Future Enhancements

Potential improvements based on current architecture:

1. **Database storage** (PostgreSQL/SQLite) instead of JSON files
2. **Background job queue** (Celery) for async LADBS scraping
3. **Caching layer** (Redis) to avoid re-scraping same properties
4. **Historical tracking** - detect when permits/prices update
5. **Bulk import** - CSV upload of multiple addresses
6. **Export** - PDF/Excel reports
7. **API endpoints** - RESTful API for programmatic access
8. **Authentication** - User accounts and saved searches

---

## Maintenance Notes

### Redfin Structure Changes
If Redfin changes their HTML structure:
1. Update selectors in `parse_redfin_html_listing()`
2. Update regex patterns in `parse_sale_history()`
3. Test with multiple property types (active/sold/off-market)

### LADBS Website Changes
If LADBS changes their portal:
1. Update selectors in `search_plr()` and `get_permit_list()`
2. Update accordion expansion logic
3. May need to add wait times if elements load slowly

### AI Prompt Tuning
To adjust summary format:
1. Edit prompt in `ai_summarizer.py`
2. Test with multiple property types
3. Validate anti-hallucination rules still work


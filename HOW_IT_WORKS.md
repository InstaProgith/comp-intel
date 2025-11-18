# How the Comp-Intel App Works - Visual Guide

## 🎯 Purpose

Analyzes real estate investment deals by scraping Redfin property data and LA building permits to understand:
- **What they paid** (purchase price)
- **What they sold for** (exit price) 
- **What they built** (permits & timeline)
- **Who did the work** (contractors/architects)
- **How profitable** (ROI, spread, hold time)

Perfect for developers researching competitor flip/development projects.

---

## 🌐 How to Test in Browser

### Start Server
```bash
python3 -m app.ui_server
```

### Access Web Interface

**Local Machine:**
```
http://127.0.0.1:5000
```

**GitHub Codespaces:**
1. Click "Ports" tab (bottom panel)
2. Port 5000 auto-forwards
3. Click globe 🌐 icon
4. Opens: `https://your-codespace.github.dev`

### Enter URLs & Analyze
Paste 1-5 Redfin URLs → Click "Analyze Properties" → Wait 30-60s

---

## 📊 Complete Data Flow

```
┌──────────────────────────────────────────────────────────────┐
│                    USER BROWSER                               │
│  Pastes Redfin URLs (1-5 properties)                         │
│  https://www.redfin.com/CA/Los-Angeles/.../home/6618580     │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTP POST
                         ↓
┌──────────────────────────────────────────────────────────────┐
│              ui_server.py (Flask Web Server)                  │
│  ┌────────────────────────────────────────────────┐          │
│  │ @app.route("/", methods=["POST"])              │          │
│  │ • Validates max 5 URLs                         │          │
│  │ • Calls orchestrator.run_multiple()            │          │
│  │ • Renders comp_intel.html template             │          │
│  └────────────────────────────────────────────────┘          │
└────────────────────────┬─────────────────────────────────────┘
                         │ Calls run_multiple(urls)
                         ↓
┌──────────────────────────────────────────────────────────────┐
│         orchestrator.py (Main Coordinator)                    │
│  ┌─────────────────────────────────────────────┐             │
│  │ For each URL:                                │             │
│  │   1. run_full_comp_pipeline(url)             │             │
│  │   2. Collect all data into 'combined' dict   │             │
│  │   3. Build headline_metrics                  │             │
│  │   4. Return results array                    │             │
│  └─────────────────────────────────────────────┘             │
└─┬──────┬──────┬─────────────────────────────────────────────┘
  │      │      │
  │      │      └─────────────────────────┐
  │      │                                │
  │      └────────────────┐               │
  │                       │               │
  ↓                       ↓               ↓
┌─────────────┐    ┌──────────────┐  ┌──────────────┐
│  Redfin     │    │   LADBS      │  │   CSLB       │
│  Scraper    │    │   Scraper    │  │   Lookup     │
└─────────────┘    └──────────────┘  └──────────────┘
  │                       │               │
  │                       │               │
  ↓                       ↓               ↓
┌──────────────────────────────────────────────────────┐
│            Data Collection Layer                      │
│                                                       │
│  Redfin Data:              LADBS Data:               │
│  ✓ Address                 ✓ Permit list             │
│  ✓ Sale history            ✓ Permit types            │
│  ✓ List price              ✓ Work descriptions       │
│  ✓ Timeline events         ✓ Issue dates             │
│  ✓ Lot size                ✓ Contractor names        │
│  ✓ Bedrooms/baths          ✓ License numbers         │
│  ✓ Year built              ✓ Status history          │
│                                                       │
│  CSLB Data:                                           │
│  ✓ License validation                                │
│  ✓ Contractor status                                 │
└───────────────────────┬───────────────────────────────┘
                        │ All data combined
                        ↓
┌──────────────────────────────────────────────────────┐
│         ai_summarizer.py (GPT-4 Analysis)            │
│  ┌────────────────────────────────────────┐          │
│  │ Prompt includes:                       │          │
│  │ • Deal snapshot (prices, ROI, hold)    │          │
│  │ • Property details (bed/bath/lot)      │          │
│  │ • Permit timeline                      │          │
│  │ • Team analysis (contractor quality)   │          │
│  │ • Value-add summary                    │          │
│  └────────────────────────────────────────┘          │
└───────────────────────┬───────────────────────────────┘
                        │ Returns markdown summary
                        ↓
┌──────────────────────────────────────────────────────┐
│    comp_intel.html (Jinja2 Template Rendering)       │
│                                                       │
│  ┌─────────────────────────────────────────┐         │
│  │ For each property:                      │         │
│  │                                         │         │
│  │ 📊 DEAL METRICS CARDS                  │         │
│  │   • Purchase: $1,358,000 (Jul 2022)    │         │
│  │   • Exit: $2,950,000 (Nov 2023)        │         │
│  │   • Spread: $1,592,000                 │         │
│  │   • ROI: 117.2%                        │         │
│  │   • Hold: 487 days                     │         │
│  │   • Lot: 6,001 SF (0.14 acres)         │         │
│  │                                         │         │
│  │ 🏗️ PERMIT SUMMARY                      │         │
│  │   • Total: 3 permits                   │         │
│  │   • Building Permit #22016-10000-xxxxx │         │
│  │   • Timeline:                          │         │
│  │     Submit: 9/1/2022                   │         │
│  │     Approve: 12/1/2022 (91 days)       │         │
│  │     Complete: 9/8/2023 (281 days)      │         │
│  │   • Contractor: Owner Builder          │         │
│  │   • Engineer: Jesus Eduardo Carrillo   │         │
│  │                                         │         │
│  │ 📝 AI INVESTMENT ANALYSIS              │         │
│  │   [Markdown rendered to HTML]          │         │
│  └─────────────────────────────────────────┘         │
└───────────────────────┬───────────────────────────────┘
                        │ HTTP Response
                        ↓
┌──────────────────────────────────────────────────────┐
│                  USER BROWSER                         │
│  Displays comprehensive investment report             │
└──────────────────────────────────────────────────────┘
```

---

## 🔍 Detailed Component Breakdown

### 1. Redfin Scraper (`redfin_scraper.py`)

**Purpose:** Extract property data from Redfin HTML

**Process:**
```
fetch_redfin_html(url)
  ↓
Download HTML with requests
  ↓
Save to data/raw/TIMESTAMP_redfin_*.html
  ↓
parse_redfin_html(html)
  ↓
  ├─→ _parse_header() → address, status, list_price
  ├─→ _parse_sale_history() → timeline events
  ├─→ _parse_public_records() → lot_sf, year_built, beds, baths
  └─→ _parse_tax_history() → tax data (kept separate)
  ↓
Return dict with all parsed data
```

**Timeline Structure:**
```python
timeline = [
  {
    "event": "sold",
    "date": "2022-07-11",
    "price": 1358000,
    "description": "Sold (Public Records)"
  },
  {
    "event": "listed",
    "date": "2023-10-15",
    "price": 2950000,
    "description": "Listed for sale"
  }
]
```

**Critical Rules:**
- ✅ ONLY uses "Sold" / "Listed" events
- ❌ NEVER uses tax amounts as prices
- ❌ Filters out tax history rows
- ✅ Parses lot size from Public Facts only

---

### 2. LADBS Scraper (`ladbs_scraper.py`)

**Purpose:** Fetch building permits using Selenium

**Process:**
```
get_ladbs_data(apn, address, redfin_url)
  ↓
Extract street number/name from Redfin URL
  ↓
setup_driver() → Chrome WebDriver
  ↓
search_plr(driver, street_number, street_name)
  ↓
Navigate to LADBS PLR website
Fill search form
Submit → Results page
  ↓
get_permit_list(driver)
  ↓
Expand accordions
Parse permit table
Filter: status_date >= 2020
  ↓
For each permit:
  get_permit_details(driver, permit_url)
    ↓
    Extract:
    • Permit number, type, status
    • Work description
    • Issue/approval dates
    • Contractor/architect/engineer
    • License numbers
    • Status history timeline
  ↓
Return permits array
```

**Permit Output:**
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
      "status_history": [
        {"event": "Plan Check Approval", "date": "11/15/2022"},
        {"event": "Permit Issued", "date": "12/01/2022"}
      ]
    }
  ]
}
```

**Error Stubs:**
- `ladbs_stub_no_selenium` - Selenium not installed
- `ladbs_stub_driver_error` - ChromeDriver failed
- `ladbs_no_permits_found` - No permits >= 2020

---

### 3. Orchestrator (`orchestrator.py`)

**Purpose:** Coordinate all scrapers and build final dataset

**Key Function: `_build_headline_metrics(combined)`**

```python
def _build_headline_metrics(combined):
    timeline = combined["redfin"]["timeline"]
    
    # Find first sold event
    sold_events = [e for e in timeline if e["event"] == "sold"]
    purchase = sold_events[0] if sold_events else None
    
    # Find last sold OR current listing
    exit_sale = sold_events[-1] if len(sold_events) > 1 else None
    listing = [e for e in timeline if e["event"] == "listed"][-1] if listing else None
    exit = exit_sale or listing
    
    # Calculate metrics
    if purchase and exit:
        spread = exit["price"] - purchase["price"]
        roi_pct = (spread / purchase["price"]) * 100
        hold_days = (parse(exit["date"]) - parse(purchase["date"])).days
    else:
        spread = None
        roi_pct = None
        hold_days = None
    
    return {
        "purchase_price": purchase["price"] if purchase else None,
        "purchase_date": purchase["date"] if purchase else None,
        "exit_price": exit["price"] if exit else None,
        "exit_date": exit["date"] if exit else None,
        "spread": spread,
        "roi_pct": roi_pct,
        "hold_days": hold_days,
        "lot_summary": combined["redfin"]["lot_summary"]
    }
```

**Logic:**
- Purchase = FIRST "sold" event
- Exit = LAST "sold" OR current "listed"
- If no purchase → all metrics = None
- If purchase but no exit → spread/ROI = None

---

### 4. AI Summarizer (`ai_summarizer.py`)

**Purpose:** Generate written analysis using GPT-4

**Prompt Structure:**

```
You are a real estate investment analyst.

STRICT RULES:
1. Use ONLY data from the JSON
2. If LADBS source contains "stub_" or "error", treat permits as UNKNOWN
3. DO NOT say "no permits exist" if LADBS failed
4. DO NOT use tax-assessed values as prices
5. DO NOT fabricate ROI/spread beyond computed metrics

Analyze this deal:
{
  "headline_metrics": {...},
  "redfin": {...},
  "ladbs": {...}
}

Generate sections:
1. DEAL SNAPSHOT - purchase, exit, spread, ROI, hold
2. PROPERTY DETAILS - bed/bath/lot/year
3. PERMIT TIMELINE - what was built, when
4. TEAM ANALYSIS - contractor quality
5. VALUE-ADD SUMMARY - sources of profit
```

**Output:** Markdown formatted report

---

### 5. Template (`comp_intel.html`)

**Purpose:** Render final HTML report

**Key Sections:**

```html
<!-- Deal Metrics Cards -->
<div class="metrics-grid">
  <div class="metric-card">
    <h3>Purchase</h3>
    <p>{{ metrics.purchase_price|format_price }} on {{ metrics.purchase_date }}</p>
  </div>
  <!-- Exit, Spread, ROI, Hold, Lot -->
</div>

<!-- Permit Summary -->
{% set building_permits = permits|selectattr('permit_type', 'match', '.*Bldg.*')|list %}
<p>Total Permits: {{ permits|length }}</p>
{% for permit in building_permits %}
  <div>{{ permit.permit_number }} - {{ permit.Work_Description }}</div>
{% endfor %}

<!-- AI Analysis -->
<div class="summary-section">
  {{ summary_markdown|safe }}
</div>
```

**Filters:**
- `format_price` - Formats 1358000 → $1,358,000
- `match` - Regex filter for permit types
- Safe markdown rendering

---

## 📈 Example: Development Project Analysis

**Input URL:**
```
https://www.redfin.com/CA/Los-Angeles/3024-Midvale-Ave-90034/home/6752669
```

**Data Collection:**

**Redfin Timeline:**
```
2022-07-11: Sold for $1,358,000
2023-10-15: Listed for $2,950,000
```

**LADBS Permits:**
```
Permit: 22016-10000-12345
Type: Bldg-Addition
Description: NEW 2-STORY SFD 3,890 SF
Contractor: Owner Builder
Engineer: Jesus Eduardo Carrillo (NA77737)

Timeline:
  Plan Submit: 9/1/2022
  Plan Approve: 12/1/2022 (91 days)
  Construction Complete: 9/8/2023 (281 days)
```

**Calculated Metrics:**
```
Purchase: $1,358,000 on Jul 11, 2022
Exit: $2,950,000 on Oct 15, 2023
Spread: $1,592,000
ROI: 117.2%
Hold: 487 days

Original: 1,379 SF
New: 3,890 SF
Expansion: +2,511 SF (+182%)

Plan Phase: 91 days
Build Phase: 281 days
Total: 372 days
```

**Generated Report:**

```markdown
## DEAL SNAPSHOT
Developer acquired 3024 Midvale Ave for $1,358,000 in July 2022
and listed the renovated property for $2,950,000 in October 2023,
representing a gross spread of $1,592,000 (117% ROI) over 487 days.

## VALUE-ADD STRATEGY
Primary value creation through ground-up construction:
- Demolished 1,379 SF single-family
- Built new 3,890 SF two-story home (+182% expansion)
- Added 2,511 SF of living space

## PERMIT TIMELINE
- Plans submitted: September 1, 2022
- Plan approval: December 1, 2022 (91-day review)
- Construction complete: September 8, 2023 (281-day build)
- Total project: 372 days from permit to completion

## TEAM ANALYSIS
Owner-builder project with structural engineering by Jesus Eduardo
Carrillo (License NA77737). No general contractor or architect on record,
suggesting experienced developer self-performing or managing subs directly.
```

---

## 🎯 Key Takeaways

### For Developers Researching Competitors:

**What You Learn:**
1. **Purchase Price** - What they paid
2. **Exit Strategy** - Sale vs. rental vs. still listed
3. **Construction Scope** - SF added, units created
4. **Timeline** - How fast from purchase → permits → completion
5. **Team** - Who they hired (contractor quality indicator)
6. **Profitability** - ROI and spread estimates

**Use Cases:**
- Validate your own deal assumptions
- Benchmark construction timelines
- Identify active developers in a market
- Reverse-engineer value-add strategies
- Find experienced contractors/architects

### Data Integrity:

✅ **Accurate:** Only uses real transaction/listing prices  
✅ **Transparent:** Shows "—" when data missing  
✅ **Honest:** Doesn't fabricate metrics from incomplete data  
✅ **Debuggable:** Saves raw HTML for validation  

---

## 📚 Additional Resources

- **TESTING_GUIDE.md** - Full architecture documentation
- **QUICK_REFERENCE.md** - Quick start commands
- **data/raw/** - Saved HTML for debugging
- **data/logs/** - Error logs

---

**Ready to test!** Run: `python3 -m app.ui_server`

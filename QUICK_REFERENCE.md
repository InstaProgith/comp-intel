# Quick Start Guide - Comp Intel App

## Start the App (3 Steps)

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Start Flask Server
```bash
python3 -m app.ui_server
```

### 3. Open Browser
- **Local:** http://127.0.0.1:5000
- **Codespaces:** Click the "Ports" tab → Forward port 5000 → Click globe icon

---

## How to Use

1. **Paste Redfin URLs** (1-5 properties, one per line)
2. **Click "Analyze Properties"**
3. **Wait 30-60 seconds** per property
4. **Review the report:**
   - Deal metrics (purchase, exit, ROI, hold time)
   - Lot size & property details
   - Permit history & timeline
   - Contractor/architect info
   - AI-generated investment analysis

---

## Test Properties

### Active Listing (No Sale)
```
https://www.redfin.com/CA/Los-Angeles/7841-Stewart-Ave-90045/home/6618580
```
**Expect:** List price only, no purchase/exit metrics

### Sold Property
```
https://www.redfin.com/CA/Los-Angeles/1393-Casiano-Rd-90049/home/6829339
```
**Expect:** Purchase $1,150,000 (Nov 2019), lot 21,084 SF

### Development Project
```
https://www.redfin.com/CA/Los-Angeles/3024-Midvale-Ave-90034/home/6752669
```
**Expect:** Purchase $1,358,000 (Jul 2022), permits with timeline

---

## What the App Does

```
Redfin URL(s)
    ↓
Scrapes Redfin HTML
    ↓
Fetches LADBS Permits (Selenium)
    ↓
Validates Contractor Licenses
    ↓
GPT-4 Analysis
    ↓
Investment Report
```

**Metrics Calculated:**
- Purchase price & date (first sale)
- Exit price & date (last sale or listing)
- Spread (exit - purchase)
- ROI % (spread / purchase × 100)
- Hold days (time between transactions)
- Lot size from property details
- Permit timeline (plan submit → approval → completion)

**Anti-Hallucination Rules:**
✓ NEVER uses tax-assessed values as prices  
✓ Shows "—" for missing data (no fake numbers)  
✓ Distinguishes LADBS errors from "no permits"  
✓ Only uses real "Sold" or "Listed" events  

---

## Troubleshooting

**LADBS Error "Failed to start Chrome driver"**
- Install Chrome: `sudo apt-get install google-chrome-stable`
- Install ChromeDriver matching your Chrome version

**Template Error "No test named 'match'"**
- Fixed: `app/ui_server.py` now registers the `@app.template_test("match")` decorator

**Wrong Prices Showing**
- Check `data/raw/` for saved HTML
- Verify timeline parsing in redfin_scraper.py
- Ensure no tax values in metrics

---

## Files You May Need to Edit

- **app/ui_server.py** - Web server, routes
- **app/orchestrator.py** - Deal metrics calculation
- **app/redfin_scraper.py** - Redfin parsing logic
- **app/ladbs_scraper.py** - LADBS permit scraping
- **app/ai_summarizer.py** - GPT prompt & analysis
- **templates/comp_intel.html** - Report HTML template

---

## Environment Setup

Create `.env` file:
```bash
OPENAI_API_KEY=sk-your-key-here
```

---

For full documentation, see `TESTING_GUIDE.md`

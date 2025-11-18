# Quick Start Guide - Comp-Intel Developer Reports

## Get Started in 60 Seconds

### 1. Start the Server
```bash
cd /workspaces/comp-intel
python3 -m app.ui_server
```

### 2. Open Browser
Navigate to: **http://127.0.0.1:5000**

### 3. Paste a Redfin URL
Example:
```
https://www.redfin.com/CA/Los-Angeles/3025-Midvale-Ave-90034/home/6752642
```

### 4. Click "Run Analysis"
Wait 30-60 seconds for results.

---

## What You'll See

### Project Snapshot Section
- **Purchase**: Date and price from sale history
- **Size change**: Original SF → New SF (+delta / +%)
- **Permit timeline**:
  - Plans submitted (+ days after purchase)
  - Plans approved (+ days after submission)
  - Construction completed (+ days after approval)
  - Total project time in days

### Team Section
- **Contractor**: Name and license (flags owner-builder)
- **Architect**: Name or "None on record"
- **Engineer**: Name and license number

### Deal Metrics Section
- **Purchase price**
- **Exit/List price** (differentiates sold vs active listing)
- **Gross spread** (exit - purchase)
- **ROI** (spread / purchase × 100%)
- **Hold period** (days from purchase to exit)

---

## Example Report Output

For 3025 Midvale Ave (completed development):

```
PROJECT SNAPSHOT
Purchased: [date] for $1,358,000
Size change: 1,379 SF → 3,890 SF (+2,511 SF / +182%)
Plans submitted: Sep 1, 2022 (52 days after purchase)
Plans approved: Dec 1, 2022 (91 days after submission)
Construction completed: Sep 8, 2023 (281 days after approval)
Total project time: 424 days

TEAM
Contractor: Owner builder
Architect: None on record
Engineer: Jesus Eduardo Carrillo (Lic. NA77737)

DEAL METRICS
Purchase price: [varies by Redfin data availability]
Exit/List price: $4,088,255 (current listing)
Gross spread: [calculated if sold]
ROI: [calculated if sold]
Hold period: [calculated if sold]
```

---

## Command Line Option

Test a single URL without the UI:

```bash
python3 -m app.orchestrator --url "https://www.redfin.com/CA/Los-Angeles/..."
```

Output will print to terminal and save JSON to `data/summaries/`.

---

## Troubleshooting

### "No LADBS permit data available"
- LADBS requires Selenium + ChromeDriver
- Install with: `pip install selenium`
- The app still works, just won't show permit timeline

### Missing Purchase Data
- Property may not have sold history on Redfin
- Only the most recent sale may be visible
- Parser correctly extracts whatever Redfin provides

### Slow Performance
- LADBS scraping takes 30-60 seconds per property
- Redfin scraping is fast (~2 seconds)
- AI summarization adds 5-10 seconds

---

## Next Steps

- Read **HOW_TO_USE.md** for detailed testing instructions
- Read **COMPLETE_APP_OVERVIEW.md** for technical architecture
- Read **CHANGES_SUMMARY.md** to understand what was implemented


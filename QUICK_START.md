# 🚀 Quick Start - Comp Intel Developer Reports

## Start the App (3 seconds)
```bash
cd /workspaces/comp-intel
python3 -m app.ui_server
```

Open browser: **http://localhost:5000**

## Test Properties

### Active Listing (Stewart Ave)
```
https://www.redfin.com/CA/Los-Angeles/7841-Stewart-Ave-90045/home/6618580
```
Shows: Listing price, 7 permits, work descriptions

### New Construction (Otsego St)
```
https://www.redfin.com/CA/Sherman-Oaks/13157-Otsego-St-91423/home/5216364
```
Shows: Owner-builder teardown + rebuild, 8 permits

### Sold Property (Casiano Rd)
```
https://www.redfin.com/CA/Los-Angeles/1393-Casiano-Rd-90049/home/6829339
```
Shows: Purchase $1.15M (2019), lot 21,084 SF

## What You'll See

### Deal Snapshot (2-row grid)
- Purchase, Exit, Listing prices
- Spread, ROI, Hold days
- Permit count

### Work Performed (Auto-grouped)
- **Building & Structure** → Additions, new construction
- **Demolition** → Teardown permits
- **MEP & Other** → Electrical, plumbing, fire, pool

### Team
- Contractors with license numbers
- Architects with license numbers

## Command Line Use
```bash
# Single property
python3 -m app.orchestrator --url "https://www.redfin.com/..."

# Output location
ls -t data/summaries/*.json | head -1
```

## Report Format
✅ **Compact** - All key info visible without scrolling  
✅ **Scannable** - 10-15 seconds per property  
✅ **Work-focused** - See what they built immediately  
✅ **Team visibility** - Know who did the work  

## Troubleshooting

### "No LADBS permit data available"
Chrome/ChromeDriver issue. Permit scraping failed but Redfin data still works.

### "No purchase data"
Property is an active listing or off-market. No sale history found.

### Blank lot size
Lot info not found in Redfin's property details section.

## Files
- **Reports:** `data/summaries/comp_*.json`
- **Raw HTML:** `data/raw/`
- **Config:** Check `app/orchestrator.py` for settings

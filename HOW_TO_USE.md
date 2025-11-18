# How to Test the Comp-Intel App in Browser

## 1. Start the Flask Server

```bash
cd /workspaces/comp-intel
python3 -m app.ui_server
```

You should see output like:
```
 * Serving Flask app 'ui_server'
 * Debug mode: on
 * Running on http://127.0.0.1:5000
Press CTRL+C to quit
```

## 2. Access the App

Open your browser and navigate to:
```
http://127.0.0.1:5000
```

If you're using VS Code's port forwarding or GitHub Codespaces, use the forwarded URL shown in your Ports panel.

## 3. Run an Analysis

1. Paste one or more Redfin URLs (up to 5) into the text area, one per line
2. Click "Run Analysis"
3. Wait for the loading animation to complete
4. Review the developer-focused report

## Example URLs to Test

### Active Listing (Stewart Ave)
```
https://www.redfin.com/CA/Los-Angeles/7841-Stewart-Ave-90045/home/6618580
```
Expected: No purchase/exit data, shows listing price only

### Completed Project (Midvale Ave)
```
https://www.redfin.com/CA/Los-Angeles/3025-Midvale-Ave-90034/home/6752642
```
Expected: Shows permit timeline with dates for submission, approval, completion

### Sold Property (Casiano Rd)
```
https://www.redfin.com/CA/Los-Angeles/1393-Casiano-Rd-90049/home/6829339
```
Expected: Shows purchase price and date from 2019

---

## Understanding the Report Format

The new developer-focused report includes:

### Project Snapshot
- Purchase date and price
- Size changes (original SF → new SF)
- Permit timeline milestones:
  - Plans submitted (+ days after purchase)
  - Plans approved (+ days after submission)
  - Construction completed (+ days after approval)
  - Total project duration

### Team
- Contractor (flags owner-builder)
- Architect
- Engineer (with license numbers)

### Deal Metrics
- Purchase price
- Exit/List price
- Gross spread
- ROI percentage
- Hold period

---

## Command Line Testing

You can also test individual URLs via command line:

```bash
python3 -m app.orchestrator --url "https://www.redfin.com/CA/Los-Angeles/3025-Midvale-Ave-90034/home/6752642"
```

This will:
1. Scrape Redfin data
2. Query LADBS for permits (via Selenium)
3. Calculate metrics and timeline
4. Generate AI summary
5. Save JSON output to `data/summaries/`
6. Print headline metrics to terminal

---

## Troubleshooting

### LADBS Not Working
If you see "No LADBS permit data available" but know permits exist:

1. Make sure Selenium and ChromeDriver are installed:
```bash
pip install selenium
# ChromeDriver should be installed and on PATH
```

2. Check the LADBS scraper log files in `data/logs/`

3. The app will still work without LADBS data, showing Redfin metrics only

### No Purchase Data
If a property shows "—" for purchase:
- The property may never have sold (land or new construction)
- Redfin may not have complete sale history
- Only the most recent sale may be visible on the page

### Missing Permit Timeline
If permit dates don't show:
- The permits may not have status history in LADBS
- Permits may be from before 2018 (cutoff year)
- Check the raw permit data in the JSON output

---

## Data Storage

All data is saved locally:

- **Raw HTML**: `data/raw/` - Redfin page snapshots
- **Summaries**: `data/summaries/` - Full JSON output with metrics
- **Logs**: `data/logs/` - Error logs for debugging


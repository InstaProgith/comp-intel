# Comp-Intel: Real Estate Investment Analysis Tool

A Flask web application that analyzes real estate investment deals by scraping Redfin property data and LA building permits to help developers research competitor projects.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Start server
python3 -m app.ui_server

# Open browser
# Local: http://127.0.0.1:5000
# Codespaces: Ports tab → Port 5000 → Click globe icon
```

## What It Does

Analyzes investment properties to show:
- **Purchase & exit prices** from Redfin sale history
- **Deal metrics**: spread, ROI, hold time
- **Building permits** from LADBS (timeline, team, scope)
- **AI-generated analysis** using GPT-4

Perfect for developers researching what competitors paid, how they added value, and who they hired.

## Example Output

For a development project:
```
Purchase:  $1,358,000 (Jul 2022)
Exit:      $2,950,000 (Oct 2023)
Spread:    $1,592,000
ROI:       117%
Hold:      487 days

Construction:
  Original: 1,379 SF
  New:      3,890 SF (+182%)

Permit Timeline:
  Submit:   9/1/2022
  Approve:  12/1/2022 (91 days)
  Complete: 9/8/2023 (281 days)

Team:
  Contractor: Owner Builder
  Engineer: Jesus Eduardo Carrillo
```

## Documentation

- **[START_HERE.md](START_HERE.md)** - Quick overview & getting started
- **[HOW_IT_WORKS.md](HOW_IT_WORKS.md)** - Complete architecture & data flow
- **[TESTING_GUIDE.md](TESTING_GUIDE.md)** - Full testing & troubleshooting
- **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - Command cheat sheet

## Architecture

```
Browser → Flask Server → Orchestrator
                           ├─→ Redfin Scraper (sale history, lot size)
                           ├─→ LADBS Scraper (permits via Selenium)
                           └─→ CSLB Lookup (license validation)
                           ↓
                         AI Summarizer (GPT-4)
                           ↓
                         HTML Report
```

## Key Features

✅ **Accurate pricing** - Only uses real sale/list prices, never tax values  
✅ **Transparent metrics** - Shows "—" for missing data, no fabrication  
✅ **Permit timeline** - Plan submission → approval → completion dates  
✅ **Team validation** - Contractor/architect licenses verified  
✅ **AI analysis** - GPT-4 generates investment summary  

## Test Properties

```
https://www.redfin.com/CA/Los-Angeles/7841-Stewart-Ave-90045/home/6618580
https://www.redfin.com/CA/Los-Angeles/3024-Midvale-Ave-90034/home/6752669
```

## Requirements

- Python 3.8+
- Flask
- Selenium + ChromeDriver (for LADBS permits)
- OpenAI API key (for AI summaries)

## Configuration

Create `.env` file:
```bash
OPENAI_API_KEY=sk-your-key-here
```

## Troubleshooting

**Chrome driver errors?**
```bash
sudo apt-get install google-chrome-stable
# Install ChromeDriver matching Chrome version
```

**Missing permits?**
- Selenium/ChromeDriver required for LADBS scraping

**No AI summary?**
- Set `OPENAI_API_KEY` in `.env`

## Development

```bash
# Test individual components
python3 -m app.orchestrator --url "https://www.redfin.com/..."

# Check syntax
python3 -m py_compile app/*.py

# View raw HTML
ls data/raw/

# Check logs
ls data/logs/
```

## Project Structure

```
comp-intel/
├── app/
│   ├── ui_server.py         # Flask web server
│   ├── orchestrator.py      # Coordinates scrapers
│   ├── redfin_scraper.py    # Redfin parser
│   ├── ladbs_scraper.py     # LADBS Selenium scraper
│   └── ai_summarizer.py     # GPT-4 analysis
├── templates/
│   └── comp_intel.html      # Report template
├── data/
│   ├── raw/                 # Saved HTML
│   └── logs/                # Error logs
└── requirements.txt
```

## Use Cases

- Research competitor acquisition prices
- Benchmark construction timelines
- Identify value-add strategies
- Find quality contractors/architects
- Validate your own deal assumptions
- Reverse-engineer successful projects

## Limitations

- Redfin data only (no MLS access)
- LA permits only (LADBS database)
- Scraping may violate ToS
- Not production-ready (no auth, rate limits)

## License

MIT

## Support

For issues, check:
1. `data/logs/` for error messages
2. `data/raw/` for saved HTML files
3. Documentation in `TESTING_GUIDE.md`

---

**Ready to start?** Read [START_HERE.md](START_HERE.md)

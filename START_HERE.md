# 🏠 Comp-Intel App - Start Here

## What Is This?

A Flask web app that analyzes real estate investment deals by scraping Redfin and LA building permits.

**Perfect for developers researching:**
- What competitors paid for properties
- How they added value (new construction, additions)
- Build timelines (plan approval → completion)
- Team quality (contractors, architects)
- Deal profitability (ROI, spread, hold time)

---

## Quick Start (3 Steps)

### 1️⃣ Install Dependencies
```bash
pip install -r requirements.txt
```

### 2️⃣ Start Server
```bash
python3 -m app.ui_server
```

### 3️⃣ Open Browser

**Local:** http://127.0.0.1:5000

**Codespaces:** Click "Ports" tab → Port 5000 → Globe icon 🌐

---

## How to Use

1. **Paste Redfin URLs** (1-5 properties, one per line)
2. **Click "Analyze Properties"**
3. **Wait 30-60 seconds**
4. **Review the report:**
   - Deal metrics (purchase, exit, ROI)
   - Lot size & property details
   - Permit timeline & team
   - AI-generated analysis

---

## Test Properties

Copy/paste these to try it out:

```
https://www.redfin.com/CA/Los-Angeles/7841-Stewart-Ave-90045/home/6618580
https://www.redfin.com/CA/Los-Angeles/3024-Midvale-Ave-90034/home/6752669
```

---

## What You'll See

### 📊 Deal Metrics
- Purchase: $1,358,000 on Jul 11, 2022
- Exit: $2,950,000 on Oct 15, 2023
- Spread: $1,592,000
- ROI: 117.2%
- Hold: 487 days
- Lot: 6,001 SF (0.14 acres)

### 🏗️ Permit Summary
- Total: 3 permits
- Building Permit: NEW 2-STORY SFD 3,890 SF
- Timeline:
  - Plans submitted: 9/1/2022
  - Approved: 12/1/2022 (91 days)
  - Completed: 9/8/2023 (281 days)
- Contractor: Owner Builder
- Engineer: Jesus Eduardo Carrillo (NA77737)

### 📝 AI Analysis
- Deal snapshot & value-add strategy
- Construction timeline analysis
- Team assessment
- Market context

---

## How It Works (Simple)

```
Your Browser
    ↓
Flask Server (ui_server.py)
    ↓
Orchestrator coordinates:
    ├─→ Redfin Scraper → property details, sale history
    ├─→ LADBS Scraper → building permits (Selenium)
    └─→ CSLB Lookup → contractor licenses
    ↓
AI Summarizer (GPT-4) → written analysis
    ↓
HTML Report displayed in browser
```

---

## Documentation

- 📘 **HOW_IT_WORKS.md** - Detailed architecture & data flow diagrams
- 📗 **TESTING_GUIDE.md** - Full testing & troubleshooting guide
- 📙 **QUICK_REFERENCE.md** - Command cheat sheet

---

## Common Issues

**🔴 "Failed to start Chrome driver"**
- Install Chrome: `sudo apt-get install google-chrome-stable`
- Install ChromeDriver matching your Chrome version

**🔴 LADBS permits not showing**
- Selenium/ChromeDriver required
- Check: `which chromedriver`

**🔴 AI summary blank**
- Set OpenAI API key in `.env`:
  ```
  OPENAI_API_KEY=sk-your-key-here
  ```

---

## Project Structure

```
comp-intel/
├── app/
│   ├── ui_server.py         # Flask web server
│   ├── orchestrator.py      # Coordinates scrapers
│   ├── redfin_scraper.py    # Redfin HTML parser
│   ├── ladbs_scraper.py     # LADBS Selenium scraper
│   ├── cslb_lookup.py       # License validation
│   └── ai_summarizer.py     # GPT-4 analysis
├── templates/
│   └── comp_intel.html      # Report template
├── data/
│   ├── raw/                 # Saved HTML (debugging)
│   └── logs/                # Error logs
└── requirements.txt         # Dependencies
```

---

## Next Steps

1. **Read HOW_IT_WORKS.md** - Understand the architecture
2. **Test with sample URLs** - See it in action
3. **Review generated reports** - Learn the output format
4. **Try your own properties** - Analyze real deals

---

**Ready?** Run: `python3 -m app.ui_server`

Then open: http://127.0.0.1:5000

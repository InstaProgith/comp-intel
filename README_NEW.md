# Real Estate Development Intelligence Tool (BLDGBIT)

A comprehensive Flask-based web application for analyzing single-family home development projects in Los Angeles by combining data from multiple sources:

- **Redfin** - Property listings, sale history, and market data
- **LADBS** (LA Department of Building and Safety) - Construction permits and timeline
- **CSLB** (California State License Board) - Contractor licensing information

## 🎯 What It Does

This tool generates detailed development analysis reports for residential properties, including:

- **Property Snapshot** - Address, specs (beds/baths/SF), lot size, year built, sale status
- **Transaction Analysis** - Purchase price, exit price, hold period, spread, ROI
- **Development Timeline** - Construction stages from permits to completion
- **Construction Summary** - Existing SF, added SF, scope level (light/medium/heavy)
- **Cost Model** - Estimated construction costs using industry-standard rates
- **Permit Overview** - All building, demolition, MEP, and other permits
- **Team** - General contractor, architect, engineer with license info
- **Data Quality Notes** - Flags and caveats about the analysis

## 📋 Quick Start

### Prerequisites
- Python 3.8+
- Git
- OpenAI API key (for AI summaries - optional)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/InstaProgith/comp-intel.git
   cd comp-intel
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment** (optional - for AI features)
   ```bash
   echo "OPENAI_API_KEY=your-key-here" > .env
   ```

5. **Run the application**
   ```bash
   python -m app.ui_server
   ```

6. **Open in browser**
   - Navigate to `http://localhost:5555`

## 🚀 Usage

### Single Property Analysis

1. Go to the home page
2. Paste a Redfin URL (e.g., `https://www.redfin.com/CA/Los-Angeles/...`)
3. Click **"Run Analysis"** for standard report or **"Run Analysis AI"** for AI-enhanced summary
4. View the generated report with all metrics and data

### Multiple Properties

- Paste multiple Redfin URLs (one per line)
- The tool will analyze each property and generate individual reports
- View search history and "repeat players" (contractors/architects appearing on multiple projects)

### Example URLs

Test the tool with these verified properties:

```
https://www.redfin.com/CA/Culver-City/3440-Cattaraugus-Ave-90232/home/6721247
https://www.redfin.com/CA/Los-Angeles/540-N-Gardner-St-90036/home/198348544
https://www.redfin.com/CA/Los-Angeles/12811-Rubens-Ave-90066/home/6731989
```

## 📂 Project Structure

```
comp-intel/
├── app/
│   ├── __init__.py
│   ├── redfin_scraper.py      # Redfin HTML parsing and data extraction
│   ├── ladbs_scraper.py        # LADBS permit scraping
│   ├── cslb_lookup.py          # Contractor license lookups
│   ├── orchestrator.py         # Main pipeline: combines all data sources
│   ├── ui_server.py            # Flask web server and routes
│   └── ai_summarizer.py        # OpenAI GPT integration
├── templates/
│   ├── comp_intel.html         # Home page with input form
│   ├── report.html             # Single property report
│   └── history.html            # Search history and repeat players
├── static/
│   └── style.css               # Application styles
├── data/
│   └── raw/                    # Cached HTML (gitignored)
├── .env                        # Environment variables (gitignored)
├── .gitignore
├── requirements.txt
├── push_to_github.sh           # Helper script for git operations
├── README.md
└── START_HERE.md               # Detailed developer guide
```

## 🔧 How It Works

### Data Collection Pipeline

1. **Redfin Scraper** (`redfin_scraper.py`)
   - Parses property HTML from Redfin
   - Extracts: address, specs, lot size, sale history, status, price/SF

2. **LADBS Scraper** (`ladbs_scraper.py`)
   - Searches LADBS by address
   - Retrieves all permits for the parcel
   - Parses: permit types, dates, contractors, status

3. **CSLB Lookup** (`cslb_lookup.py`)
   - Validates contractor licenses
   - Retrieves license status and classification

4. **Orchestrator** (`orchestrator.py`)
   - Combines all data sources
   - Computes metrics (ROI, spread, hold period, FAR)
   - Builds timeline from permit dates and sale history
   - Categorizes permits and determines scope level
   - Applies cost model using fixed unit costs
   - Generates final report data structure

### Cost Model

The tool uses industry-standard unit costs:

- **New Construction**: $350/SF
- **Remodel**: $150/SF
- **Addition**: $300/SF
- **Garage**: $200/SF
- **Landscape/Hardscape**: $30,000 (flat)
- **Pool**: $70,000 (if pool permits exist)
- **Soft Costs**: 6% of hard costs
- **Financing**: 10% interest, 15 months, 1 point

### Timeline Stages

- Purchase → Plans Submitted
- Plans Submitted → Approval
- Plans Approved → Construction Start
- Construction Duration
- CofO → Sale
- List → Sold (market time)

## 🛠️ Development

### Testing Changes

```bash
# Activate virtual environment
source .venv/bin/activate

# Run the pipeline for a test property
python3 -c "
from app.orchestrator import run_full_comp_pipeline
result = run_full_comp_pipeline('https://www.redfin.com/CA/Los-Angeles/...')
print(result['property_snapshot'])
"
```

### Code Style

- Use descriptive variable names
- Add docstrings to functions
- Keep functions focused and modular
- Comment complex logic

### Git Workflow

```bash
# Check status
git status

# Add changes
git add .

# Commit
git commit -m "Description of changes"

# Push to GitHub
git push origin main
```

Or use the helper script:
```bash
./push_to_github.sh "Your commit message"
```

## 📊 Data Sources

### Redfin
- Public property listings
- Historical sales data
- Property characteristics
- Market statistics

### LADBS
- Building permits (public records)
- Permit timeline and status
- Contractor information
- Permit descriptions

### CSLB
- Contractor license verification
- License status and classification
- Public business information

## 🔒 Privacy & Legal

- All data collected is from public sources
- No private or confidential information is accessed
- Tool is for research and analysis purposes
- Users must comply with terms of service of data sources

## 🐛 Troubleshooting

### Common Issues

**"Module not found" errors**
- Ensure virtual environment is activated: `source .venv/bin/activate`
- Reinstall dependencies: `pip install -r requirements.txt`

**Scraping errors**
- Check internet connection
- Verify Redfin URL is valid and accessible
- LADBS may be temporarily unavailable (retry later)

**Missing data in reports**
- Some properties may lack permit history
- Older sales may not have complete Redfin history
- Check "Data Notes" section for explanations

**Git push rejected**
- Pull latest changes: `git pull origin main`
- Resolve conflicts if any
- Push again: `git push origin main`

## 📝 License

MIT License - see LICENSE file for details

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📧 Contact

For questions or issues:
- Open an issue on GitHub
- Check existing documentation in START_HERE.md

---

**Note**: This tool is for educational and research purposes. Always verify data from original sources before making investment decisions.

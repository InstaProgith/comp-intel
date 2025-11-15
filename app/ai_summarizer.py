import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("ONE_MIN_API_KEY")
if not API_KEY:
    raise SystemExit("Missing ONE_MIN_API_KEY in .env")

URL = "https://api.1min.ai/api/features"


def summarize_comp(combined_data: dict) -> str:
    """
    Sends the combined Redfin + LADBS + metrics data to 1min.ai
    for a developer-grade comp-intel summary.

    Important: combined_data should already contain only real,
    parsed numbers from Redfin/LADBS; no fabricated prices or
    square footage.
    """

    # Convert JSON to readable text for the prompt
    input_json_text = json.dumps(combined_data, indent=2)

    prompt_text = f"""
You are a comp-intel analyst for a Los Angeles real estate developer.

You will receive a JSON object (below). It contains:
- Redfin / MLS data
- LADBS permit list and permit summaries
- Derived deal metrics (purchase/exit/hold/ROI)
- Project contacts from public records

Your task is to produce a concise but high-value summary that reads like
professional due-diligence for a developer.

Follow these rules exactly:

===========================================================
1) DEAL SNAPSHOT
===========================================================
- Address
- Current configuration (beds, baths, living SF) from listing
- Original configuration from PUBLIC RECORDS (beds, baths, SF, year built)
- How many SF were added or changed (if data allows)
- Purchase price + purchase date (from sale history)
- Current listing price + listing date (or last sale if already sold)
- Hold period in days (purchase → exit, or purchase → today if still held)
- Gross spread (exit/list price - purchase)
- Gross ROI (spread / purchase price)
Only compute these when the numbers exist. If some numbers are missing,
say so instead of guessing.

===========================================================
2) SCOPE OF WORK (PERMITS)
===========================================================
Analyze all LADBS permits in the JSON:
- Identify which are core building/addition permits (look at Type/Sub-Type and work_description)
- Categorize demo, addition, ADU, remodel, new structure, pool, etc.
- State clearly what major work was done in the last 5–10 years.
- Mention any open/active/not-final permits.
- Do NOT just list permits — interpret them for a developer.

===========================================================
3) TEAM (COMPETITOR NETWORK)
===========================================================
For core permits, extract the team:
- General Contractor (flag “Owner-Builder” clearly)
- Architect
- Structural Engineer

If repeated names or firms appear, mention that they are repeat players.

Output structure:
  - GC: …
  - Architect: …
  - Engineer: …
  - Notes: any repeated players or interesting patterns.

===========================================================
4) PERMIT TIMING (DURATIONS)
===========================================================
Using the permit status history and metrics:
- For the main building/addition permit (or closest equivalent):
  - Submitted → Plan Check Approved
  - Plan Check Approved → Issued
  - Issued → Finaled

Provide durations in calendar days when the underlying dates exist.
If final is missing, say “not finaled”.

===========================================================
5) VALUE-ADD SUMMARY
===========================================================
In 2–3 sentences, give the “story”:
- What they bought
- What they built (including any ADUs or major additions)
- How much value was added (directionally)
- How long it took
- What spread they are targeting or achieved

Keep it direct, factual, and developer-focused. Do not invent numbers
that are not present in the JSON.

===========================================================
JSON INPUT (USE THIS DATA ONLY)
===========================================================

{input_json_text}

Now produce the final summary.
"""

    payload = {
        "type": "CHAT_WITH_AI",
        "model": "gpt-4o-mini",
        "promptObject": {
            "prompt": prompt_text,
            "isMixed": False,
            "webSearch": False,
        },
    }

    headers = {"API-KEY": API_KEY, "Content-Type": "application/json"}

    resp = requests.post(URL, headers=headers, data=json.dumps(payload), timeout=120)

    try:
        data = resp.json()
        line = (
            data.get("aiRecord", {})
            .get("aiRecordDetail", {})
            .get("resultObject", [None])[0]
        )
        if isinstance(line, str) and line.strip():
            return line.strip()
        return resp.text
    except Exception:
        return resp.text

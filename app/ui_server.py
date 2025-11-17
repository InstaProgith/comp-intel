# app/ui_server.py

import os
import re
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from flask import Flask, render_template, request

# Always import using the package path
from app.orchestrator import run_full_comp_pipeline, run_multiple


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = Path(BASE_DIR) / "data" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
MAX_URLS = 5  # Stage 6: limit number of Redfin URLs per request

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)


@app.template_test("match")
def jinja_match(value, pattern):
    """
    Used in Jinja as: selectattr('field', 'match', 'regex')
    Returns True if regex `pattern` matches `value`.
    """
    if value is None:
        return False
    try:
        return re.search(pattern, str(value)) is not None
    except re.error:
        return False


@app.route("/", methods=["GET", "POST"])
def comp_intel():
    if request.method == "GET":
        return render_template(
            "comp_intel.html",
            results=None,
            urls_text="",
            year=datetime.now().year,
        )

    urls_text = (request.form.get("urls") or "").strip()
    if not urls_text:
        return render_template(
            "comp_intel.html",
            results=None,
            urls_text="",
            year=datetime.now().year,
        )

    # Stage 6 input cleaning & validation
    raw_lines = [u.strip() for u in urls_text.splitlines() if u.strip()]
    valid_urls = [u for u in raw_lines if u.startswith("https://www.redfin.com/")]

    # Enforce MAX_URLS limit
    if len(valid_urls) > MAX_URLS:
        too_many_result = {
            "address": "Too many URLs",
            "url": "",
            "summary_markdown": f"<p class='error-message'>Please submit at most {MAX_URLS} Redfin URLs at a time.</p>",
            "headline_metrics": None,
            "metrics": {
                "purchase_price": None,
                "purchase_date": None,
                "exit_price": None,
                "exit_date": None,
                "spread": None,
                "roi_pct": None,
                "hold_days": None,
            },
            "current_summary": "—",
            "public_record_summary": "—",
            "lot_summary": "—",
            "permit_summary": "Too many URLs submitted.",
            "permit_count": 0,
            "redfin": {"timeline": []},
            "ladbs": {"permits": []},
            "project_contacts": None,
            "cslb_contractor": None,
        }
        return render_template(
            "comp_intel.html",
            results=[too_many_result],
            urls_text=urls_text,
            year=datetime.now().year,
        )

    # Handle zero valid URLs
    if len(valid_urls) == 0:
        none_result = {
            "address": "No valid Redfin URLs",
            "url": "",
            "summary_markdown": "<p class='error-message'>Please paste at least one Redfin URL that starts with https://www.redfin.com/.</p>",
            "headline_metrics": None,
            "metrics": {
                "purchase_price": None,
                "purchase_date": None,
                "exit_price": None,
                "exit_date": None,
                "spread": None,
                "roi_pct": None,
                "hold_days": None,
            },
            "current_summary": "—",
            "public_record_summary": "—",
            "lot_summary": "—",
            "permit_summary": "No valid Redfin URLs provided.",
            "permit_count": 0,
            "redfin": {"timeline": []},
            "ladbs": {"permits": []},
            "project_contacts": None,
            "cslb_contractor": None,
        }
        return render_template(
            "comp_intel.html",
            results=[none_result],
            urls_text=urls_text,
            year=datetime.now().year,
        )

    results = run_multiple(valid_urls)

    return render_template(
        "comp_intel.html",
        results=results,
        urls_text=urls_text,
        year=datetime.now().year,
    )


if __name__ == "__main__":
    # Run locally at http://127.0.0.1:5000
    app.run(host="127.0.0.1", port=5000, debug=True)

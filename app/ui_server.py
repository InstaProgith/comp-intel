# app/ui_server.py

import os
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


def _is_valid_redfin_url(url: str) -> bool:
    """Validate that URL is a Redfin listing URL."""
    url_lower = url.lower()
    return "redfin.com" in url_lower and "/home/" in url_lower


def _log_error(url: str, error: Exception) -> None:
    """Log error to logs directory with timestamp and URL."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOGS_DIR / f"error_{timestamp}.log"
    
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"Timestamp: {datetime.now().isoformat()}\n")
        f.write(f"URL: {url}\n")
        f.write(f"Error: {str(error)}\n")
        f.write(f"Traceback:\n{traceback.format_exc()}\n")
        f.write("-" * 80 + "\n")


def _build_error_result(url: str, error_message: str) -> Dict[str, Any]:
    """Build a safe error result object matching template schema."""
    return {
        "address": "Error",
        "url": url,
        "summary_markdown": f"<p class='error-message'>{error_message}</p>",
        "current_summary": "—",
        "public_record_summary": "—",
        "lot_summary": "—",
        "permit_summary": "—",
        "permit_count": 0,
        "metrics": {
            "purchase_price": None,
            "purchase_date": None,
            "exit_price": None,
            "exit_date": None,
            "spread": None,
            "roi_pct": None,
            "hold_days": None,
        },
        "redfin": {"timeline": []},
        "ladbs": {"permits": []},
        "cslb_contractor": None,
        "project_contacts": None,
    }


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
            "error": f"Please submit at most {MAX_URLS} Redfin URLs at a time.",
            "summary_markdown": "",
            "headline_metrics": None,
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
            "error": "Please paste at least one Redfin URL that starts with https://www.redfin.com/.",
            "summary_markdown": "",
            "headline_metrics": None,
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

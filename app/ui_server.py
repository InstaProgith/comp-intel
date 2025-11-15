# app/ui_server.py

import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from flask import Flask, render_template, request

# Always import using the package path
from app.orchestrator import run_full_comp_pipeline


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = Path(BASE_DIR) / "data" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

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

    urls = [u.strip() for u in urls_text.splitlines() if u.strip()]
    
    # Validate URL count
    if len(urls) > 10:
        error_result = _build_error_result(
            "Multiple URLs",
            "Too many URLs submitted. Maximum 10 URLs allowed per request."
        )
        return render_template(
            "comp_intel.html",
            results=[error_result],
            urls_text=urls_text,
            year=datetime.now().year,
        )

    results: List[Dict[str, Any]] = []

    for url in urls:
        # Validate Redfin URL format
        if not _is_valid_redfin_url(url):
            results.append(_build_error_result(
                url,
                "Invalid URL format. Please provide a valid Redfin listing URL (e.g., https://www.redfin.com/.../home/...)"
            ))
            continue

        try:
            comp_data = run_full_comp_pipeline(url)
            results.append(comp_data)
        except Exception as e:
            _log_error(url, e)
            # User-friendly error message without stack trace
            results.append(_build_error_result(
                url,
                "An error occurred while processing this property. The issue has been logged for review."
            ))

    return render_template(
        "comp_intel.html",
        results=results,
        urls_text=urls_text,
        year=datetime.now().year,
    )


if __name__ == "__main__":
    # Run locally at http://127.0.0.1:5000
    app.run(host="127.0.0.1", port=5000, debug=True)

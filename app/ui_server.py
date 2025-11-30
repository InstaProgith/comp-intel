# app/ui_server.py

import os
import re
import secrets
from functools import wraps
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from flask import Flask, render_template, request, jsonify, session, redirect, make_response

# Always import using the package path
from app.orchestrator import run_full_comp_pipeline, run_multiple, get_search_log, get_repeat_players


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = Path(BASE_DIR) / "data" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
MAX_URLS = 5  # Stage 6: limit number of Redfin URLs per request

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)

# Set Flask secret key from environment variable with dev fallback
# WARNING: The fallback is only for local development - always set FLASK_SECRET_KEY in production
_flask_secret = os.environ.get("FLASK_SECRET_KEY")
if not _flask_secret:
    import warnings
    warnings.warn(
        "FLASK_SECRET_KEY not set! Using insecure fallback. "
        "Set FLASK_SECRET_KEY environment variable in production.",
        RuntimeWarning
    )
    _flask_secret = "DEV_ONLY_CHANGE_ME"
app.secret_key = _flask_secret


def get_expected_password() -> str:
    """
    Resolve the access password with this precedence:
    1. Environment variable APP_ACCESS_PASSWORD
    2. A text file at the repo root named access_password.txt
    3. As a last resort ONLY for local dev, a hardcoded placeholder
    """
    # 1. Check environment variable first
    env_pw = os.environ.get("APP_ACCESS_PASSWORD")
    if env_pw:
        return env_pw

    # 2. Fallback: read from access_password.txt at repo root
    try:
        pw_file = os.path.join(BASE_DIR, "access_password.txt")
        if os.path.exists(pw_file):
            with open(pw_file, "r", encoding="utf-8") as f:
                pw = f.read().strip()
                if pw:
                    return pw
    except Exception:
        pass

    # 3. Final dev-only fallback
    return "CHANGE_ME_DEV"


def login_required(f):
    """
    Decorator that requires password authentication.
    Shows a login form if not authenticated.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("logged_in"):
            return f(*args, **kwargs)

        if request.method == "POST" and "password" in request.form:
            pw = request.form.get("password", "")
            expected = get_expected_password()
            # Use constant-time comparison to prevent timing attacks
            if pw and secrets.compare_digest(pw, expected):
                session["logged_in"] = True
                return redirect(request.path)

        # Show simple login page
        return make_response("""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>BLDGBIT · Login</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap" rel="stylesheet">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f4f4f5;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .login-card {
      background: #fff;
      padding: 48px 40px;
      border-radius: 16px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.08);
      max-width: 400px;
      width: 100%;
      text-align: center;
    }
    .login-card h2 {
      font-size: 24px;
      font-weight: 800;
      color: #111;
      margin-bottom: 8px;
    }
    .login-card .subtitle {
      font-size: 14px;
      color: #666;
      margin-bottom: 32px;
    }
    .login-card input[type="password"] {
      width: 100%;
      padding: 14px 16px;
      border: 1px solid #ddd;
      border-radius: 10px;
      font-size: 16px;
      margin-bottom: 16px;
      transition: border-color 0.2s;
    }
    .login-card input[type="password"]:focus {
      outline: none;
      border-color: #111;
    }
    .login-card button {
      width: 100%;
      background: #111;
      color: #fff;
      padding: 14px 24px;
      border: none;
      border-radius: 10px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.2s;
    }
    .login-card button:hover {
      background: #333;
    }
  </style>
</head>
<body>
  <div class="login-card">
    <h2>BLDGBIT · Comp Intelligence</h2>
    <p class="subtitle">This tool is restricted. Enter the access password:</p>
    <form method="post">
      <input type="password" name="password" placeholder="Access password" autofocus required />
      <button type="submit">Enter</button>
    </form>
  </div>
</body>
</html>
        """, 200)
    return wrapper


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
@login_required
def comp_intel():
    # Get search history and repeat players for display
    search_log = get_search_log()
    repeat_players = get_repeat_players()
    
    if request.method == "GET":
        return render_template(
            "comp_intel.html",
            results=None,
            urls_text="",
            year=datetime.now().year,
            search_log=search_log,
            repeat_players=repeat_players,
        )

    urls_text = (request.form.get("urls") or "").strip()
    if not urls_text:
        return render_template(
            "comp_intel.html",
            results=None,
            urls_text="",
            year=datetime.now().year,
            search_log=search_log,
            repeat_players=repeat_players,
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
            search_log=search_log,
            repeat_players=repeat_players,
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
            search_log=search_log,
            repeat_players=repeat_players,
        )

    results = run_multiple(valid_urls)
    
    # Refresh search log and repeat players after new results
    search_log = get_search_log()
    repeat_players = get_repeat_players()

    return render_template(
        "comp_intel.html",
        results=results,
        urls_text=urls_text,
        year=datetime.now().year,
        search_log=search_log,
        repeat_players=repeat_players,
    )


@app.route("/history")
@login_required
def history():
    """Dedicated route for viewing search history and repeat players."""
    search_log = get_search_log()
    repeat_players = get_repeat_players()
    return render_template(
        "history.html",
        search_log=search_log,
        repeat_players=repeat_players,
        year=datetime.now().year,
    )


@app.route("/report", methods=["POST"])
@login_required
def single_report():
    """
    Render a clean single-building report.
    This route renders report.html which does NOT include:
    - Input card / textarea / "Run Analysis AI" button
    - Search history table
    - Repeat players block
    
    Used for PDF generation and clean report viewing.
    """
    urls_text = (request.form.get("urls") or "").strip()
    if not urls_text:
        return render_template(
            "report.html",
            r=None,
            year=datetime.now().year,
        )
    
    # Parse URLs - take only the first one for single report
    raw_lines = [u.strip() for u in urls_text.splitlines() if u.strip()]
    valid_urls = [u for u in raw_lines if u.startswith("https://www.redfin.com/")]
    
    if not valid_urls:
        return render_template(
            "report.html",
            r=None,
            year=datetime.now().year,
        )
    
    # Run pipeline for the first URL only
    result = run_full_comp_pipeline(valid_urls[0])
    
    return render_template(
        "report.html",
        r=result,
        year=datetime.now().year,
    )


@app.route("/api/history")
@login_required
def api_history():
    """API endpoint for search history data."""
    search_log = get_search_log()
    repeat_players = get_repeat_players()
    return jsonify({
        "search_log": search_log,
        "repeat_players": repeat_players,
    })


if __name__ == "__main__":
    # Run locally at http://127.0.0.1:5000
    # Debug mode depends on FLASK_DEBUG environment variable
    debug = os.environ.get("FLASK_DEBUG") == "1"
    app.run(host="127.0.0.1", port=5000, debug=debug)

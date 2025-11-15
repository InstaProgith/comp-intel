# app/ui_server.py

import os
from datetime import datetime
from typing import Any, Dict, List

from flask import Flask, render_template, request

# Always import using the package path
from app.orchestrator import run_full_comp_pipeline


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)


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
    results: List[Dict[str, Any]] = []

    for url in urls:
        try:
            comp_data = run_full_comp_pipeline(url)
        except Exception as e:
            comp_data = {
                "address": "Error",
                "url": url,
                "summary_markdown": f"<p>Error processing this URL:<br>{e}</p>",
                "current_summary": None,
                "public_record_summary": None,
                "lot_summary": None,
                "permit_summary": None,
                "permit_count": None,
                "team_summary": None,
            }
        results.append(comp_data)

    return render_template(
        "comp_intel.html",
        results=results,
        urls_text=urls_text,
        year=datetime.now().year,
    )


if __name__ == "__main__":
    # Run locally at http://127.0.0.1:5000
    app.run(host="127.0.0.1", port=5000, debug=True)

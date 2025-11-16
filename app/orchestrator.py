from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
from datetime import datetime
import argparse
import json
import re

# Try package-style imports first, fall back to flat files if needed
try:
    from app.redfin_scraper import get_redfin_data  # type: ignore
    from app.ladbs_scraper import get_ladbs_data  # type: ignore
    from app.ai_summarizer import summarize_comp  # type: ignore
    from app.cslb_lookup import lookup_cslb_license  # type: ignore
except ImportError:
    from redfin_scraper import get_redfin_data  # type: ignore
    from ladbs_scraper import get_ladbs_data  # type: ignore
    from ai_summarizer import summarize_comp  # type: ignore
    from cslb_lookup import lookup_cslb_license  # type: ignore

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SUMMARIES_DIR = DATA_DIR / "summaries"
SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)


def _pick_purchase_and_exit(
    timeline: List[Dict[str, Any]]
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Pick purchase and exit events from timeline.
    
    CRITICAL RULE: Only SOLD events count as purchase or exit.
    - Listing events are NOT purchases.
    - Listing events are NOT exits.
    - If there are no sold events, return (None, None).
    
    Returns: (purchase_event, exit_event)
      - purchase_event: first sold event or None
      - exit_event: last sold event or None
    """
    if not timeline:
        return None, None

    try:
        timeline = sorted(timeline, key=lambda e: e.get("date") or "")
    except Exception:
        pass

    # ONLY sold events count as purchase/exit
    sold_events = [e for e in timeline if e.get("event") == "sold"]

    if not sold_events:
        return None, None

    purchase = sold_events[0]
    exit_event = sold_events[-1] if len(sold_events) > 1 else None

    return purchase, exit_event


def _fmt_money(val: Optional[int]) -> str:
    if val is None:
        return "—"
    try:
        return f"${val:,.0f}"
    except Exception:
        return "—"


def _build_headline_metrics(redfin: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build headline metrics from Redfin timeline.
    
    CRITICAL ANTI-HALLUCINATION RULES:
    - Purchase and exit MUST be actual SOLD events only.
    - If there are no sold events (e.g., active listing only):
        ALL metrics return None (purchase, exit, spread, ROI, hold).
    - Listing prices are NOT used as purchase or exit prices.
    - list_price field is separate and displayed only in the listing UI slot.
    """
    timeline: List[Dict[str, Any]] = redfin.get("timeline") or []
    purchase, exit_event = _pick_purchase_and_exit(timeline)

    purchase_price = purchase.get("price") if purchase else None
    purchase_date = purchase.get("date") if purchase else None
    exit_price = exit_event.get("price") if exit_event else None
    exit_date = exit_event.get("date") if exit_event else None

    spread = None
    roi_pct = None
    hold_days = None

    if purchase_price is not None and exit_price is not None:
        spread = exit_price - purchase_price
        if purchase_price > 0:
            roi_pct = round(100.0 * spread / purchase_price, 2)

    if purchase_date and exit_date:
        try:
            d0 = datetime.fromisoformat(purchase_date)
            d1 = datetime.fromisoformat(exit_date)
            hold_days = (d1 - d0).days
        except Exception:
            hold_days = None

    # Include list_price separately (NOT as exit price)
    list_price = redfin.get("list_price")

    return {
        "purchase_price": purchase_price,
        "purchase_date": purchase_date,
        "exit_price": exit_price,
        "exit_date": exit_date,
        "spread": spread,
        "roi_pct": roi_pct,
        "hold_days": hold_days,
        "list_price": list_price,  # current listing price (separate from exit)
    }


def _extract_basic_project_contacts(ladbs: Dict[str, Any]) -> Dict[str, Any]:
    permits = ladbs.get("permits") or []
    if not permits:
        return {}

    contractor_text: Optional[str] = None
    for p in permits:
        info = (p.get("Contractor_Info") or "").strip()
        if info and info.upper() != "N/A":
            contractor_text = info
            break

    if not contractor_text:
        return {}

    name = contractor_text
    if ":" in contractor_text:
        name = contractor_text.split(":", 1)[1].strip()

    lic_match = re.search(r"\b(\d{6,8})\b", contractor_text)
    lic = lic_match.group(1) if lic_match else None

    contractor_obj: Dict[str, Any] = {
        "raw": contractor_text,
        "business_name": name,
    }
    if lic:
        contractor_obj["license"] = lic

    return {"contractor": contractor_obj}


def run_full_comp_pipeline(url: str) -> Dict[str, Any]:
    print(f"[INFO] Running comp-intel pipeline for: {url}")
    
    LOGS_DIR = DATA_DIR / "logs"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Fetch Redfin data with error handling
    redfin_data: Dict[str, Any] = {}
    try:
        redfin_data = get_redfin_data(url)
        print("[INFO] Redfin data fetched.")
    except Exception as e:
        print(f"[ERROR] Redfin fetch failed: {e}")
        _log_failure(LOGS_DIR, url, "redfin", e)
        redfin_data = {
            "source": "redfin_error",
            "address": "Unknown (Redfin fetch failed)",
            "timeline": [],
            "tax": {},
            "current_summary": "—",
            "public_record_summary": "—",
            "lot_summary": "—",
        }

    # Validate redfin_data has minimal required structure
    if not isinstance(redfin_data, dict):
        redfin_data = {"source": "redfin_invalid", "timeline": [], "tax": {}}

    apn = None
    tax = redfin_data.get("tax") or {}
    if isinstance(tax, dict):
        apn = tax.get("apn")

    address = redfin_data.get("address")

    # Fetch LADBS data with error handling
    ladbs_data: Dict[str, Any] = {}
    try:
        ladbs_data = get_ladbs_data(apn=apn, address=address, redfin_url=url)
        print("[INFO] LADBS data fetched.")
    except Exception as e:
        print(f"[ERROR] LADBS fetch failed: {e}")
        _log_failure(LOGS_DIR, url, "ladbs", e)
        ladbs_data = {
            "source": "ladbs_error",
            "permits": [],
            "note": "LADBS data unavailable due to error.",
        }

    # Validate ladbs_data has minimal required structure
    if not isinstance(ladbs_data, dict):
        ladbs_data = {"source": "ladbs_invalid", "permits": [], "note": "Invalid LADBS data."}
    if "permits" not in ladbs_data:
        ladbs_data["permits"] = []

    metrics = _build_headline_metrics(redfin_data)
    project_contacts = _extract_basic_project_contacts(ladbs_data)

    # CSLB lookup for primary contractor
    cslb_contractor = None
    contractor_info = project_contacts.get("contractor") if project_contacts else None
    if contractor_info and contractor_info.get("license"):
        license_num = contractor_info["license"]
        print(f"[INFO] Looking up CSLB license: {license_num}")
        try:
            cslb_contractor = lookup_cslb_license(license_num)
            if cslb_contractor:
                print(f"[INFO] CSLB data found: {cslb_contractor.get('business_name')}")
            else:
                print(f"[INFO] No CSLB data found for license: {license_num}")
        except Exception as e:
            print(f"[WARN] CSLB lookup failed: {e}")
            _log_failure(LOGS_DIR, url, "cslb", e)

    combined: Dict[str, Any] = {
        "url": url,
        "address": redfin_data.get("address", "Unknown address"),
        "headline_metrics": metrics,
        "metrics": metrics,               # alias so template can use r.metrics.*
        "current_summary": redfin_data.get("current_summary", "—"),
        "public_record_summary": redfin_data.get("public_record_summary", "—"),
        "lot_summary": redfin_data.get("lot_summary", "—"),
        "permit_summary": ladbs_data.get("note", "—"),
        "permit_count": len(ladbs_data.get("permits") or []),
        "ladbs": ladbs_data,
        "redfin": redfin_data,
        "project_contacts": project_contacts or None,
        "cslb_contractor": cslb_contractor,
    }

    try:
        combined["summary_markdown"] = summarize_comp(combined)
    except Exception as e:
        print(f"[WARN] summarize_comp failed: {e}")
        _log_failure(LOGS_DIR, url, "summarizer", e)
        combined["summary_markdown"] = (
            "Summary unavailable due to an error in the AI summarizer. "
            "Raw Redfin and LADBS data are still shown above."
        )

    now_tag = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = SUMMARIES_DIR / f"comp_{now_tag}.json"
    try:
        out_path.write_text(json.dumps(combined, indent=2, default=str), encoding="utf-8")
        print(f"[INFO] Saved combined output to {out_path}")
    except Exception as e:
        print(f"[WARN] Failed to save combined JSON: {e}")

    return combined


def _log_failure(logs_dir: Path, url: str, component: str, error: Exception) -> None:
    """Log component failures to logs directory."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"{component}_error_{timestamp}.log"
    
    try:
        import traceback
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            f.write(f"URL: {url}\n")
            f.write(f"Component: {component}\n")
            f.write(f"Error: {str(error)}\n")
            f.write(f"Traceback:\n{traceback.format_exc()}\n")
            f.write("-" * 80 + "\n")
    except Exception as log_error:
        print(f"[ERROR] Failed to write error log: {log_error}")




def run_multiple(urls: List[str]) -> List[Dict[str, Any]]:
    """Run the comp pipeline for multiple URLs with per-URL error isolation."""
    results: List[Dict[str, Any]] = []
    for url in urls:
        try:
            results.append(run_full_comp_pipeline(url))
        except Exception as exc:
            results.append({
                "address": "Error processing property",
                "url": url,
                "summary_markdown": "<p class='error-message'>An error occurred…</p>",
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
                "permit_summary": "—",
                "permit_count": 0,
                "redfin": {"timeline": []},
                "ladbs": {"permits": []},
                "project_contacts": None,
                "cslb_contractor": None,
            })
            # continue to next URL without raising
    return results

def orchestrate(url: str) -> None:
    data = run_full_comp_pipeline(url)
    print("---")
    print(f"Address: {data.get('address')}")
    hm = data.get("headline_metrics") or {}
    print(f"Purchase: {_fmt_money(hm.get('purchase_price'))} on {hm.get('purchase_date')}")
    print(f"Exit/Current: {_fmt_money(hm.get('exit_price'))} on {hm.get('exit_date')}")
    print(f"Spread: {_fmt_money(hm.get('spread'))}  ROI: {hm.get('roi_pct')}%  Hold: {hm.get('hold_days')} days")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run comp-intel pipeline for a single Redfin URL")
    parser.add_argument("--url", required=True, help="Redfin listing URL")
    args = parser.parse_args()
    orchestrate(args.url)


if __name__ == "__main__":
    main()

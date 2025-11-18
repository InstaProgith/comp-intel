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


def _parse_permit_timeline(permits: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Extract key permit timeline milestones from LADBS permits.
    
    Returns:
        - plans_submitted_date: earliest permit application date
        - plans_approved_date: earliest plan check approval date
        - construction_completed_date: earliest finaled/CO date
        - main_permit: the core building permit dict
    """
    if not permits:
        return {}
    
    # Find building permits (not electrical/mechanical/plumbing)
    building_permits = []
    for p in permits:
        permit_type = (p.get("permit_type") or p.get("Type") or "").upper()
        if any(keyword in permit_type for keyword in ["BLDG", "BUILDING", "ADDITION", "NEW"]):
            building_permits.append(p)
    
    if not building_permits:
        building_permits = permits  # fallback to all permits
    
    main_permit = building_permits[0] if building_permits else None
    
    # Extract dates from status history
    plans_submitted = None
    plans_approved = None
    construction_completed = None
    
    for permit in building_permits:
        status_history = permit.get("status_history") or permit.get("raw_details", {}).get("status_history") or []
        
        for event in status_history:
            event_name = (event.get("event") or "").upper()
            date_str = event.get("date") or ""
            
            if not date_str:
                continue
                
            try:
                # Parse date - could be "MM/DD/YYYY" or other formats
                if "/" in date_str:
                    event_date = datetime.strptime(date_str, "%m/%d/%Y")
                else:
                    event_date = datetime.fromisoformat(date_str)
                
                # Plans submitted (application event)
                if "APPLICATION" in event_name or "SUBMIT" in event_name:
                    if not plans_submitted or event_date < plans_submitted:
                        plans_submitted = event_date
                
                # Plans approved (plan check approved)
                if "PLAN CHECK APPROV" in event_name or "PC APPROV" in event_name:
                    if not plans_approved or event_date < plans_approved:
                        plans_approved = event_date
                
                # Construction completed (finaled/CO)
                if "FINAL" in event_name or "CERTIFICATE OF OCCUPANCY" in event_name:
                    if not construction_completed or event_date < construction_completed:
                        construction_completed = event_date
            except Exception:
                continue
    
    return {
        "main_permit": main_permit,
        "plans_submitted_date": plans_submitted.date().isoformat() if plans_submitted else None,
        "plans_approved_date": plans_approved.date().isoformat() if plans_approved else None,
        "construction_completed_date": construction_completed.date().isoformat() if construction_completed else None,
    }


def _calculate_project_durations(purchase_date: Optional[str], permit_timeline: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate durations between project milestones.
    
    Returns dict with:
        - days_to_submit: purchase → plans submitted
        - days_to_approve: plans submitted → approved
        - days_to_complete: plans approved → construction completed
        - total_project_days: purchase → construction completed
    """
    if not purchase_date:
        return {}
    
    try:
        purchase_dt = datetime.fromisoformat(purchase_date)
    except Exception:
        return {}
    
    submitted_str = permit_timeline.get("plans_submitted_date")
    approved_str = permit_timeline.get("plans_approved_date")
    completed_str = permit_timeline.get("construction_completed_date")
    
    durations = {}
    
    if submitted_str:
        try:
            submitted_dt = datetime.fromisoformat(submitted_str)
            durations["days_to_submit"] = (submitted_dt - purchase_dt).days
        except Exception:
            pass
    
    if submitted_str and approved_str:
        try:
            submitted_dt = datetime.fromisoformat(submitted_str)
            approved_dt = datetime.fromisoformat(approved_str)
            durations["days_to_approve"] = (approved_dt - submitted_dt).days
        except Exception:
            pass
    
    if approved_str and completed_str:
        try:
            approved_dt = datetime.fromisoformat(approved_str)
            completed_dt = datetime.fromisoformat(completed_str)
            durations["days_to_complete"] = (completed_dt - approved_dt).days
        except Exception:
            pass
    
    if completed_str:
        try:
            completed_dt = datetime.fromisoformat(completed_str)
            durations["total_project_days"] = (completed_dt - purchase_dt).days
        except Exception:
            pass
    
    return durations


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
    
    # Calculate SF changes (original vs new)
    original_sf = None
    new_sf = None
    sf_added = None
    sf_pct_change = None
    
    public_records = redfin.get("public_records") or {}
    original_sf = public_records.get("building_sf")
    new_sf = redfin.get("building_sf") or redfin.get("listing_building_sf")
    
    if original_sf and new_sf and original_sf != new_sf:
        sf_added = new_sf - original_sf
        if original_sf > 0:
            sf_pct_change = round(100.0 * sf_added / original_sf, 1)

    return {
        "purchase_price": purchase_price,
        "purchase_date": purchase_date,
        "exit_price": exit_price,
        "exit_date": exit_date,
        "spread": spread,
        "roi_pct": roi_pct,
        "hold_days": hold_days,
        "list_price": list_price,  # current listing price (separate from exit)
        "original_sf": original_sf,
        "new_sf": new_sf,
        "sf_added": sf_added,
        "sf_pct_change": sf_pct_change,
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
    
    # Parse permit timeline
    permits = ladbs_data.get("permits") or []
    permit_timeline = _parse_permit_timeline(permits)
    
    # Calculate project durations
    purchase_date = metrics.get("purchase_date")
    project_durations = _calculate_project_durations(purchase_date, permit_timeline)

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
        "permit_timeline": permit_timeline,
        "project_durations": project_durations,
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

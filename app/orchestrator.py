from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
from datetime import datetime
import argparse
import json
import re
import threading

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

# ----- SEARCH HISTORY SYSTEM -----
# Thread-safe in-memory + disk-backed search log
_search_log_lock = threading.Lock()
_search_log: List[Dict[str, Any]] = []
SEARCH_LOG_PATH = DATA_DIR / "search_log.json"


def _load_search_log() -> None:
    """Load search log from disk on startup."""
    global _search_log
    if SEARCH_LOG_PATH.exists():
        try:
            with open(SEARCH_LOG_PATH, "r", encoding="utf-8") as f:
                _search_log = json.load(f)
        except Exception:
            _search_log = []


def _save_search_log() -> None:
    """Persist search log to disk."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(SEARCH_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(_search_log, f, indent=2, default=str)
    except Exception as e:
        print(f"[WARN] Failed to save search log: {e}")


def append_to_search_log(entry: Dict[str, Any]) -> None:
    """Thread-safe append to search log with persistence."""
    with _search_log_lock:
        _search_log.append(entry)
        _save_search_log()


def get_search_log() -> List[Dict[str, Any]]:
    """Get a copy of the current search log."""
    with _search_log_lock:
        return list(_search_log)


def get_repeat_players() -> Dict[str, Any]:
    """
    Compute repeat player stats from search log.
    Returns dict with top GCs, architects, engineers by count with addresses.
    """
    with _search_log_lock:
        gc_map: Dict[str, List[str]] = {}
        arch_map: Dict[str, List[str]] = {}
        eng_map: Dict[str, List[str]] = {}

        for entry in _search_log:
            addr = entry.get("address", "Unknown")
            gc = entry.get("primary_gc_name")
            arch = entry.get("primary_architect_name")
            eng = entry.get("primary_engineer_name")

            if _is_valid_name(gc):
                gc_map.setdefault(gc, []).append(addr)
            if _is_valid_name(arch):
                arch_map.setdefault(arch, []).append(addr)
            if _is_valid_name(eng):
                eng_map.setdefault(eng, []).append(addr)

        def _top_n(m: Dict[str, List[str]], n: int = 10) -> List[Dict[str, Any]]:
            sorted_items = sorted(m.items(), key=lambda x: len(x[1]), reverse=True)[:n]
            return [{"name": k, "count": len(v), "addresses": v} for k, v in sorted_items]

        return {
            "top_gcs": _top_n(gc_map),
            "top_architects": _top_n(arch_map),
            "top_engineers": _top_n(eng_map),
        }


def _is_valid_name(name: Optional[str]) -> bool:
    """Check if a name is valid (not empty, not N/A, not blank)."""
    if not name:
        return False
    stripped = name.strip()
    if not stripped:
        return False
    # Common invalid/placeholder values
    invalid_values = {"N/A", "NA", "NONE", "UNKNOWN", "-", "--", ""}
    return stripped.upper() not in invalid_values


# Load search log on module import
_load_search_log()


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
    spread_per_day = None

    if purchase_price is not None and exit_price is not None:
        spread = exit_price - purchase_price
        if purchase_price > 0:
            roi_pct = round(100.0 * spread / purchase_price, 2)

    if purchase_date and exit_date:
        try:
            d0 = datetime.fromisoformat(purchase_date)
            d1 = datetime.fromisoformat(exit_date)
            hold_days = (d1 - d0).days
            # Calculate spread per day
            if hold_days and hold_days > 0 and spread is not None:
                spread_per_day = round(spread / hold_days, 2)
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

    # Land SF and FAR calculations
    land_sf = public_records.get("lot_sf") or redfin.get("lot_sf")
    building_sf_before = original_sf
    building_sf_after = new_sf
    far_before = None
    far_after = None

    if land_sf and land_sf > 0:
        if building_sf_before:
            far_before = round(building_sf_before / land_sf, 2)
        if building_sf_after:
            far_after = round(building_sf_after / land_sf, 2)

    # $/SF calculations
    purchase_psf = None
    exit_psf = None
    if purchase_price and building_sf_before and building_sf_before > 0:
        purchase_psf = round(purchase_price / building_sf_before, 2)
    if exit_price and building_sf_after and building_sf_after > 0:
        exit_psf = round(exit_price / building_sf_after, 2)
    elif exit_price and building_sf_before and building_sf_before > 0:
        exit_psf = round(exit_price / building_sf_before, 2)
    # If no exit price, try list price for $/SF
    list_psf = None
    if list_price and building_sf_after and building_sf_after > 0:
        list_psf = round(list_price / building_sf_after, 2)
    elif list_price and building_sf_before and building_sf_before > 0:
        list_psf = round(list_price / building_sf_before, 2)

    return {
        "purchase_price": purchase_price,
        "purchase_date": purchase_date,
        "exit_price": exit_price,
        "exit_date": exit_date,
        "spread": spread,
        "roi_pct": roi_pct,
        "hold_days": hold_days,
        "spread_per_day": spread_per_day,
        "list_price": list_price,  # current listing price (separate from exit)
        "original_sf": original_sf,
        "new_sf": new_sf,
        "sf_added": sf_added,
        "sf_pct_change": sf_pct_change,
        # Land and FAR
        "land_sf": land_sf,
        "building_sf_before": building_sf_before,
        "building_sf_after": building_sf_after,
        "far_before": far_before,
        "far_after": far_after,
        # $/SF metrics
        "purchase_psf": purchase_psf,
        "exit_psf": exit_psf,
        "list_psf": list_psf,
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


def _categorize_permits(permits: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Categorize permits into Building, Demo, MEP, Other.
    Also classify scope level based on permit patterns.
    
    Returns:
        - building_count: count of building/addition permits
        - demo_count: count of demolition permits
        - mep_count: count of mechanical/electrical/plumbing permits
        - other_count: count of other permits
        - scope_level: 'LIGHT', 'MEDIUM', or 'HEAVY'
        - scope_details: explanation of classification
    """
    if not permits:
        return {
            "building_count": 0,
            "demo_count": 0,
            "mep_count": 0,
            "other_count": 0,
            "scope_level": "UNKNOWN",
            "scope_details": "No permits found",
        }

    building_count = 0
    demo_count = 0
    mep_count = 0
    other_count = 0
    
    has_adu = False
    has_new_structure = False
    has_addition = False
    has_major_remodel = False
    total_permits = len(permits)

    for p in permits:
        permit_type = (p.get("permit_type") or p.get("Type") or "").upper()
        work_desc = (p.get("Work_Description") or p.get("work_description") or "").upper()
        sub_type = (p.get("sub_type") or "").upper()
        
        combined = f"{permit_type} {work_desc} {sub_type}"
        
        # Classify permit
        if any(kw in combined for kw in ["DEMO", "DEMOLITION"]):
            demo_count += 1
        elif any(kw in combined for kw in ["ELECTRICAL", "PLUMBING", "MECHANICAL", "HVAC"]):
            mep_count += 1
        elif any(kw in combined for kw in ["BLDG", "BUILDING", "ADDITION", "NEW", "CONSTRUCT", "ADU", "REMODEL"]):
            building_count += 1
            # Check for scope indicators
            if "ADU" in combined or "ACCESSORY" in combined:
                has_adu = True
            if "NEW" in combined or "NEW CONSTRUCTION" in combined:
                has_new_structure = True
            if "ADDITION" in combined:
                has_addition = True
            if "MAJOR" in combined or "SUBSTANTIAL" in combined or "REMODEL" in combined:
                has_major_remodel = True
        else:
            other_count += 1

    # Classify scope level
    scope_level = "LIGHT"
    scope_details = "Cosmetic or minor work"
    
    if has_new_structure or has_adu or building_count >= 3:
        scope_level = "HEAVY"
        details = []
        if has_new_structure:
            details.append("new structure")
        if has_adu:
            details.append("ADU")
        if building_count >= 3:
            details.append(f"{building_count} building permits")
        scope_details = "Major: " + ", ".join(details)
    elif has_addition or has_major_remodel or building_count >= 2 or mep_count >= 3:
        scope_level = "MEDIUM"
        details = []
        if has_addition:
            details.append("addition")
        if has_major_remodel:
            details.append("major remodel")
        if mep_count >= 3:
            details.append(f"{mep_count} MEP permits")
        scope_details = "Moderate: " + ", ".join(details) if details else "Moderate work"
    elif total_permits <= 2 and building_count == 0:
        scope_level = "LIGHT"
        scope_details = "Minor or cosmetic work only"

    return {
        "building_count": building_count,
        "demo_count": demo_count,
        "mep_count": mep_count,
        "other_count": other_count,
        "scope_level": scope_level,
        "scope_details": scope_details,
    }


def _extract_team_network(permits: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Extract full team network from permits.
    Identifies primary GC/Architect/Engineer and also-on-permits participants.
    
    Returns:
        - primary_gc: dict with name, license, cslb_url
        - primary_architect: dict with name, license
        - primary_engineer: dict with name, license
        - other_contractors: list of other contractors on permits
        - other_architects: list of other architects on permits
        - other_engineers: list of other engineers on permits
    """
    if not permits:
        return {
            "primary_gc": None,
            "primary_architect": None,
            "primary_engineer": None,
            "other_contractors": [],
            "other_architects": [],
            "other_engineers": [],
        }

    # Collect all team members with frequency counts
    contractors: Dict[str, Dict[str, Any]] = {}
    architects: Dict[str, Dict[str, Any]] = {}
    engineers: Dict[str, Dict[str, Any]] = {}

    for p in permits:
        # Contractor
        c_name = p.get("contractor")
        c_lic = p.get("contractor_license")
        if _is_valid_name(c_name):
            key = c_name.strip()
            if key not in contractors:
                contractors[key] = {"name": key, "license": c_lic, "count": 0}
            contractors[key]["count"] += 1
            if c_lic and not contractors[key].get("license"):
                contractors[key]["license"] = c_lic

        # Architect
        a_name = p.get("architect")
        a_lic = p.get("architect_license")
        if _is_valid_name(a_name):
            key = a_name.strip()
            if key not in architects:
                architects[key] = {"name": key, "license": a_lic, "count": 0}
            architects[key]["count"] += 1
            if a_lic and not architects[key].get("license"):
                architects[key]["license"] = a_lic

        # Engineer
        e_name = p.get("engineer")
        e_lic = p.get("engineer_license")
        if _is_valid_name(e_name):
            key = e_name.strip()
            if key not in engineers:
                engineers[key] = {"name": key, "license": e_lic, "count": 0}
            engineers[key]["count"] += 1
            if e_lic and not engineers[key].get("license"):
                engineers[key]["license"] = e_lic

    # Sort by count and pick primary + others
    def _pick_primary_and_others(d: Dict[str, Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        if not d:
            return None, []
        sorted_list = sorted(d.values(), key=lambda x: x["count"], reverse=True)
        primary = sorted_list[0] if sorted_list else None
        others = sorted_list[1:] if len(sorted_list) > 1 else []
        return primary, [o for o in others]

    primary_gc, other_contractors = _pick_primary_and_others(contractors)
    primary_architect, other_architects = _pick_primary_and_others(architects)
    primary_engineer, other_engineers = _pick_primary_and_others(engineers)

    # Build CSLB URL for primary GC if license available
    if primary_gc and primary_gc.get("license"):
        lic = primary_gc["license"]
        primary_gc["cslb_url"] = f"https://www2.cslb.ca.gov/OnlineServices/CheckLicenseII/LicenseDetail.aspx?LicNum={lic}"

    return {
        "primary_gc": primary_gc,
        "primary_architect": primary_architect,
        "primary_engineer": primary_engineer,
        "other_contractors": other_contractors,
        "other_architects": other_architects,
        "other_engineers": other_engineers,
    }


def _build_property_snapshot(redfin: Dict[str, Any], metrics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build property snapshot with canonical field names.
    """
    address_full = redfin.get("address", "Unknown address")
    beds = redfin.get("beds") or redfin.get("listing_beds")
    baths = redfin.get("baths") or redfin.get("listing_baths")
    building_sf = metrics.get("building_sf_after") or redfin.get("building_sf")
    lot_sf = metrics.get("land_sf")
    
    # Determine property type from permits or default
    property_type = "Single-Family"  # Default
    
    # Determine status based on timeline
    timeline = redfin.get("timeline") or []
    sold_events = [e for e in timeline if e.get("event") == "sold"]
    list_price = redfin.get("list_price")
    
    status = "Unknown"
    status_date = None
    status_price = None
    
    if sold_events:
        last_sold = sorted(sold_events, key=lambda e: e.get("date") or "")[-1]
        status = "Sold"
        status_date = last_sold.get("date")
        status_price = last_sold.get("price")
    elif list_price:
        status = "Active Listing"
        status_price = list_price
        # Try to find list date from timeline
        listed_events = [e for e in timeline if e.get("event") == "listed"]
        if listed_events:
            last_listed = sorted(listed_events, key=lambda e: e.get("date") or "")[-1]
            status_date = last_listed.get("date")
    
    return {
        "address_full": address_full,
        "beds": beds,
        "baths": baths,
        "building_sf": building_sf,
        "lot_sf": lot_sf,
        "property_type": property_type,
        "status": status,
        "status_date": status_date,
        "status_price": status_price,
    }


def _build_construction_summary(
    redfin: Dict[str, Any], 
    metrics: Dict[str, Any], 
    permit_categories: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Build construction summary with SF logic.
    """
    existing_sf = metrics.get("building_sf_before") or 0
    final_sf = metrics.get("building_sf_after") or metrics.get("building_sf_before") or 0
    added_sf = metrics.get("sf_added") or 0
    lot_sf = metrics.get("land_sf")
    scope_level = permit_categories.get("scope_level", "UNKNOWN")
    
    # If we have no existing SF info but have final SF, treat as new construction
    is_new_construction = False
    if existing_sf == 0 and final_sf > 0:
        is_new_construction = True
        added_sf = final_sf
    
    return {
        "existing_sf": existing_sf if existing_sf > 0 else None,
        "added_sf": added_sf if added_sf > 0 else None,
        "final_sf": final_sf if final_sf > 0 else None,
        "lot_sf": lot_sf,
        "scope_level": scope_level,
        "is_new_construction": is_new_construction,
    }


def _build_cost_model(
    metrics: Dict[str, Any],
    construction_summary: Dict[str, Any],
    permit_categories: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Build cost model using fixed assumptions.
    
    Fixed costs:
    - Full new construction: $350/SF
    - Remodel (existing SF): $150/SF
    - Addition: $300/SF
    - Garage: $200/SF
    - Landscape/hardscape/demo: $30,000 flat
    - Pool: $70,000 flat
    - Soft costs: 6% of hard construction cost
    - Financing: 10% annual, 15 months, 1 point
    """
    purchase_price = metrics.get("purchase_price")
    exit_price = metrics.get("exit_price") or metrics.get("list_price")
    
    existing_sf = construction_summary.get("existing_sf") or 0
    added_sf = construction_summary.get("added_sf") or 0
    final_sf = construction_summary.get("final_sf") or 0
    is_new_construction = construction_summary.get("is_new_construction", False)
    
    # Determine construction type costs
    cost_new_construction = 0
    cost_remodel = 0
    cost_addition = 0
    cost_garage = 0
    remodel_sf = 0
    addition_sf = 0
    new_sf_full = 0
    garage_sf = 0
    
    if is_new_construction:
        # Full new construction
        new_sf_full = final_sf
        cost_new_construction = new_sf_full * 350
    else:
        # Remodel + Addition scenario
        remodel_sf = existing_sf
        cost_remodel = remodel_sf * 150
        
        if added_sf > 0:
            addition_sf = added_sf
            cost_addition = addition_sf * 300
    
    # Check for pool in permit categories
    has_pool = False
    scope_details = permit_categories.get("scope_details", "").upper()
    if "POOL" in scope_details:
        has_pool = True
    
    cost_landscape = 30000
    cost_pool = 70000 if has_pool else 0
    
    hard_cost_total = (
        cost_new_construction + 
        cost_remodel + 
        cost_addition + 
        cost_garage + 
        cost_landscape + 
        cost_pool
    )
    
    soft_costs = round(hard_cost_total * 0.06)
    
    # Simple financing: 10% annual rate, 15 months, 1 point
    # Assume loan is on purchase price or hard cost, whichever is smaller
    loan_base = purchase_price if purchase_price else hard_cost_total
    interest_cost = round(loan_base * 0.10 * (15 / 12)) if loan_base else 0
    points_cost = round(loan_base * 0.01) if loan_base else 0
    financing_cost = interest_cost + points_cost
    
    total_project_cost = None
    estimated_profit = None
    
    if purchase_price:
        total_project_cost = purchase_price + hard_cost_total + soft_costs + financing_cost
        if exit_price:
            estimated_profit = exit_price - total_project_cost
    
    return {
        "remodel_sf": remodel_sf,
        "cost_remodel": cost_remodel,
        "addition_sf": addition_sf,
        "cost_addition": cost_addition,
        "new_sf_full": new_sf_full,
        "cost_new_construction": cost_new_construction,
        "garage_sf": garage_sf,
        "cost_garage": cost_garage,
        "cost_landscape": cost_landscape,
        "has_pool": has_pool,
        "cost_pool": cost_pool,
        "hard_cost_total": hard_cost_total,
        "soft_costs": soft_costs,
        "financing_cost": financing_cost,
        "total_project_cost": total_project_cost,
        "estimated_profit": estimated_profit,
    }


def _build_timeline_summary(
    metrics: Dict[str, Any],
    permit_timeline: Dict[str, Any],
    project_durations: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Build timeline summary with stage durations.
    """
    purchase_date = metrics.get("purchase_date")
    exit_date = metrics.get("exit_date")
    
    plans_submitted_date = permit_timeline.get("plans_submitted_date")
    plans_approved_date = permit_timeline.get("plans_approved_date")
    construction_completed_date = permit_timeline.get("construction_completed_date")
    
    # Calculate total time
    total_days = metrics.get("hold_days")
    total_months = round(total_days / 30.44, 1) if total_days else None
    
    stages = []
    
    # Purchase → Plans Submitted
    if purchase_date and plans_submitted_date:
        days = project_durations.get("days_to_submit")
        if days is not None:
            stages.append({
                "name": "Purchase → Plans Submitted",
                "days": days,
                "start_date": purchase_date,
                "end_date": plans_submitted_date,
            })
    
    # Plans Submitted → Approval
    if plans_submitted_date and plans_approved_date:
        days = project_durations.get("days_to_approve")
        if days is not None:
            stages.append({
                "name": "Plans Submitted → Approval",
                "days": days,
                "start_date": plans_submitted_date,
                "end_date": plans_approved_date,
            })
    
    # Plans Approved → Construction Complete
    if plans_approved_date and construction_completed_date:
        days = project_durations.get("days_to_complete")
        if days is not None:
            stages.append({
                "name": "Construction Duration",
                "days": days,
                "start_date": plans_approved_date,
                "end_date": construction_completed_date,
            })
    
    # CofO → Sale (if both known)
    if construction_completed_date and exit_date:
        try:
            cofo_dt = datetime.fromisoformat(construction_completed_date)
            exit_dt = datetime.fromisoformat(exit_date)
            cofo_to_sale_days = (exit_dt - cofo_dt).days
            if cofo_to_sale_days >= 0:
                stages.append({
                    "name": "CofO → Sale",
                    "days": cofo_to_sale_days,
                    "start_date": construction_completed_date,
                    "end_date": exit_date,
                })
        except Exception:
            pass
    
    return {
        "stages": stages,
        "total_days": total_days,
        "total_months": total_months,
        "purchase_date": purchase_date,
        "exit_date": exit_date,
        "plans_submitted_date": plans_submitted_date,
        "plans_approved_date": plans_approved_date,
        "construction_completed_date": construction_completed_date,
        "cofo_date": construction_completed_date,  # alias
    }


def _build_data_notes(
    metrics: Dict[str, Any],
    property_snapshot: Dict[str, Any],
    permit_timeline: Dict[str, Any],
    redfin_ok: bool,
    ladbs_ok: bool
) -> List[str]:
    """
    Build list of data notes explaining missing/weak data.
    """
    notes = []
    
    if not redfin_ok:
        notes.append("Redfin data unavailable; property details may be incomplete.")
    
    if not ladbs_ok:
        notes.append("LADBS data unavailable; permit history not verified.")
    
    if not metrics.get("land_sf"):
        notes.append("Lot size not found in Redfin/public record; FAR not calculated.")
    
    if not metrics.get("purchase_price"):
        notes.append("Purchase price not found; spread and ROI omitted.")
    
    if not metrics.get("purchase_date"):
        notes.append("Purchase date unknown; timeline durations may be incomplete.")
    
    if not permit_timeline.get("construction_completed_date"):
        notes.append("CofO date not found; construction completion inferred from last inspection or marked as Not Final.")
    
    if not property_snapshot.get("beds"):
        notes.append("Bedroom count not available from listing data.")
    
    if not property_snapshot.get("building_sf"):
        notes.append("Building SF not available from listing data.")
    
    return notes


def _build_links(url: str, team_network: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build links section for report.
    """
    gc_cslb_url = None
    if team_network.get("primary_gc") and team_network["primary_gc"].get("cslb_url"):
        gc_cslb_url = team_network["primary_gc"]["cslb_url"]
    
    # LADBS permit search URL (generic search page)
    ladbs_url = "https://www.ladbsservices2.lacity.org/OnlineServices/OnlineServices/OnlineServices?service=plr"
    
    return {
        "redfin_url": url,
        "ladbs_url": ladbs_url,
        "gc_cslb_url": gc_cslb_url,
    }


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
    cslb_ok = True
    cslb_error = None
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
                cslb_ok = False
                cslb_error = "No data found for license"
        except Exception as e:
            print(f"[WARN] CSLB lookup failed: {e}")
            _log_failure(LOGS_DIR, url, "cslb", e)
            cslb_ok = False
            cslb_error = str(e)

    # Permit categorization and scope level
    permit_categories = _categorize_permits(permits)
    
    # Team network extraction
    team_network = _extract_team_network(permits)

    # Data quality / error state indicators
    redfin_source = redfin_data.get("source", "")
    redfin_ok = not (redfin_source.startswith("redfin_error") or redfin_source == "redfin_invalid" or redfin_source == "redfin_fetch_error")
    redfin_error = None if redfin_ok else "Redfin data unavailable (scrape error or no match)"
    
    ladbs_source = ladbs_data.get("source", "")
    ladbs_ok = not (ladbs_source.startswith("ladbs_stub_") or ladbs_source == "ladbs_error" or ladbs_source == "ladbs_invalid")
    ladbs_error = None if ladbs_ok else ladbs_data.get("note", "LADBS data unavailable")

    # Build new report sections
    property_snapshot = _build_property_snapshot(redfin_data, metrics)
    construction_summary = _build_construction_summary(redfin_data, metrics, permit_categories)
    cost_model = _build_cost_model(metrics, construction_summary, permit_categories)
    timeline_summary = _build_timeline_summary(metrics, permit_timeline, project_durations)
    data_notes = _build_data_notes(metrics, property_snapshot, permit_timeline, redfin_ok, ladbs_ok)
    links = _build_links(url, team_network)

    # Calculate hold_months for display
    hold_days = metrics.get("hold_days")
    hold_months = round(hold_days / 30.44, 1) if hold_days else None

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
        # New fields
        "permit_categories": permit_categories,
        "team_network": team_network,
        # Data quality indicators
        "redfin_ok": redfin_ok,
        "redfin_error": redfin_error,
        "ladbs_ok": ladbs_ok,
        "ladbs_error": ladbs_error,
        "cslb_ok": cslb_ok,
        "cslb_error": cslb_error,
        # NEW REPORT SECTIONS
        "property_snapshot": property_snapshot,
        "construction_summary": construction_summary,
        "cost_model": cost_model,
        "timeline_summary": timeline_summary,
        "data_notes": data_notes,
        "links": links,
        "hold_months": hold_months,
    }

    # Skip AI summarizer - we're removing narrative sections
    combined["summary_markdown"] = None

    now_tag = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = SUMMARIES_DIR / f"comp_{now_tag}.json"
    try:
        out_path.write_text(json.dumps(combined, indent=2, default=str), encoding="utf-8")
        print(f"[INFO] Saved combined output to {out_path}")
    except Exception as e:
        print(f"[WARN] Failed to save combined JSON: {e}")

    # Append to search log for history tracking
    city_zip = _extract_city_zip(redfin_data.get("address", ""))
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "address": redfin_data.get("address", "Unknown"),
        "city_zip": city_zip,
        "purchase_date": metrics.get("purchase_date"),
        "exit_date": metrics.get("exit_date") or metrics.get("list_price") and "current",
        "hold_days": metrics.get("hold_days"),
        "purchase_price": metrics.get("purchase_price"),
        "exit_price": metrics.get("exit_price") or metrics.get("list_price"),
        "spread": metrics.get("spread"),
        "roi_pct": metrics.get("roi_pct"),
        "spread_per_day": metrics.get("spread_per_day"),
        "land_sf": metrics.get("land_sf"),
        "building_sf_before": metrics.get("building_sf_before"),
        "building_sf_after": metrics.get("building_sf_after"),
        "far_before": metrics.get("far_before"),
        "far_after": metrics.get("far_after"),
        "primary_gc_name": team_network.get("primary_gc", {}).get("name") if team_network.get("primary_gc") else None,
        "primary_gc_license": team_network.get("primary_gc", {}).get("license") if team_network.get("primary_gc") else None,
        "primary_architect_name": team_network.get("primary_architect", {}).get("name") if team_network.get("primary_architect") else None,
        "primary_engineer_name": team_network.get("primary_engineer", {}).get("name") if team_network.get("primary_engineer") else None,
        "scope_level": permit_categories.get("scope_level"),
    }
    append_to_search_log(log_entry)

    return combined


def _extract_city_zip(address: str) -> str:
    """Extract city and ZIP from address string."""
    if not address:
        return ""
    # Try to find ZIP code pattern
    zip_match = re.search(r"(\d{5}(?:-\d{4})?)", address)
    zip_code = zip_match.group(1) if zip_match else ""
    # Try to find city (usually before state abbreviation)
    city_match = re.search(r",\s*([^,]+),\s*[A-Z]{2}", address)
    city = city_match.group(1).strip() if city_match else ""
    return f"{city} {zip_code}".strip()


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

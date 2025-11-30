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

# -----------------------------------------------------------------------------
# CENTRALIZED COST MODEL CONSTANTS - Easy to tune in one place
# -----------------------------------------------------------------------------
COST_MODEL = {
    # Construction costs per SF
    "cost_per_sf_new_construction": 350,  # Full new construction
    "cost_per_sf_remodel": 150,            # Remodel existing SF
    "cost_per_sf_addition": 300,           # Addition to existing structure
    "cost_per_sf_garage": 200,             # Garage construction
    "cost_per_sf_adu": 300,                # ADU construction
    
    # Fixed allowances
    "landscape_demo_allowance": 30000,     # Landscape/hardscape/demo flat allowance
    "pool_allowance": 70000,               # Pool installation flat cost
    
    # ADU estimation
    "typical_adu_sf": 1000,                # Typical ADU size for cost estimation when added SF > ADU
    
    # Soft costs and financing
    "soft_cost_pct": 0.06,                 # 6% of hard costs
    "interest_rate_annual": 0.10,          # 10% annual hard money rate
    "hold_months_default": 15,             # Default hold for financing calc
    "loan_points": 0.01,                   # 1 point on loan
}

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
    
    NEW: Dedupe by property - each property counts only once per team member,
    even if analyzed multiple times.
    """
    with _search_log_lock:
        gc_map: Dict[str, set] = {}  # Maps GC name to set of canonical addresses
        arch_map: Dict[str, set] = {}
        eng_map: Dict[str, set] = {}

        for entry in _search_log:
            addr = entry.get("address", "Unknown")
            # Create canonical address key (normalize for deduplication)
            canonical_addr = _canonicalize_address(addr)
            
            gc = entry.get("primary_gc_name")
            arch = entry.get("primary_architect_name")
            eng = entry.get("primary_engineer_name")

            if _is_valid_name(gc):
                if gc not in gc_map:
                    gc_map[gc] = set()
                gc_map[gc].add(canonical_addr)
            if _is_valid_name(arch):
                if arch not in arch_map:
                    arch_map[arch] = set()
                arch_map[arch].add(canonical_addr)
            if _is_valid_name(eng):
                if eng not in eng_map:
                    eng_map[eng] = set()
                eng_map[eng].add(canonical_addr)

        def _top_n(m: Dict[str, set], n: int = 10) -> List[Dict[str, Any]]:
            # Convert sets to sorted lists and sort by count
            sorted_items = sorted(
                [(k, sorted(list(v))) for k, v in m.items()],
                key=lambda x: len(x[1]),
                reverse=True
            )[:n]
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


def _canonicalize_address(address: str) -> str:
    """
    Normalize an address for deduplication.
    Removes extra spaces, converts to uppercase, removes special chars.
    """
    if not address:
        return ""
    # Convert to uppercase
    addr = address.upper()
    # Remove common separators and extra whitespace
    addr = re.sub(r'[,.\s]+', ' ', addr)
    # Remove special characters
    addr = re.sub(r'[^\w\s]', '', addr)
    # Collapse whitespace
    addr = ' '.join(addr.split())
    return addr.strip()


# Load search log on module import
_load_search_log()


def _pick_purchase_and_exit(
    timeline: List[Dict[str, Any]],
    earliest_permit_date: Optional[str] = None
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Pick purchase and exit events from timeline.
    
    NEW RULES (Issue Fix):
    1. EXIT is always the MOST RECENT event:
       - If there's a sold event, use the LAST sale as exit.
       - Otherwise, use the latest list (Active/Pending) as exit.
    2. PURCHASE is only valid if:
       - There is a sale event BEFORE the exit event.
       - The purchase_date is NOT after the earliest LADBS permit date.
       - If there is only one sold event, it is the EXIT (not purchase).
    
    Returns: (purchase_event, exit_event)
      - purchase_event: prior sale event before exit, or None
      - exit_event: most recent sale or listing event
    """
    if not timeline:
        return None, None

    try:
        timeline = sorted(timeline, key=lambda e: e.get("date") or "")
    except Exception:
        pass

    # Find sold events
    sold_events = [e for e in timeline if e.get("event") == "sold"]
    
    # Find listing events (for exit if no sale)
    listing_events = [e for e in timeline if e.get("event") in ("listed", "active", "pending")]
    
    exit_event = None
    purchase_event = None
    
    if sold_events:
        # Sort sold events by date
        sold_events = sorted(sold_events, key=lambda e: e.get("date") or "")
        
        # EXIT is the LAST (most recent) sold event
        exit_event = sold_events[-1]
        
        # PURCHASE is the prior sold event (if exists)
        if len(sold_events) > 1:
            # Take the second-to-last sold event as purchase candidate
            purchase_candidate = sold_events[-2]
            
            # Validate purchase: must be before earliest permit date (if known)
            purchase_date_str = purchase_candidate.get("date")
            is_valid_purchase = True
            
            if earliest_permit_date and purchase_date_str:
                try:
                    purchase_dt = datetime.fromisoformat(purchase_date_str)
                    permit_dt = datetime.fromisoformat(earliest_permit_date)
                    # If purchase is AFTER earliest permit, it's invalid
                    if purchase_dt > permit_dt:
                        is_valid_purchase = False
                except Exception:
                    pass
            
            if is_valid_purchase:
                purchase_event = purchase_candidate
    else:
        # No sold events - use latest listing as exit (no purchase)
        if listing_events:
            listing_events = sorted(listing_events, key=lambda e: e.get("date") or "")
            exit_event = listing_events[-1]
    
    return purchase_event, exit_event


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
        - construction_start_date: earliest permit issued date (construction start)
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
    construction_start = None
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
                
                # Construction start (permit issued)
                if "ISSUED" in event_name or "PERMIT ISSUED" in event_name:
                    if not construction_start or event_date < construction_start:
                        construction_start = event_date
                
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
        "construction_start_date": construction_start.date().isoformat() if construction_start else None,
        "construction_completed_date": construction_completed.date().isoformat() if construction_completed else None,
    }


def _calculate_project_durations(purchase_date: Optional[str], permit_timeline: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate durations between project milestones.
    
    Returns dict with:
        - days_to_submit: purchase → plans submitted
        - days_to_approve: plans submitted → approved
        - days_approval_to_start: plans approved → construction start
        - days_construction: construction start → construction completed
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
    start_str = permit_timeline.get("construction_start_date")
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
    
    if approved_str and start_str:
        try:
            approved_dt = datetime.fromisoformat(approved_str)
            start_dt = datetime.fromisoformat(start_str)
            durations["days_approval_to_start"] = (start_dt - approved_dt).days
        except Exception:
            pass
    
    if start_str and completed_str:
        try:
            start_dt = datetime.fromisoformat(start_str)
            completed_dt = datetime.fromisoformat(completed_str)
            durations["days_construction"] = (completed_dt - start_dt).days
        except Exception:
            pass
    
    if completed_str:
        try:
            completed_dt = datetime.fromisoformat(completed_str)
            durations["total_project_days"] = (completed_dt - purchase_dt).days
        except Exception:
            pass
    
    return durations


def _build_headline_metrics(redfin: Dict[str, Any], earliest_permit_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Build headline metrics from Redfin timeline.
    
    NEW RULES (Issue Fix):
    - EXIT is the most recent event (sale or listing).
    - PURCHASE is only valid if there's a prior sale before exit AND
      the purchase date is not after the earliest permit date.
    - If PURCHASE is unknown, spread/ROI/hold metrics are not computed.
    - list_price is separate from exit_price.
    """
    timeline: List[Dict[str, Any]] = redfin.get("timeline") or []
    purchase, exit_event = _pick_purchase_and_exit(timeline, earliest_permit_date)

    purchase_price = purchase.get("price") if purchase else None
    purchase_date = purchase.get("date") if purchase else None
    
    # Exit event could be a sale or a listing
    exit_price = None
    exit_date = None
    if exit_event:
        exit_price = exit_event.get("price")
        exit_date = exit_event.get("date")

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
    Categorize permits into Building, Demo, MEP, Other with detailed flags.
    
    Returns:
        - building_count: count of building/addition permits
        - demo_count: count of demolition permits
        - mep_count: count of mechanical/electrical/plumbing permits
        - other_count: count of other permits
        - supplement_count: count of supplement/revision permits
        - scope_level: 'LIGHT', 'MEDIUM', or 'HEAVY'
        - scope_details: explanation of classification
        - permit_complexity_score: 'LOW', 'MEDIUM', or 'HIGH'
        - Flags: has_fire_sprinklers, removed_fire_sprinklers, has_pool, 
                 has_grading_or_hillside, has_methane, has_adu, has_new_structure,
                 started_before_final_approval
        - building_permits: list of main building permits
        - mep_permits: list of MEP permits
        - supplement_permits: list of supplements/revisions
        - other_permits: list of other permits (pool, grading, etc.)
    """
    if not permits:
        return {
            "building_count": 0,
            "demo_count": 0,
            "mep_count": 0,
            "other_count": 0,
            "supplement_count": 0,
            "scope_level": "UNKNOWN",
            "scope_details": "No permits found",
            "permit_complexity_score": "UNKNOWN",
            "has_fire_sprinklers": False,
            "removed_fire_sprinklers": False,
            "has_pool": False,
            "has_grading_or_hillside": False,
            "has_methane": False,
            "has_adu": False,
            "has_new_structure": False,
            "started_before_final_approval": False,
            "building_permits": [],
            "mep_permits": [],
            "supplement_permits": [],
            "other_permits": [],
        }

    building_count = 0
    demo_count = 0
    mep_count = 0
    other_count = 0
    supplement_count = 0
    
    # Feature flags
    has_fire_sprinklers = False
    removed_fire_sprinklers = False
    has_pool = False
    has_grading_or_hillside = False
    has_methane = False
    has_adu = False
    has_new_structure = False
    has_addition = False
    has_major_remodel = False
    started_before_final_approval = False
    
    # Permit lists by category
    building_permits: List[Dict[str, Any]] = []
    mep_permits: List[Dict[str, Any]] = []
    supplement_permits: List[Dict[str, Any]] = []
    other_permits_list: List[Dict[str, Any]] = []
    
    total_permits = len(permits)

    for p in permits:
        permit_type = (p.get("permit_type") or p.get("Type") or "").upper()
        work_desc = (p.get("Work_Description") or p.get("work_description") or "").upper()
        sub_type = (p.get("sub_type") or "").upper()
        status = (p.get("Status") or p.get("status") or "").upper()
        
        combined = f"{permit_type} {work_desc} {sub_type}"
        
        # Detect fire sprinklers
        if "SPRINKLER" in combined or "NFPA" in combined or "FIRE SUPPRESSION" in combined:
            has_fire_sprinklers = True
            # Check if sprinklers were removed
            if "REMOV" in combined or "DELET" in combined or "DECOMMISSION" in combined:
                removed_fire_sprinklers = True
        
        # Detect pool
        if "POOL" in combined or "SPA" in combined:
            has_pool = True
        
        # Detect grading/hillside
        if any(kw in combined for kw in ["GRADING", "HILLSIDE", "RETAINING WALL", "EXCAVATION", "SLOPE"]):
            has_grading_or_hillside = True
        
        # Detect methane
        if "METHANE" in combined:
            has_methane = True
        
        # Classify permit
        if any(kw in combined for kw in ["SUPPLEMENT", "REVISION", "REV ", "SUPP"]):
            supplement_count += 1
            supplement_permits.append(p)
        elif any(kw in combined for kw in ["DEMO", "DEMOLITION"]):
            demo_count += 1
            other_permits_list.append(p)
        elif any(kw in combined for kw in ["ELECTRICAL", "PLUMBING", "MECHANICAL", "HVAC"]):
            mep_count += 1
            mep_permits.append(p)
        elif any(kw in combined for kw in ["BLDG", "BUILDING", "ADDITION", "NEW", "CONSTRUCT", "ADU", "REMODEL"]):
            building_count += 1
            building_permits.append(p)
            # Check for scope indicators
            if "ADU" in combined or "ACCESSORY DWELLING" in combined:
                has_adu = True
            if "NEW" in combined and any(kw in combined for kw in ["CONSTRUCT", "STRUCTURE", "SFD", "SFR", "DWELLING"]):
                has_new_structure = True
            if "ADDITION" in combined:
                has_addition = True
            if "MAJOR" in combined or "SUBSTANTIAL" in combined or ("REMODEL" in combined and not "MINOR" in combined):
                has_major_remodel = True
        else:
            other_count += 1
            other_permits_list.append(p)

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

    # Compute permit_complexity_score based on multiple factors
    complexity_score = 0
    if total_permits >= 8:
        complexity_score += 3
    elif total_permits >= 5:
        complexity_score += 2
    elif total_permits >= 3:
        complexity_score += 1
    
    if supplement_count >= 3:
        complexity_score += 2
    elif supplement_count >= 1:
        complexity_score += 1
    
    if has_pool:
        complexity_score += 1
    if has_grading_or_hillside:
        complexity_score += 2
    if has_methane:
        complexity_score += 1
    if has_fire_sprinklers:
        complexity_score += 1
    
    if complexity_score >= 5:
        permit_complexity_score = "HIGH"
    elif complexity_score >= 2:
        permit_complexity_score = "MEDIUM"
    else:
        permit_complexity_score = "LOW"

    return {
        "building_count": building_count,
        "demo_count": demo_count,
        "mep_count": mep_count,
        "other_count": other_count,
        "supplement_count": supplement_count,
        "scope_level": scope_level,
        "scope_details": scope_details,
        "permit_complexity_score": permit_complexity_score,
        "has_fire_sprinklers": has_fire_sprinklers,
        "removed_fire_sprinklers": removed_fire_sprinklers,
        "has_pool": has_pool,
        "has_grading_or_hillside": has_grading_or_hillside,
        "has_methane": has_methane,
        "has_adu": has_adu,
        "has_new_structure": has_new_structure,
        "started_before_final_approval": started_before_final_approval,
        "building_permits": building_permits,
        "mep_permits": mep_permits,
        "supplement_permits": supplement_permits,
        "other_permits": other_permits_list,
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


def _build_property_snapshot(redfin: Dict[str, Any], metrics: Dict[str, Any], permits: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Build property snapshot with canonical field names matching golden test format.
    
    Expected format:
    Line 1: "3440 Cattaraugus Ave, Culver City, CA 90232"
    Line 2: "5 bd / 5.5 ba · 3,595 SF · Lot 5,397 SF · Single-family · Built 2024"
    Line 3: "Sold on Sep 5, 2025 for $3,750,000 (List: $3,988,000) · $1,043 / SF"
    """
    address_full = redfin.get("address", "Unknown address")
    beds = redfin.get("beds") or redfin.get("listing_beds")
    baths = redfin.get("baths") or redfin.get("listing_baths")
    
    # Format beds/baths nicely (remove .0 for whole numbers)
    if beds and beds == int(beds):
        beds = int(beds)
    if baths and baths == int(baths):
        baths = int(baths)
    
    building_sf = redfin.get("building_sf") or metrics.get("building_sf_after")
    lot_sf = redfin.get("lot_sf") or metrics.get("land_sf")
    year_built = redfin.get("year_built")
    
    # Enhanced year built logic: detect if property was substantially rebuilt
    # If there are recent major building permits, use the completion year instead of original year
    if permits and year_built:
        permit_years = []
        for permit in permits:
            # Look for building/new construction permits that have been finaled
            permit_type = (permit.get("permit_type") or permit.get("Type") or "").upper()
            status = (permit.get("status") or permit.get("Status") or "").upper()
            
            if any(keyword in permit_type for keyword in ["BLDG", "BUILDING", "NEW", "ADDITION"]):
                # Check if status contains "FINAL" or "COFO" with a date
                # Format: "CofO Issued on 5/3/2021" or "Finaled on 12/15/2022"
                status_date_match = re.search(r'(?:CofO|Final|Complet).*?(\d{1,2}/\d{1,2}/\d{4})', status, re.I)
                if status_date_match:
                    date_str = status_date_match.group(1)
                    try:
                        parts = date_str.split("/")
                        if len(parts) == 3:
                            permit_year = int(parts[2])
                            permit_years.append(permit_year)
                    except (ValueError, IndexError):
                        pass
                
                # Also check status_history
                status_history = permit.get("status_history") or permit.get("raw_details", {}).get("status_history") or []
                for event in status_history:
                    event_name = (event.get("event") or "").upper()
                    date_str = event.get("date") or ""
                    if any(keyword in event_name for keyword in ["FINAL", "COMPLET", "COFO", "CERTIFICATE"]):
                        try:
                            # Parse date format MM/DD/YYYY
                            if "/" in date_str:
                                parts = date_str.split("/")
                                if len(parts) == 3 and len(parts[2]) == 4:
                                    permit_year = int(parts[2])
                                    permit_years.append(permit_year)
                                    break
                        except (ValueError, IndexError):
                            continue
        
        # If we found permit completion years and they're recent (within last 10 years)
        # and significantly newer than original year built, use the permit year
        if permit_years:
            latest_permit_year = max(permit_years)
            current_year = datetime.now().year
            
            # If permit is recent (within 10 years) and at least 20 years newer than original
            if (current_year - latest_permit_year <= 10) and (latest_permit_year - year_built >= 20):
                year_built = latest_permit_year
    
    # Property type - get from Redfin or default
    property_type = redfin.get("property_type") or "Single-family"
    
    # Get price/SF from Redfin or calculate
    price_per_sf = redfin.get("price_per_sf")
    
    # Determine status based on timeline
    timeline = redfin.get("timeline") or []
    
    # Find the most recent sold event
    sold_events = [e for e in timeline if e.get("event") == "sold"]
    listed_events = [e for e in timeline if e.get("event") == "listed"]
    
    status = "Unknown"
    status_date = None
    status_price = None
    list_price_before_sale = None
    list_date = None
    days_on_market = None
    
    if sold_events:
        # Sort by date and get the most recent sale
        last_sold = sorted(sold_events, key=lambda e: e.get("date") or "")[-1]
        status = "Sold"
        status_date = last_sold.get("date")
        status_price = last_sold.get("price")
        
        # Look for a listing event before this sale (could be the original list price)
        if listed_events and status_date:
            prior_listings = [e for e in listed_events if e.get("date", "") < status_date]
            if prior_listings:
                # Get the most recent listing before sale
                last_list = sorted(prior_listings, key=lambda e: e.get("date") or "")[-1]
                list_price_before_sale = last_list.get("price")
                list_date = last_list.get("date")
                
                # Calculate days on market
                if list_date and status_date:
                    try:
                        list_dt = datetime.fromisoformat(list_date)
                        sold_dt = datetime.fromisoformat(status_date)
                        days_on_market = (sold_dt - list_dt).days
                    except Exception:
                        pass
            elif listed_events:
                # Fallback: use any listing event
                first_list = sorted(listed_events, key=lambda e: e.get("date") or "")[0]
                list_price_before_sale = first_list.get("price")
                list_date = first_list.get("date")
    else:
        # Not sold - check if actively listed
        list_price_redfin = redfin.get("list_price")
        if list_price_redfin:
            status = "Active Listing"
            status_price = list_price_redfin
            # Try to find list date from timeline
            if listed_events:
                last_listed = sorted(listed_events, key=lambda e: e.get("date") or "")[-1]
                status_date = last_listed.get("date")
                list_date = status_date
                
                # Days on market = days since listing
                if list_date:
                    try:
                        list_dt = datetime.fromisoformat(list_date)
                        now_dt = datetime.now()
                        days_on_market = (now_dt - list_dt).days
                    except Exception:
                        pass
        elif listed_events:
            # Has listing events but no current price
            last_listed = sorted(listed_events, key=lambda e: e.get("date") or "")[-1]
            status = "Listed"
            status_date = last_listed.get("date")
            status_price = last_listed.get("price")
            list_date = status_date
    
    # Calculate price per SF if not already available
    if not price_per_sf and status_price and building_sf and building_sf > 0:
        price_per_sf = round(status_price / building_sf)
    
    return {
        "address_full": address_full,
        "beds": beds,
        "baths": baths,
        "building_sf": building_sf,
        "lot_sf": lot_sf,
        "year_built": year_built,
        "property_type": property_type,
        "status": status,
        "status_date": status_date,
        "status_price": status_price,
        "list_price_before_sale": list_price_before_sale,
        "list_date": list_date,
        "price_per_sf": price_per_sf,
        "days_on_market": days_on_market,
        "price_history": timeline,  # Full price history for reference
    }


def _build_construction_summary(
    redfin: Dict[str, Any], 
    metrics: Dict[str, Any], 
    permit_categories: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Build construction summary with SF logic.
    
    NEW RULES (Issue Fix):
    - When project is NEW construction (no meaningful existing SF):
      - existing_sf = 0 (not None/Unknown)
      - is_new_construction = True
      - added_sf = final_sf
    - Display "0 (New Construction)" consistently in all sections.
    """
    existing_sf = metrics.get("building_sf_before") or 0
    final_sf = metrics.get("building_sf_after") or metrics.get("building_sf_before") or 0
    added_sf = metrics.get("sf_added") or 0
    lot_sf = metrics.get("land_sf")
    scope_level = permit_categories.get("scope_level", "UNKNOWN")
    
    # Determine if this is new construction
    is_new_construction = False
    if existing_sf == 0 and final_sf > 0:
        is_new_construction = True
        added_sf = final_sf
        existing_sf = 0  # Explicitly set to 0, not None
    
    return {
        "existing_sf": existing_sf,  # Will be 0 for new construction, not None
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
    Build cost model using centralized COST_MODEL constants.
    
    Uses configurable costs from COST_MODEL dict:
    - Full new construction: $350/SF (default)
    - Remodel (existing SF): $150/SF (default)
    - Addition: $300/SF (default)
    - Garage: $200/SF (default)
    - ADU: $300/SF (default)
    - Landscape/hardscape/demo: $30,000 flat (default)
    - Pool: $70,000 flat (default)
    - Soft costs: 6% of hard construction cost (default)
    - Financing: 10% annual, 15 months hold, 1 point (defaults)
    
    Rules:
    - Only compute total_project_cost and estimated_profit when PURCHASE is known.
    - When purchase is unknown: show construction cost breakdown only.
    """
    purchase_price = metrics.get("purchase_price")
    exit_price = metrics.get("exit_price") or metrics.get("list_price")
    hold_days = metrics.get("hold_days")
    
    existing_sf = construction_summary.get("existing_sf") or 0
    added_sf = construction_summary.get("added_sf") or 0
    final_sf = construction_summary.get("final_sf") or 0
    is_new_construction = construction_summary.get("is_new_construction", False)
    
    # Get cost constants from centralized config
    cost_per_sf_new = COST_MODEL["cost_per_sf_new_construction"]
    cost_per_sf_remodel = COST_MODEL["cost_per_sf_remodel"]
    cost_per_sf_addition = COST_MODEL["cost_per_sf_addition"]
    cost_per_sf_garage = COST_MODEL["cost_per_sf_garage"]
    cost_per_sf_adu = COST_MODEL["cost_per_sf_adu"]
    landscape_allowance = COST_MODEL["landscape_demo_allowance"]
    pool_allowance = COST_MODEL["pool_allowance"]
    soft_cost_pct = COST_MODEL["soft_cost_pct"]
    interest_rate = COST_MODEL["interest_rate_annual"]
    default_hold_months = COST_MODEL["hold_months_default"]
    loan_points_pct = COST_MODEL["loan_points"]
    
    # Determine construction type costs
    cost_new_construction = 0
    cost_remodel = 0
    cost_addition = 0
    cost_garage = 0
    cost_adu = 0
    remodel_sf = 0
    addition_sf = 0
    new_sf_full = 0
    garage_sf = 0
    adu_sf = 0
    
    # Check for ADU in permit categories
    has_adu = permit_categories.get("has_adu", False)
    typical_adu_sf = COST_MODEL["typical_adu_sf"]
    
    if is_new_construction:
        # Full new construction
        new_sf_full = final_sf
        cost_new_construction = new_sf_full * cost_per_sf_new
    else:
        # Remodel + Addition scenario
        remodel_sf = existing_sf
        cost_remodel = remodel_sf * cost_per_sf_remodel
        
        if added_sf > 0:
            # If ADU detected, attribute some SF to ADU
            if has_adu:
                # Use configurable typical ADU size, cap at added_sf
                estimated_adu_sf = min(added_sf, typical_adu_sf)
                adu_sf = estimated_adu_sf
                addition_sf = added_sf - adu_sf
                cost_adu = adu_sf * cost_per_sf_adu
                cost_addition = addition_sf * cost_per_sf_addition
            else:
                addition_sf = added_sf
                cost_addition = addition_sf * cost_per_sf_addition
    
    # Check for pool in permit categories (use new flag)
    has_pool = permit_categories.get("has_pool", False)
    
    cost_landscape = landscape_allowance
    cost_pool = pool_allowance if has_pool else 0
    
    hard_cost_total = (
        cost_new_construction + 
        cost_remodel + 
        cost_addition + 
        cost_garage + 
        cost_adu +
        cost_landscape + 
        cost_pool
    )
    
    soft_costs = round(hard_cost_total * soft_cost_pct)
    
    # Financing cost calculation
    # Use actual hold days if known, otherwise default
    if hold_days and hold_days > 0:
        hold_months = hold_days / 30.44
    else:
        hold_months = default_hold_months
    
    # When purchase is UNKNOWN: compute financing only on construction costs
    # When purchase is KNOWN: compute financing on purchase price
    if purchase_price:
        loan_base = purchase_price
    else:
        # No purchase known - use hard cost total as loan base (construction loan only)
        loan_base = hard_cost_total
    
    interest_cost = round(loan_base * interest_rate * (hold_months / 12)) if loan_base else 0
    points_cost = round(loan_base * loan_points_pct) if loan_base else 0
    financing_cost = interest_cost + points_cost
    
    # CRITICAL: Only compute total_project_cost and estimated_profit when purchase is KNOWN
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
        "adu_sf": adu_sf,
        "cost_adu": cost_adu,
        "cost_landscape": cost_landscape,
        "has_pool": has_pool,
        "cost_pool": cost_pool,
        "hard_cost_total": hard_cost_total,
        "soft_costs": soft_costs,
        "soft_cost_pct": soft_cost_pct,
        "financing_cost": financing_cost,
        "interest_cost": interest_cost,
        "points_cost": points_cost,
        "hold_months_used": hold_months,
        "total_project_cost": total_project_cost,
        "estimated_profit": estimated_profit,
        "purchase_unknown": purchase_price is None,
        # Include cost model constants for transparency
        "cost_model_constants": {
            "cost_per_sf_new": cost_per_sf_new,
            "cost_per_sf_remodel": cost_per_sf_remodel,
            "cost_per_sf_addition": cost_per_sf_addition,
            "cost_per_sf_garage": cost_per_sf_garage,
            "cost_per_sf_adu": cost_per_sf_adu,
            "landscape_allowance": landscape_allowance,
            "pool_allowance": pool_allowance,
            "soft_cost_pct": soft_cost_pct,
            "interest_rate": interest_rate,
            "loan_points_pct": loan_points_pct,
            "typical_adu_sf": typical_adu_sf,
        },
    }


def _build_timeline_summary(
    metrics: Dict[str, Any],
    permit_timeline: Dict[str, Any],
    project_durations: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Build timeline summary with stage durations.
    
    NEW RULES (Issue Fix):
    - Any duration < 0 days is treated as INVALID and skipped.
    - Purchase-dependent rows are omitted when purchase is unknown/invalid.
    - Total project time is only computed when purchase is valid.
    """
    purchase_date = metrics.get("purchase_date")
    exit_date = metrics.get("exit_date")
    
    plans_submitted_date = permit_timeline.get("plans_submitted_date")
    plans_approved_date = permit_timeline.get("plans_approved_date")
    construction_start_date = permit_timeline.get("construction_start_date")
    construction_completed_date = permit_timeline.get("construction_completed_date")
    
    # Calculate total time only if purchase is known
    total_days = None
    total_months = None
    if purchase_date and exit_date:
        try:
            p_dt = datetime.fromisoformat(purchase_date)
            e_dt = datetime.fromisoformat(exit_date)
            td = (e_dt - p_dt).days
            if td >= 0:  # Only valid if non-negative
                total_days = td
                total_months = round(td / 30.44, 1)
        except Exception:
            pass
    
    stages = []
    
    # Purchase → Plans Submitted (only if purchase is known)
    if purchase_date and plans_submitted_date:
        days = project_durations.get("days_to_submit")
        if days is not None and days >= 0:  # Skip negative durations
            stages.append({
                "name": "Purchase → Plans Submitted",
                "days": days,
                "start_date": purchase_date,
                "end_date": plans_submitted_date,
            })
    
    # Plans Submitted → Approval (permit-based, no purchase needed)
    if plans_submitted_date and plans_approved_date:
        days = project_durations.get("days_to_approve")
        if days is not None and days >= 0:  # Skip negative durations
            stages.append({
                "name": "Plans Submitted → Approval",
                "days": days,
                "start_date": plans_submitted_date,
                "end_date": plans_approved_date,
            })
    
    # Plans Approved → Construction Complete (permit-based, no purchase needed)
    if plans_approved_date and construction_completed_date:
        days = project_durations.get("days_to_complete")
        if days is not None and days >= 0:  # Skip negative durations
            stages.append({
                "name": "Plans Approved → Construction Start",
                "days": days,
                "start_date": plans_approved_date,
                "end_date": construction_start_date,
            })
    
    # STAGE 4: Construction Duration (Start → Completion)
    if construction_start_date and construction_completed_date:
        days = project_durations.get("days_construction")
        if days is not None and days >= 0:  # Skip negative durations
            stages.append({
                "name": "Construction Duration",
                "days": days,
                "start_date": construction_start_date,
                "end_date": construction_completed_date,
            })
    
    # STAGE 5: CofO → Sale (if both known)
    if construction_completed_date and exit_date:
        try:
            cofo_dt = datetime.fromisoformat(construction_completed_date)
            exit_dt = datetime.fromisoformat(exit_date)
            cofo_to_sale_days = (exit_dt - cofo_dt).days
            if cofo_to_sale_days >= 0:  # Skip negative durations
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
        "construction_start_date": construction_start_date,
        "construction_completed_date": construction_completed_date,
        "cofo_date": construction_completed_date,  # alias
    }


def _calculate_deal_fitness_score(
    metrics: Dict[str, Any],
    permit_categories: Dict[str, Any],
    timeline_summary: Dict[str, Any],
    cost_model: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Calculate Deal Fitness Score (0-100) for the comp.
    
    Simple first-pass scoring using:
    - ROI % (higher = better)
    - Permit complexity (lower = better)
    - Money-on-time (spread per day, higher = better)
    - Hold duration (shorter = better for flips)
    
    Returns:
        - score: 0-100 overall score
        - grade: A/B/C/D/F letter grade
        - components: breakdown of scoring factors
        - notes: explanation of the score
    """
    score = 0
    components: Dict[str, Any] = {}
    notes: List[str] = []
    
    # Component 1: ROI Score (0-30 points)
    roi_pct = metrics.get("roi_pct")
    roi_score = 0
    if roi_pct is not None:
        if roi_pct >= 50:
            roi_score = 30
            notes.append("Excellent ROI (≥50%)")
        elif roi_pct >= 30:
            roi_score = 25
            notes.append("Good ROI (30-50%)")
        elif roi_pct >= 20:
            roi_score = 20
            notes.append("Moderate ROI (20-30%)")
        elif roi_pct >= 10:
            roi_score = 15
            notes.append("Low ROI (10-20%)")
        elif roi_pct >= 0:
            roi_score = 10
            notes.append("Minimal ROI (<10%)")
        else:
            roi_score = 0
            notes.append("Negative ROI (loss)")
    else:
        roi_score = 0
        notes.append("ROI not calculable (missing purchase)")
    
    components["roi_score"] = roi_score
    score += roi_score
    
    # Component 2: Permit Complexity Score (0-25 points, lower complexity = higher score)
    permit_complexity = permit_categories.get("permit_complexity_score", "UNKNOWN")
    complexity_score = 0
    if permit_complexity == "LOW":
        complexity_score = 25
        notes.append("Low permit complexity")
    elif permit_complexity == "MEDIUM":
        complexity_score = 15
        notes.append("Moderate permit complexity")
    elif permit_complexity == "HIGH":
        complexity_score = 5
        notes.append("High permit complexity")
    else:
        complexity_score = 10  # Unknown gets middle score
        notes.append("Permit complexity unknown")
    
    components["complexity_score"] = complexity_score
    score += complexity_score
    
    # Component 3: Money-on-Time Score (0-25 points based on spread per day)
    spread_per_day = metrics.get("spread_per_day")
    mot_score = 0
    if spread_per_day is not None and spread_per_day > 0:
        if spread_per_day >= 3000:
            mot_score = 25
            notes.append("Excellent $/day (≥$3k)")
        elif spread_per_day >= 2000:
            mot_score = 20
            notes.append("Good $/day ($2-3k)")
        elif spread_per_day >= 1000:
            mot_score = 15
            notes.append("Moderate $/day ($1-2k)")
        elif spread_per_day >= 500:
            mot_score = 10
            notes.append("Low $/day ($500-1k)")
        else:
            mot_score = 5
            notes.append("Very low $/day (<$500)")
    else:
        mot_score = 0
        notes.append("$/day not calculable")
    
    components["mot_score"] = mot_score
    score += mot_score
    
    # Component 4: Hold Duration Score (0-20 points, shorter = better for flips)
    hold_days = metrics.get("hold_days")
    hold_score = 0
    if hold_days is not None and hold_days > 0:
        if hold_days <= 180:  # ≤6 months
            hold_score = 20
            notes.append("Quick flip (≤6 months)")
        elif hold_days <= 365:  # ≤12 months
            hold_score = 15
            notes.append("Standard hold (6-12 months)")
        elif hold_days <= 548:  # ≤18 months
            hold_score = 10
            notes.append("Extended hold (12-18 months)")
        elif hold_days <= 730:  # ≤24 months
            hold_score = 5
            notes.append("Long hold (18-24 months)")
        else:
            hold_score = 0
            notes.append("Very long hold (>24 months)")
    else:
        hold_score = 0
        notes.append("Hold duration unknown")
    
    components["hold_score"] = hold_score
    score += hold_score
    
    # Calculate grade
    if score >= 85:
        grade = "A"
    elif score >= 70:
        grade = "B"
    elif score >= 55:
        grade = "C"
    elif score >= 40:
        grade = "D"
    else:
        grade = "F"
    
    return {
        "score": score,
        "grade": grade,
        "components": components,
        "notes": notes,
        "max_score": 100,
    }


def _build_data_notes(
    metrics: Dict[str, Any],
    property_snapshot: Dict[str, Any],
    permit_timeline: Dict[str, Any],
    timeline_summary: Dict[str, Any],
    cost_model: Dict[str, Any],
    construction_summary: Dict[str, Any],
    redfin_ok: bool,
    ladbs_ok: bool
) -> List[str]:
    """
    Build list of data notes explaining missing/weak data.
    
    NEW RULES (Issue Fix):
    - Add entries for each actual data issue:
      - Missing or unknown purchase price
      - Invalid/skipped timeline durations
      - Profit not computed due to missing purchase
      - Missing lot size or FAR calculations
    - Only show "No major data issues detected" when list is empty.
    """
    notes = []
    
    if not redfin_ok:
        notes.append("Redfin data unavailable; property details may be incomplete.")
    
    if not ladbs_ok:
        notes.append("LADBS data unavailable; permit history not verified.")
    
    # CRITICAL: Purchase price unknown
    if not metrics.get("purchase_price"):
        notes.append("Purchase price unknown (no prior developer sale in Redfin history); spread, ROI, and profit not computed.")
    
    # Purchase date unknown
    if not metrics.get("purchase_date") and metrics.get("purchase_price"):
        notes.append("Purchase date unknown; timeline durations may be incomplete.")
    
    # Timeline issues: check if any purchase-dependent stages were skipped
    purchase_date = metrics.get("purchase_date")
    plans_submitted = permit_timeline.get("plans_submitted_date")
    
    if plans_submitted and purchase_date:
        try:
            p_dt = datetime.fromisoformat(purchase_date)
            s_dt = datetime.fromisoformat(plans_submitted)
            if p_dt > s_dt:
                notes.append("Purchase → plans duration omitted because available purchase date is after permit dates.")
        except Exception:
            pass
    
    # Lot size / FAR missing
    if not metrics.get("land_sf"):
        notes.append("Lot size not found; FAR calculations not available.")
    
    # CofO date not found
    if not permit_timeline.get("construction_completed_date"):
        notes.append("Certificate of Occupancy date not found; construction completion timing uncertain.")
    
    # Building SF not available
    if not property_snapshot.get("building_sf"):
        notes.append("Building square footage not available from Redfin listing data.")
    
    # Profit not computed note (only if purchase exists but profit is None)
    if metrics.get("purchase_price") and cost_model.get("estimated_profit") is None:
        notes.append("Profit could not be estimated; exit price not available.")
    
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

    # Parse permit timeline FIRST to get earliest permit date
    permits = ladbs_data.get("permits") or []
    permit_timeline = _parse_permit_timeline(permits)
    earliest_permit_date = permit_timeline.get("plans_submitted_date")
    
    # Build metrics with earliest permit date for purchase validation
    metrics = _build_headline_metrics(redfin_data, earliest_permit_date)
    project_contacts = _extract_basic_project_contacts(ladbs_data)
    
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
    property_snapshot = _build_property_snapshot(redfin_data, metrics, ladbs_data.get("permits", []))
    construction_summary = _build_construction_summary(redfin_data, metrics, permit_categories)
    cost_model = _build_cost_model(metrics, construction_summary, permit_categories)
    timeline_summary = _build_timeline_summary(metrics, permit_timeline, project_durations)
    
    # Calculate Deal Fitness Score
    deal_fitness = _calculate_deal_fitness_score(metrics, permit_categories, timeline_summary, cost_model)
    
    data_notes = _build_data_notes(
        metrics, property_snapshot, permit_timeline, timeline_summary,
        cost_model, construction_summary, redfin_ok, ladbs_ok
    )
    links = _build_links(url, team_network)

    # Calculate hold_months for display
    hold_days = metrics.get("hold_days")
    hold_months = round(hold_days / 30.44, 1) if hold_days else None
    
    # Get AI-generated strategy notes
    strategy_notes = None
    try:
        strategy_notes = summarize_comp({
            "address": redfin_data.get("address"),
            "metrics": metrics,
            "permit_categories": permit_categories,
            "construction_summary": construction_summary,
            "timeline_summary": timeline_summary,
            "team_network": team_network,
            "property_snapshot": property_snapshot,
        })
    except Exception as e:
        print(f"[WARN] AI summarizer failed: {e}")
        strategy_notes = None

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
        "deal_fitness": deal_fitness,
        "strategy_notes": strategy_notes,
        "data_notes": data_notes,
        "links": links,
        "hold_months": hold_months,
    }

    # summary_markdown is deprecated, strategy_notes is used instead
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

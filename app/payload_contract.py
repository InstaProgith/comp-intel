from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional
import re

PAYLOAD_CONTRACT_VERSION = "qa-v1"
MISSING_TEXT_VALUES = {"", "none", "null", "n/a", "na", "--"}


def _is_missing_text(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    return value.strip().lower() in MISSING_TEXT_VALUES


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, list) else []


def _deep_apply_defaults(value: Any, defaults: Dict[str, Any]) -> Dict[str, Any]:
    result = _as_dict(value)
    for key, default_value in defaults.items():
        existing = result.get(key)
        if isinstance(default_value, dict):
            result[key] = _deep_apply_defaults(existing, default_value)
        elif isinstance(default_value, list):
            if not isinstance(existing, list):
                result[key] = deepcopy(default_value)
        elif key not in result:
            result[key] = default_value
    return result


def _default_redfin() -> Dict[str, Any]:
    return {
        "source": None,
        "address": None,
        "tax": {},
        "timeline": [],
        "list_price": None,
        "lot_sf": None,
        "current_summary": "-",
        "public_record_summary": "-",
        "lot_summary": "-",
        "sold_banner": None,
        "public_records": {},
    }


def _default_ladbs_permit() -> Dict[str, Any]:
    return {
        "permit_number": None,
        "permit_type": None,
        "Type": None,
        "Status": None,
        "status_date": None,
        "Work_Description": None,
        "Issued_Date": None,
        "job_number": None,
        "contractor": None,
        "contractor_license": None,
        "architect": None,
        "architect_license": None,
        "engineer": None,
        "engineer_license": None,
        "address_label": None,
        "raw_details": {},
    }


def _default_ladbs() -> Dict[str, Any]:
    return {
        "source": None,
        "apn": None,
        "address": None,
        "fetched_at": None,
        "permits": [],
        "note": None,
        "requested_strategy": None,
        "retrieval_strategy": None,
        "fallback_used": False,
        "pin": None,
        "pin_source": None,
        "pin_resolution": None,
        "pin_route": None,
        "pin_route_source": None,
        "pin_route_note": None,
        "address_source": None,
    }


def _default_zimas_profile() -> Dict[str, Any]:
    return {
        "source": None,
        "transport": None,
        "fetched_at": None,
        "pin": None,
        "apn": None,
        "address": None,
        "note": None,
        "pin_resolution_source": None,
        "pin_resolution": None,
        "parcel_identity": {
            "site_address": None,
            "zip_code": None,
            "pin": None,
            "apn": None,
            "lot_area_sqft": None,
            "tract": None,
            "map_reference": None,
            "lot": None,
            "map_sheet": None,
            "thomas_brothers_grid": None,
        },
        "planning_context": {
            "community_plan_area": None,
            "area_planning_commission": None,
            "neighborhood_council": None,
            "council_district": None,
            "census_tract": None,
            "ladbs_district_office": None,
            "recent_activity": None,
            "city_planning_commission": None,
            "ordinance": None,
        },
        "zoning_profile": {
            "zoning": None,
            "zoning_information": None,
            "general_plan_land_use": None,
            "general_plan_notes": None,
            "special_notes": None,
            "historic_preservation_review": None,
            "special_land_use_zoning": None,
            "hpoz": None,
            "baseline_hillside_ordinance": None,
            "specific_plan_area": None,
            "residential_market_area": None,
        },
        "environmental_profile": {
            "urban_agriculture_incentive_zone": None,
            "flood_zone": None,
            "methane_hazard_site": None,
            "upRS_applicability": None,
            "hillside_area": None,
        },
        "hazard_profile": {
            "nearest_fault": None,
            "nearest_fault_distance_km": None,
            "alquist_priolo_fault_zone": None,
            "liquefaction": None,
            "landslide": None,
            "tsunami_hazard_area": None,
        },
        "permit_references": {
            "building_permit_info": None,
            "administrative_review": None,
            "home_sharing": None,
        },
        "section_rows": {},
        "links": {
            "profile_url": None,
            "root_url": None,
        },
        "diagnostics": {
            "pin_resolution": None,
            "profile_url": None,
            "tab_keys": [],
        },
    }


def _default_ladbs_record_document() -> Dict[str, Any]:
    return {
        "doc_type": None,
        "sub_type": None,
        "doc_date": None,
        "doc_number": None,
        "description": None,
        "record_id": None,
        "image_visibility": None,
        "image_to_open": None,
        "doc_ids": None,
        "has_digital_image": False,
        "summary_url": None,
        "image_main_url": None,
        "image_list_url": None,
        "pdf_library": None,
        "pdf_doc_id": None,
        "pdf_url": None,
    }


def _default_ladbs_records() -> Dict[str, Any]:
    return {
        "source": None,
        "transport": None,
        "fetched_at": None,
        "apn": None,
        "pin": None,
        "documents": [],
        "note": None,
        "links": {
            "search_url": None,
            "selection_url": None,
        },
        "search_criteria": None,
        "preselected_addresses": [],
        "page_summary": {},
        "diagnostics": {
            "search_url": None,
            "bootstrap_url": None,
            "selection_candidates": [],
            "selected_addresses": [],
            "document_link_resolutions": [],
        },
    }


def _default_metrics() -> Dict[str, Any]:
    return {
        "purchase_price": None,
        "purchase_date": None,
        "exit_price": None,
        "exit_date": None,
        "spread": None,
        "roi_pct": None,
        "hold_days": None,
        "spread_per_day": None,
        "list_price": None,
        "original_sf": None,
        "new_sf": None,
        "sf_added": None,
        "sf_pct_change": None,
        "land_sf": None,
        "building_sf_before": None,
        "building_sf_after": None,
        "far_before": None,
        "far_after": None,
        "purchase_psf": None,
        "exit_psf": None,
        "list_psf": None,
    }


def _default_property_snapshot() -> Dict[str, Any]:
    return {
        "address_full": None,
        "beds": None,
        "baths": None,
        "building_sf": None,
        "lot_sf": None,
        "property_type": None,
        "year_built": None,
        "status": None,
        "status_date": None,
        "status_price": None,
        "list_price_before_sale": None,
        "price_per_sf": None,
    }


def _default_construction_summary() -> Dict[str, Any]:
    return {
        "existing_sf": None,
        "added_sf": None,
        "final_sf": None,
        "lot_sf": None,
        "scope_level": None,
        "is_new_construction": False,
    }


def _default_permit_categories() -> Dict[str, Any]:
    return {
        "building_count": 0,
        "demo_count": 0,
        "mep_count": 0,
        "other_count": 0,
        "scope_level": None,
        "permit_complexity_score": None,
        "has_pool": False,
        "has_adu": False,
        "has_grading_or_hillside": False,
        "has_methane": False,
        "has_fire_sprinklers": False,
        "removed_fire_sprinklers": False,
        "has_new_structure": False,
    }


def _default_team_network() -> Dict[str, Any]:
    return {
        "primary_gc": None,
        "primary_architect": None,
        "primary_engineer": None,
    }


def _default_timeline_summary() -> Dict[str, Any]:
    return {
        "stages": [],
        "total_days": None,
        "total_months": None,
    }


def _default_cost_model() -> Dict[str, Any]:
    return {
        "remodel_sf": 0,
        "addition_sf": 0,
        "new_sf_full": 0,
        "garage_sf": 0,
        "cost_remodel": 0,
        "cost_addition": 0,
        "cost_new_construction": 0,
        "cost_garage": 0,
        "cost_landscape": 0,
        "has_pool": False,
        "cost_pool": 0,
        "hard_cost_total": 0,
        "soft_costs": 0,
        "financing_cost": 0,
        "total_project_cost": None,
        "estimated_profit": None,
    }


def _default_deal_fitness() -> Dict[str, Any]:
    return {
        "score": None,
        "grade": None,
        "components": {},
        "notes": [],
        "max_score": 100,
    }


def _default_links() -> Dict[str, Any]:
    return {
        "redfin_url": None,
        "ladbs_url": None,
        "zimas_url": None,
        "ladbs_records_url": None,
        "gc_cslb_url": None,
    }


def _default_source_diagnostics() -> Dict[str, Any]:
    return {
        "contract_version": PAYLOAD_CONTRACT_VERSION,
        "schema_warnings": [],
        "source_states": {},
        "anomaly_count": 0,
        "anomaly_codes": [],
    }


def _default_top_level() -> Dict[str, Any]:
    return {
        "url": None,
        "address": "Unknown address",
        "headline_metrics": _default_metrics(),
        "metrics": _default_metrics(),
        "permit_timeline": {},
        "project_durations": {},
        "current_summary": "-",
        "public_record_summary": "-",
        "lot_summary": "-",
        "permit_summary": "-",
        "permit_count": 0,
        "ladbs": _default_ladbs(),
        "redfin": _default_redfin(),
        "project_contacts": None,
        "cslb_contractor": None,
        "permit_categories": _default_permit_categories(),
        "team_network": _default_team_network(),
        "redfin_ok": False,
        "redfin_error": None,
        "ladbs_ok": False,
        "ladbs_error": None,
        "zimas_ok": False,
        "zimas_error": None,
        "ladbs_records_ok": False,
        "ladbs_records_error": None,
        "cslb_ok": False,
        "cslb_error": None,
        "property_snapshot": _default_property_snapshot(),
        "construction_summary": _default_construction_summary(),
        "cost_model": _default_cost_model(),
        "timeline_summary": _default_timeline_summary(),
        "deal_fitness": _default_deal_fitness(),
        "strategy_notes": None,
        "data_notes": [],
        "links": _default_links(),
        "hold_months": None,
        "zimas_profile": _default_zimas_profile(),
        "ladbs_records": _default_ladbs_records(),
        "source_diagnostics": _default_source_diagnostics(),
        "anomalies": [],
        "payload_contract_version": PAYLOAD_CONTRACT_VERSION,
        "summary_markdown": None,
    }


def _sanitize_permits(permits: Any) -> List[Dict[str, Any]]:
    return [
        _deep_apply_defaults(item, _default_ladbs_permit())
        for item in _as_list(permits)
        if isinstance(item, dict)
    ]


def _sanitize_documents(documents: Any) -> List[Dict[str, Any]]:
    return [
        _deep_apply_defaults(item, _default_ladbs_record_document())
        for item in _as_list(documents)
        if isinstance(item, dict)
    ]


def _normalize_address_variant(value: Optional[str]) -> Optional[str]:
    if _is_missing_text(value):
        return None
    normalized = re.sub(r"[^A-Z0-9 ]+", " ", str(value).upper())
    normalized = " ".join(normalized.split())
    return normalized or None


def _parse_document_date(value: Optional[str]) -> Optional[datetime]:
    if _is_missing_text(value):
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value), fmt)
        except ValueError:
            continue
    return None


def _parse_permit_date(value: Optional[str]) -> Optional[datetime]:
    if _is_missing_text(value):
        return None
    match = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", str(value))
    if match:
        return _parse_document_date(match.group(1))
    return _parse_document_date(value)


def _sort_documents(documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        documents,
        key=lambda document: (
            _parse_document_date(_as_dict(document).get("doc_date")) or datetime.min,
            str(_as_dict(document).get("doc_number") or ""),
            str(_as_dict(document).get("record_id") or ""),
        ),
        reverse=True,
    )


def _sort_permits(permits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        permits,
        key=lambda permit: (
            _parse_permit_date(_as_dict(permit).get("status_date"))
            or _parse_permit_date(_as_dict(permit).get("Issued_Date"))
            or datetime.min,
            str(_as_dict(permit).get("permit_number") or ""),
        ),
        reverse=True,
    )


def _build_source_diagnostics(payload: Dict[str, Any], anomalies: List[Dict[str, Any]]) -> Dict[str, Any]:
    redfin = _as_dict(payload.get("redfin"))
    ladbs = _as_dict(payload.get("ladbs"))
    zimas = _as_dict(payload.get("zimas_profile"))
    records = _as_dict(payload.get("ladbs_records"))
    documents = _as_list(records.get("documents"))

    duplicate_record_ids = {
        record_id
        for record_id in [doc.get("record_id") for doc in documents if isinstance(doc, dict)]
        if record_id
        if sum(1 for doc in documents if isinstance(doc, dict) and doc.get("record_id") == record_id) > 1
    }

    return {
        "contract_version": PAYLOAD_CONTRACT_VERSION,
        "schema_warnings": [],
        "anomaly_count": len(anomalies),
        "anomaly_codes": [str(anomaly.get("code")) for anomaly in anomalies if anomaly.get("code")],
        "source_states": {
            "redfin": {
                "source": redfin.get("source"),
                "ok": bool(payload.get("redfin_ok")),
                "timeline_events": len(_as_list(redfin.get("timeline"))),
                "has_tax_apn": bool(_as_dict(redfin.get("tax")).get("apn")),
            },
            "zimas": {
                "source": zimas.get("source"),
                "ok": bool(payload.get("zimas_ok")),
                "transport": zimas.get("transport"),
                "pin": zimas.get("pin"),
                "apn": zimas.get("apn"),
            },
            "ladbs_permits": {
                "source": ladbs.get("source"),
                "ok": bool(payload.get("ladbs_ok")),
                "retrieval_strategy": ladbs.get("retrieval_strategy"),
                "fallback_used": bool(ladbs.get("fallback_used")),
                "permit_count": len(_as_list(ladbs.get("permits"))),
                "address_source": ladbs.get("address_source"),
            },
            "ladbs_records": {
                "source": records.get("source"),
                "ok": bool(payload.get("ladbs_records_ok")),
                "transport": records.get("transport"),
                "document_count": len(documents),
                "digital_image_count": sum(
                    1 for doc in documents if isinstance(doc, dict) and doc.get("has_digital_image")
                ),
                "pdf_link_count": sum(1 for doc in documents if isinstance(doc, dict) and doc.get("pdf_url")),
                "duplicate_record_id_count": len(duplicate_record_ids),
            },
        },
    }


def detect_payload_anomalies(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    anomalies: List[Dict[str, Any]] = []
    metrics = _as_dict(payload.get("metrics"))
    zimas = _as_dict(payload.get("zimas_profile"))
    zpi = _as_dict(zimas.get("parcel_identity"))
    ladbs = _as_dict(payload.get("ladbs"))
    records = _as_dict(payload.get("ladbs_records"))
    permits = _as_list(ladbs.get("permits"))
    documents = _as_list(records.get("documents"))

    redfin_lot_sf = metrics.get("land_sf")
    zimas_lot_sf = zpi.get("lot_area_sqft")
    if isinstance(redfin_lot_sf, (int, float)) and isinstance(zimas_lot_sf, (int, float)) and redfin_lot_sf > 0:
        pct_delta = abs(redfin_lot_sf - zimas_lot_sf) / float(redfin_lot_sf)
        if pct_delta >= 0.10:
            anomalies.append(
                {
                    "code": "lot_size_mismatch",
                    "severity": "warning",
                    "message": (
                        f"Lot-size mismatch across sources: Redfin {redfin_lot_sf:,.0f} SF vs "
                        f"ZIMAS {zimas_lot_sf:,.1f} SF ({pct_delta * 100:.1f}% difference)."
                    ),
                    "details": {
                        "redfin_lot_sf": redfin_lot_sf,
                        "zimas_lot_sf": zimas_lot_sf,
                        "delta_pct": round(pct_delta * 100, 2),
                    },
                }
            )

    address_labels = sorted(
        {
            normalized
            for normalized in (
                _normalize_address_variant(_as_dict(permit).get("address_label"))
                for permit in permits
                if isinstance(permit, dict)
            )
            if normalized
        }
    )
    if len(address_labels) > 1:
        anomalies.append(
            {
                "code": "permit_address_variants",
                "severity": "review",
                "message": "LADBS permits reference multiple address variants; review the permit set for unit/address crossover.",
                "details": {
                    "address_labels": address_labels,
                },
            }
        )

    record_id_map: Dict[str, List[str]] = {}
    for document in documents:
        if not isinstance(document, dict):
            continue
        record_id = document.get("record_id")
        doc_number = document.get("doc_number")
        if not record_id or not doc_number:
            continue
        record_id_map.setdefault(str(record_id), []).append(str(doc_number))
    duplicate_record_ids = {
        record_id: sorted(set(doc_numbers))
        for record_id, doc_numbers in record_id_map.items()
        if len(set(doc_numbers)) > 1
    }
    if duplicate_record_ids:
        anomalies.append(
            {
                "code": "shared_record_ids",
                "severity": "review",
                "message": "LADBS records reuse the same underlying record ID for multiple document numbers.",
                "details": {
                    "record_ids": duplicate_record_ids,
                },
            }
        )

    if payload.get("zimas_ok"):
        zoning = _as_dict(zimas.get("zoning_profile")).get("zoning")
        community_plan = _as_dict(zimas.get("planning_context")).get("community_plan_area")
        if _is_missing_text(zoning) or _is_missing_text(community_plan):
            anomalies.append(
                {
                    "code": "zimas_core_fields_missing",
                    "severity": "warning",
                    "message": "ZIMAS profile succeeded but one or more core zoning/planning fields are blank.",
                    "details": {
                        "zoning": zoning,
                        "community_plan_area": community_plan,
                    },
                }
            )

    sorted_dates = [
        _parse_document_date(_as_dict(document).get("doc_date"))
        for document in documents
        if isinstance(document, dict)
    ]
    sorted_dates = [value for value in sorted_dates if value is not None]
    if sorted_dates and sorted_dates != sorted(sorted_dates, reverse=True):
        anomalies.append(
            {
                "code": "records_not_date_sorted",
                "severity": "review",
                "message": "LADBS record rows are not sorted newest-to-oldest by document date; review carefully when comparing filings.",
                "details": {},
            }
        )

    return anomalies


def validate_report_payload_shape(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    def expect(path: str, value: Any, expected_types: tuple[type, ...]) -> None:
        if not isinstance(value, expected_types):
            expected_names = ", ".join(sorted(t.__name__ for t in expected_types))
            errors.append(f"{path} should be {expected_names}, got {type(value).__name__}")

    expect("payload", payload, (dict,))
    expect("headline_metrics", payload.get("headline_metrics"), (dict,))
    expect("metrics", payload.get("metrics"), (dict,))
    expect("ladbs", payload.get("ladbs"), (dict,))
    expect("redfin", payload.get("redfin"), (dict,))
    expect("zimas_profile", payload.get("zimas_profile"), (dict,))
    expect("ladbs_records", payload.get("ladbs_records"), (dict,))
    expect("links", payload.get("links"), (dict,))
    expect("data_notes", payload.get("data_notes"), (list,))
    expect("anomalies", payload.get("anomalies"), (list,))
    expect("source_diagnostics", payload.get("source_diagnostics"), (dict,))

    if isinstance(payload.get("ladbs"), dict):
        expect("ladbs.permits", payload["ladbs"].get("permits"), (list,))
    if isinstance(payload.get("redfin"), dict):
        expect("redfin.timeline", payload["redfin"].get("timeline"), (list,))
    if isinstance(payload.get("zimas_profile"), dict):
        expect("zimas_profile.parcel_identity", payload["zimas_profile"].get("parcel_identity"), (dict,))
        expect("zimas_profile.planning_context", payload["zimas_profile"].get("planning_context"), (dict,))
        expect("zimas_profile.zoning_profile", payload["zimas_profile"].get("zoning_profile"), (dict,))
        expect("zimas_profile.environmental_profile", payload["zimas_profile"].get("environmental_profile"), (dict,))
        expect("zimas_profile.hazard_profile", payload["zimas_profile"].get("hazard_profile"), (dict,))
    if isinstance(payload.get("ladbs_records"), dict):
        expect("ladbs_records.documents", payload["ladbs_records"].get("documents"), (list,))

    return errors


def apply_payload_contract(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    normalized = _deep_apply_defaults(payload, _default_top_level())

    normalized["redfin"] = _deep_apply_defaults(normalized.get("redfin"), _default_redfin())
    normalized["ladbs"] = _deep_apply_defaults(normalized.get("ladbs"), _default_ladbs())
    normalized["zimas_profile"] = _deep_apply_defaults(normalized.get("zimas_profile"), _default_zimas_profile())
    normalized["ladbs_records"] = _deep_apply_defaults(normalized.get("ladbs_records"), _default_ladbs_records())
    normalized["property_snapshot"] = _deep_apply_defaults(
        normalized.get("property_snapshot"), _default_property_snapshot()
    )
    normalized["construction_summary"] = _deep_apply_defaults(
        normalized.get("construction_summary"), _default_construction_summary()
    )
    normalized["permit_categories"] = _deep_apply_defaults(
        normalized.get("permit_categories"), _default_permit_categories()
    )
    normalized["team_network"] = _deep_apply_defaults(normalized.get("team_network"), _default_team_network())
    normalized["timeline_summary"] = _deep_apply_defaults(
        normalized.get("timeline_summary"), _default_timeline_summary()
    )
    normalized["cost_model"] = _deep_apply_defaults(normalized.get("cost_model"), _default_cost_model())
    normalized["deal_fitness"] = _deep_apply_defaults(
        normalized.get("deal_fitness"), _default_deal_fitness()
    )
    normalized["headline_metrics"] = _deep_apply_defaults(
        normalized.get("headline_metrics"), _default_metrics()
    )
    normalized["metrics"] = _deep_apply_defaults(
        normalized.get("metrics") or normalized.get("headline_metrics"),
        _default_metrics(),
    )
    normalized["links"] = _deep_apply_defaults(normalized.get("links"), _default_links())
    normalized["source_diagnostics"] = _deep_apply_defaults(
        normalized.get("source_diagnostics"), _default_source_diagnostics()
    )
    normalized["payload_contract_version"] = PAYLOAD_CONTRACT_VERSION
    normalized["summary_markdown"] = None

    normalized["ladbs"]["permits"] = _sort_permits(_sanitize_permits(normalized["ladbs"].get("permits")))
    normalized["ladbs_records"]["documents"] = _sort_documents(
        _sanitize_documents(normalized["ladbs_records"].get("documents"))
    )
    normalized["data_notes"] = [str(note) for note in _as_list(normalized.get("data_notes")) if note]

    anomalies = detect_payload_anomalies(normalized)
    normalized["anomalies"] = anomalies
    normalized["source_diagnostics"] = _build_source_diagnostics(normalized, anomalies)
    normalized["source_diagnostics"]["schema_warnings"] = validate_report_payload_shape(normalized)
    return normalized

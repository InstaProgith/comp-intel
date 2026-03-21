from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List

from flask import render_template

from app.orchestrator import run_full_comp_pipeline

DEFAULT_PROPERTIES = [
    {
        "name": "lucerne",
        "redfin_url": "https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003",
        "expectations": {
            "address_contains": "Lucerne",
            "pin": "129B185   131",
            "apn": "5082004025",
            "zoning": "R1-1-O",
            "general_plan_land_use": "Low II Residential",
            "community_plan_area": "Wilshire",
            "min_permit_count": 7,
            "min_record_count": 14,
            "required_permit_numbers": [
                "25041-90000-59794",
                "25042-90000-22280",
                "25014-10000-03595",
            ],
            "required_document_numbers": [
                "06014-70000-09673",
                "06016-70000-21824",
                "06014-70001-09673",
            ],
            "required_report_sections": [
                "Developer Snapshot",
                "Permit Overview",
                "ZIMAS Parcel Profile",
                "LADBS Records",
                "Review Flags",
                "Data Notes",
            ],
            "forbidden_report_strings": [
                ">None<",
                "null",
            ],
        },
    }
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a configurable real-property QA harness against the full comp-intel pipeline."
    )
    parser.add_argument(
        "--redfin-url",
        action="append",
        dest="redfin_urls",
        help="Add one Redfin property URL to the QA run. Can be passed multiple times.",
    )
    parser.add_argument(
        "--property-file",
        help="Optional JSON file containing a list of property objects or a {'properties': [...]} wrapper.",
    )
    parser.add_argument("--json", action="store_true", help="Print the full QA summary payload as JSON.")
    return parser


def _load_property_file(path_text: str) -> List[Dict[str, Any]]:
    path = Path(path_text)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("properties") or []
    results: List[Dict[str, Any]] = []
    for index, item in enumerate(payload):
        if isinstance(item, str):
            results.append({"name": f"property-{index + 1}", "redfin_url": item})
        elif isinstance(item, dict) and item.get("redfin_url"):
            case = dict(item)
            case["name"] = item.get("name") or f"property-{index + 1}"
            case["redfin_url"] = item["redfin_url"]
            case["expectations"] = item.get("expectations") or {}
            results.append(case)
    return results


def _collect_properties(args: argparse.Namespace) -> List[Dict[str, Any]]:
    properties: List[Dict[str, Any]] = []
    if args.property_file:
        properties.extend(_load_property_file(args.property_file))
    if args.redfin_urls:
        for index, url in enumerate(args.redfin_urls, start=1):
            properties.append({"name": f"cli-{index}", "redfin_url": url, "expectations": {}})
    return properties or list(DEFAULT_PROPERTIES)


def _render_report_html(payload: Dict[str, Any]) -> str:
    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("APP_TESTING", "1")
    os.environ.setdefault("FLASK_SECRET_KEY", "qa-harness-secret")
    os.environ.setdefault("APP_ACCESS_PASSWORD", "qa-harness-password")
    from app.ui_server import app as ui_app

    with ui_app.test_request_context("/report"):
        return render_template("report.html", r=payload)


def _build_report_checks(report_html: str) -> Dict[str, Any]:
    return {
        "contains_none": ">None<" in report_html,
        "contains_null": "null" in report_html,
        "has_review_flags": "Review Flags" in report_html,
        "has_data_notes": "Data Notes" in report_html,
        "has_zimas_section": "ZIMAS Parcel Profile" in report_html,
        "has_ladbs_records_section": "LADBS Records" in report_html,
    }


def _build_key_fields(payload: Dict[str, Any]) -> Dict[str, Any]:
    zimas = payload.get("zimas_profile") or {}
    zoning_profile = zimas.get("zoning_profile") or {}
    planning_context = zimas.get("planning_context") or {}
    hazard_profile = zimas.get("hazard_profile") or {}
    documents = (payload.get("ladbs_records") or {}).get("documents") or []
    return {
        "address": payload.get("address"),
        "pin": zimas.get("pin"),
        "apn": zimas.get("apn"),
        "zoning": zoning_profile.get("zoning"),
        "general_plan_land_use": zoning_profile.get("general_plan_land_use"),
        "community_plan_area": planning_context.get("community_plan_area"),
        "nearest_fault": hazard_profile.get("nearest_fault"),
        "permit_count": len((payload.get("ladbs") or {}).get("permits") or []),
        "record_count": len(documents),
        "pdf_link_count": sum(1 for document in documents if isinstance(document, dict) and document.get("pdf_url")),
    }


def _evaluate_expectations(case: Dict[str, Any], payload: Dict[str, Any], report_html: str) -> List[str]:
    expectations = case.get("expectations") or {}
    failures: List[str] = []
    address = str(payload.get("address") or "")
    zimas = payload.get("zimas_profile") or {}
    zoning_profile = zimas.get("zoning_profile") or {}
    planning_context = zimas.get("planning_context") or {}
    permits = (payload.get("ladbs") or {}).get("permits") or []
    documents = (payload.get("ladbs_records") or {}).get("documents") or []
    ladbs = payload.get("ladbs") or {}
    records = payload.get("ladbs_records") or {}

    def expect_equal(label: str, actual: Any, expected: Any) -> None:
        if actual != expected:
            failures.append(f"{label} expected {expected!r} but got {actual!r}")

    def expect_in(label: str, actual: Any, allowed_values: List[Any]) -> None:
        if allowed_values and actual not in allowed_values:
            failures.append(f"{label} expected one of {allowed_values!r} but got {actual!r}")

    if expectations.get("address_contains") and expectations["address_contains"].lower() not in address.lower():
        failures.append(
            f"address should contain {expectations['address_contains']!r}, got {address!r}"
        )

    if expectations.get("pin"):
        expect_equal("zimas pin", zimas.get("pin"), expectations["pin"])
    if expectations.get("apn"):
        expect_equal("zimas apn", zimas.get("apn"), expectations["apn"])
    if expectations.get("zoning"):
        expect_equal("zoning", zoning_profile.get("zoning"), expectations["zoning"])
    if expectations.get("general_plan_land_use"):
        expect_equal(
            "general plan land use",
            zoning_profile.get("general_plan_land_use"),
            expectations["general_plan_land_use"],
        )
    if expectations.get("community_plan_area"):
        expect_equal(
            "community plan area",
            planning_context.get("community_plan_area"),
            expectations["community_plan_area"],
        )

    min_permit_count = expectations.get("min_permit_count")
    if isinstance(min_permit_count, int) and len(permits) < min_permit_count:
        failures.append(f"permit count expected at least {min_permit_count}, got {len(permits)}")

    min_record_count = expectations.get("min_record_count")
    if isinstance(min_record_count, int) and len(documents) < min_record_count:
        failures.append(f"record count expected at least {min_record_count}, got {len(documents)}")

    min_pdf_count = expectations.get("min_pdf_count")
    pdf_count = sum(1 for document in documents if isinstance(document, dict) and document.get("pdf_url"))
    if isinstance(min_pdf_count, int) and pdf_count < min_pdf_count:
        failures.append(f"pdf link count expected at least {min_pdf_count}, got {pdf_count}")

    if expectations.get("allowed_permit_sources"):
        expect_in("permit source", ladbs.get("source"), list(expectations["allowed_permit_sources"]))
    if expectations.get("allowed_records_sources"):
        expect_in("records source", records.get("source"), list(expectations["allowed_records_sources"]))
    if expectations.get("allowed_zimas_sources"):
        expect_in("zimas source", zimas.get("source"), list(expectations["allowed_zimas_sources"]))

    permit_numbers = {str(permit.get("permit_number")) for permit in permits if isinstance(permit, dict)}
    for permit_number in expectations.get("required_permit_numbers") or []:
        if permit_number not in permit_numbers:
            failures.append(f"required permit number missing: {permit_number}")

    document_numbers = {str(document.get("doc_number")) for document in documents if isinstance(document, dict)}
    for document_number in expectations.get("required_document_numbers") or []:
        if document_number not in document_numbers:
            failures.append(f"required document number missing: {document_number}")

    for heading in expectations.get("required_report_sections") or []:
        if heading not in report_html:
            failures.append(f"report heading missing: {heading}")

    for text in expectations.get("forbidden_report_strings") or []:
        if text in report_html:
            failures.append(f"forbidden report text present: {text}")

    for snippet in expectations.get("required_data_note_substrings") or []:
        if not any(snippet in str(note) for note in (payload.get("data_notes") or [])):
            failures.append(f"required data note missing substring: {snippet}")

    return failures


def _build_summary(case: Dict[str, Any], payload: Dict[str, Any], report_html: str) -> Dict[str, Any]:
    source_states = (payload.get("source_diagnostics") or {}).get("source_states") or {}
    permits = ((payload.get("ladbs") or {}).get("permits") or [])[:3]
    documents = ((payload.get("ladbs_records") or {}).get("documents") or [])[:3]
    qa_failures = _evaluate_expectations(case, payload, report_html)
    review_flags = [
        {
            "code": anomaly.get("code"),
            "severity": anomaly.get("severity"),
            "message": anomaly.get("message"),
        }
        for anomaly in (payload.get("anomalies") or [])
    ]
    return {
        "name": case.get("name"),
        "tags": case.get("tags") or [],
        "redfin_url": case.get("redfin_url"),
        "address": payload.get("address"),
        "known_truths": case.get("known_truths") or {},
        "key_fields_to_verify": case.get("key_fields_to_verify") or [],
        "acceptable_uncertainty_notes": case.get("acceptable_uncertainty_notes") or [],
        "key_fields": _build_key_fields(payload),
        "schema_warnings": (payload.get("source_diagnostics") or {}).get("schema_warnings") or [],
        "anomaly_count": len(payload.get("anomalies") or []),
        "anomaly_codes": (payload.get("source_diagnostics") or {}).get("anomaly_codes") or [],
        "review_flags": review_flags,
        "source_states": source_states,
        "permit_numbers": [permit.get("permit_number") for permit in permits if isinstance(permit, dict)],
        "document_numbers": [document.get("doc_number") for document in documents if isinstance(document, dict)],
        "data_notes": payload.get("data_notes") or [],
        "report_checks": _build_report_checks(report_html),
        "qa_failures": qa_failures,
        "qa_failure_count": len(qa_failures),
        "qa_passed": not qa_failures,
    }


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    properties = _collect_properties(args)
    summaries: List[Dict[str, Any]] = []

    for case in properties:
        payload = run_full_comp_pipeline(case["redfin_url"])
        report_html = _render_report_html(payload)
        summaries.append(_build_summary(case, payload, report_html))

    if args.json:
        print(json.dumps({"properties": summaries}, indent=2, sort_keys=True))
    else:
        for summary in summaries:
            print(f"[QA] name={summary['name']!r}")
            print(f"[QA] address={summary['address']!r}")
            print(f"[QA] redfin_url={summary['redfin_url']!r}")
            print(f"[QA] schema_warnings={len(summary['schema_warnings'])}")
            print(f"[QA] anomaly_count={summary['anomaly_count']}")
            if summary["anomaly_codes"]:
                print(f"[QA] anomaly_codes={summary['anomaly_codes']}")
            print("[QA] key_fields=" + json.dumps(summary["key_fields"], sort_keys=True))
            print("[QA] report_checks=" + json.dumps(summary["report_checks"], sort_keys=True))
            print(
                "[QA] sources="
                + json.dumps(summary["source_states"], sort_keys=True)
            )
            if summary["permit_numbers"]:
                print(f"[QA] permit_numbers={summary['permit_numbers']}")
            if summary["document_numbers"]:
                print(f"[QA] document_numbers={summary['document_numbers']}")
            if summary["data_notes"]:
                print(f"[QA] data_notes={summary['data_notes']}")
            if summary["qa_failures"]:
                print(f"[QA] qa_failures={summary['qa_failures']}")

    return 0 if all(not summary["schema_warnings"] and summary["qa_passed"] for summary in summaries) else 1


if __name__ == "__main__":
    raise SystemExit(main())

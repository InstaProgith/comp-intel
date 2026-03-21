from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup
from flask import render_template

from app.orchestrator import run_full_comp_pipeline
from app.payload_contract import apply_payload_contract

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = BASE_DIR / "review_bundles" / "report_acceptance"
DEFAULT_PROPERTY_FILE = BASE_DIR / "validation" / "report_acceptance_property_pack.json"
EXPECTED_SECTION_ORDER = [
    "Developer Snapshot",
    "Timeline Summary",
    "Construction Summary",
    "Cost Model",
    "Permit Overview",
    "ZIMAS Parcel Profile",
    "LADBS Records",
    "Team",
    "Strategy Notes",
    "Review Flags",
    "Data Notes",
    "Links",
]
MOJIBAKE_TOKENS = ("Â·", "â€”", "â€¦", "Ã", "Â ")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate tracked report-acceptance bundles for a small real-property review set."
    )
    parser.add_argument(
        "--property-file",
        default=str(DEFAULT_PROPERTY_FILE),
        help="JSON file containing the report-acceptance property pack.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where per-property review bundles should be written.",
    )
    parser.add_argument("--json", action="store_true", help="Print the acceptance summary payload as JSON.")
    return parser


def _load_property_file(path_text: str) -> List[Dict[str, Any]]:
    path = Path(path_text)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("properties") or []

    results: List[Dict[str, Any]] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict) or not item.get("redfin_url"):
            continue
        case = dict(item)
        case["name"] = item.get("name") or f"property-{index + 1}"
        case["expectations"] = item.get("expectations") or {}
        case["known_truths"] = item.get("known_truths") or {}
        case["acceptable_uncertainty_notes"] = item.get("acceptable_uncertainty_notes") or []
        case["review_checks"] = item.get("review_checks") or {}
        results.append(case)
    return results


def _render_report_html(payload: Dict[str, Any]) -> str:
    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("APP_TESTING", "1")
    os.environ.setdefault("FLASK_SECRET_KEY", "report-acceptance-secret")
    os.environ.setdefault("APP_ACCESS_PASSWORD", "report-acceptance-password")
    from app.ui_server import app as ui_app

    with ui_app.test_request_context("/report"):
        return render_template("report.html", r=payload)


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalize_compare_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _normalize_text(value).lower()).strip()


def _extract_section_map(report_html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(report_html, "lxml")
    section_map: Dict[str, Any] = {}
    for section in soup.select(".report-section"):
        header = section.select_one(".report-section-header")
        if header:
            section_map[_normalize_text(header.get_text(" ", strip=True))] = section
    return section_map


def _extract_report_checks(payload: Dict[str, Any], report_html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(report_html, "lxml")
    section_map = _extract_section_map(report_html)
    actual_headers = list(section_map.keys())
    strategy_notes_present = bool((payload.get("strategy_notes") or {}).get("tactics") or (payload.get("strategy_notes") or {}).get("risks") or (payload.get("strategy_notes") or {}).get("insights"))
    expected_headers = [header for header in EXPECTED_SECTION_ORDER if header != "Strategy Notes" or strategy_notes_present]

    permit_section = section_map.get("Permit Overview")
    record_section = section_map.get("LADBS Records")
    zimas_section = section_map.get("ZIMAS Parcel Profile")
    review_flag_messages = [
        _normalize_text(node.get_text(" ", strip=True))
        for node in soup.select(".review-flag-message")
        if _normalize_text(node.get_text(" ", strip=True))
    ]
    data_note_messages = [
        _normalize_text(node.get_text(" ", strip=True))
        for node in soup.select(".data-notes-list li")
        if _normalize_text(node.get_text(" ", strip=True))
    ]
    normalized_data_notes = {_normalize_compare_text(note) for note in data_note_messages}
    duplicate_note_overlap = [
        message for message in review_flag_messages if _normalize_compare_text(message) in normalized_data_notes
    ]

    zimas_rows: Dict[str, str] = {}
    if zimas_section:
        for row in zimas_section.select("table.audit-list tr"):
            cells = row.find_all("td")
            if len(cells) >= 2:
                zimas_rows[_normalize_text(cells[0].get_text(" ", strip=True))] = _normalize_text(cells[1].get_text(" ", strip=True))

    key_field_mismatches: List[str] = []
    rendered_address = _normalize_text((soup.select_one(".property-address") or {}).get_text(" ", strip=True) if soup.select_one(".property-address") else "")
    payload_address = _normalize_text(payload.get("address"))
    if payload_address and rendered_address and payload_address != rendered_address:
        key_field_mismatches.append(f"Report address {rendered_address!r} does not match payload address {payload_address!r}.")

    zimas = payload.get("zimas_profile") or {}
    zoning_profile = zimas.get("zoning_profile") or {}
    planning_context = zimas.get("planning_context") or {}
    expected_render_pairs = {
        "PIN": zimas.get("pin"),
        "APN": zimas.get("apn"),
        "Zoning": zoning_profile.get("zoning"),
        "General Plan": zoning_profile.get("general_plan_land_use"),
        "Community Plan": planning_context.get("community_plan_area"),
    }
    for label, payload_value in expected_render_pairs.items():
        rendered_value = zimas_rows.get(label)
        if payload_value and rendered_value and _normalize_compare_text(rendered_value) == "unknown":
            key_field_mismatches.append(f"{label} rendered as Unknown despite payload value {payload_value!r}.")

    report_pdf_links = 0
    if record_section:
        for link in record_section.select(".doc-links a"):
            if _normalize_compare_text(link.get_text(" ", strip=True)) == "pdf":
                report_pdf_links += 1

    return {
        "property_header_present": bool(soup.select_one(".property-header")),
        "section_headers": actual_headers,
        "expected_section_headers": expected_headers,
        "section_order_matches": actual_headers == expected_headers,
        "missing_sections": [header for header in expected_headers if header not in actual_headers],
        "contains_none": ">None<" in report_html or " None " in report_html,
        "contains_null": "null" in report_html,
        "contains_mojibake": any(token in report_html for token in MOJIBAKE_TOKENS),
        "permit_items_rendered": len(permit_section.select(".permit-item")) if permit_section else 0,
        "record_items_rendered": len(record_section.select(".permit-item")) if record_section else 0,
        "pdf_links_rendered": report_pdf_links,
        "duplicate_note_overlap": duplicate_note_overlap,
        "zimas_rows": zimas_rows,
        "key_field_render_mismatches": key_field_mismatches,
    }


def _evaluate_property(case: Dict[str, Any], payload: Dict[str, Any], report_checks: Dict[str, Any]) -> Dict[str, Any]:
    expectations = case.get("expectations") or {}
    known_truths = case.get("known_truths") or {}
    zimas = payload.get("zimas_profile") or {}
    zoning_profile = zimas.get("zoning_profile") or {}
    planning_context = zimas.get("planning_context") or {}
    permits = (payload.get("ladbs") or {}).get("permits") or []
    documents = (payload.get("ladbs_records") or {}).get("documents") or []
    pdf_count = sum(1 for doc in documents if isinstance(doc, dict) and doc.get("pdf_url"))
    source_states = (payload.get("source_diagnostics") or {}).get("source_states") or {}

    fact_mismatches: List[str] = []
    report_issues: List[str] = []
    questionable_items: List[str] = []

    expected_pairs = {
        "address": payload.get("address"),
        "apn": zimas.get("apn"),
        "pin": zimas.get("pin"),
        "zoning": zoning_profile.get("zoning"),
        "general_plan_land_use": zoning_profile.get("general_plan_land_use"),
        "community_plan_area": planning_context.get("community_plan_area"),
    }
    for key, expected_value in known_truths.items():
        actual_value = expected_pairs.get(key)
        if expected_value and actual_value != expected_value:
            fact_mismatches.append(f"{key} expected {expected_value!r} but got {actual_value!r}.")

    min_permit_count = expectations.get("min_permit_count")
    if isinstance(min_permit_count, int) and len(permits) < min_permit_count:
        fact_mismatches.append(f"Permit count {len(permits)} is below expected minimum {min_permit_count}.")

    min_record_count = expectations.get("min_record_count")
    if isinstance(min_record_count, int) and len(documents) < min_record_count:
        fact_mismatches.append(f"Record count {len(documents)} is below expected minimum {min_record_count}.")

    min_pdf_count = expectations.get("min_pdf_count")
    if isinstance(min_pdf_count, int) and pdf_count < min_pdf_count:
        fact_mismatches.append(f"PDF-link count {pdf_count} is below expected minimum {min_pdf_count}.")

    permit_numbers = {str(permit.get("permit_number")) for permit in permits if isinstance(permit, dict)}
    for permit_number in expectations.get("required_permit_numbers") or []:
        if permit_number not in permit_numbers:
            fact_mismatches.append(f"Representative permit {permit_number} is missing from the payload.")

    document_numbers = {str(document.get("doc_number")) for document in documents if isinstance(document, dict)}
    for document_number in expectations.get("required_document_numbers") or []:
        if document_number not in document_numbers:
            fact_mismatches.append(f"Representative document {document_number} is missing from the payload.")

    if not report_checks["property_header_present"]:
        report_issues.append("Property header is missing from the rendered report.")
    if not report_checks["section_order_matches"]:
        report_issues.append(
            "Section order mismatch: "
            f"expected {report_checks['expected_section_headers']!r}, got {report_checks['section_headers']!r}."
        )
    if report_checks["missing_sections"]:
        report_issues.append(f"Missing report sections: {report_checks['missing_sections']!r}.")
    if report_checks["contains_none"]:
        report_issues.append("Rendered report still contains raw None-style placeholder text.")
    if report_checks["contains_null"]:
        report_issues.append("Rendered report still contains raw null text.")
    if report_checks["contains_mojibake"]:
        report_issues.append("Rendered report contains mojibake or encoding garbage.")
    if report_checks["duplicate_note_overlap"]:
        report_issues.append(
            "Review Flags and Data Notes repeat the same message(s): "
            f"{report_checks['duplicate_note_overlap']!r}."
        )
    if report_checks["key_field_render_mismatches"]:
        report_issues.extend(report_checks["key_field_render_mismatches"])

    if report_checks["permit_items_rendered"] != len(permits):
        report_issues.append(
            "Permit item count in the report "
            f"({report_checks['permit_items_rendered']}) does not match payload permit count ({len(permits)})."
        )
    if report_checks["record_items_rendered"] != len(documents):
        report_issues.append(
            "Record item count in the report "
            f"({report_checks['record_items_rendered']}) does not match payload record count ({len(documents)})."
        )
    if report_checks["pdf_links_rendered"] != pdf_count:
        report_issues.append(
            "PDF-link count in the report "
            f"({report_checks['pdf_links_rendered']}) does not match payload PDF-link count ({pdf_count})."
        )

    for flag in payload.get("anomalies") or []:
        message = _normalize_text(flag.get("message"))
        if message:
            questionable_items.append(message)
    for note in payload.get("data_notes") or []:
        normalized_note = _normalize_text(note)
        if normalized_note:
            questionable_items.append(normalized_note)
    for note in case.get("acceptable_uncertainty_notes") or []:
        normalized_note = _normalize_text(note)
        if normalized_note and normalized_note not in questionable_items:
            questionable_items.append(normalized_note)

    questionable_items = list(dict.fromkeys(questionable_items))

    if fact_mismatches or report_issues:
        verdict = "needs-fix"
    elif (payload.get("anomalies") or []) or (payload.get("data_notes") or []):
        verdict = "accepted-with-review"
    else:
        verdict = "accepted"

    representative_permits = [
        permit.get("permit_number")
        for permit in permits[:3]
        if isinstance(permit, dict) and permit.get("permit_number")
    ]
    representative_documents = [
        document.get("doc_number")
        for document in documents[:3]
        if isinstance(document, dict) and document.get("doc_number")
    ]

    return {
        "name": case.get("name"),
        "role": case.get("role"),
        "redfin_url": case.get("redfin_url"),
        "address": payload.get("address"),
        "verdict": verdict,
        "known_truths": known_truths,
        "actual_facts": {
            "apn": zimas.get("apn"),
            "pin": zimas.get("pin"),
            "zoning": zoning_profile.get("zoning"),
            "general_plan_land_use": zoning_profile.get("general_plan_land_use"),
            "community_plan_area": planning_context.get("community_plan_area"),
            "permit_count": len(permits),
            "record_count": len(documents),
            "pdf_link_count": pdf_count,
        },
        "representative_permits": representative_permits,
        "representative_documents": representative_documents,
        "source_states": source_states,
        "fact_mismatches": fact_mismatches,
        "report_issues": report_issues,
        "questionable_items": questionable_items,
        "review_flags": payload.get("anomalies") or [],
        "data_notes": payload.get("data_notes") or [],
        "report_checks": report_checks,
    }


def _build_property_summary_markdown(summary: Dict[str, Any], bundle_dir: Path) -> str:
    actual = summary["actual_facts"]
    source_states = summary["source_states"]
    review_flags = summary["review_flags"]
    report_checks = summary["report_checks"]
    lines = [
        f"# {summary['name'].replace('-', ' ').title()} Review Summary",
        "",
        f"- Verdict: `{summary['verdict']}`",
        f"- Role: `{summary.get('role') or 'review'}`",
        f"- Address: `{summary['address']}`",
        f"- URL: {summary['redfin_url']}",
        f"- Payload: [payload.normalized.json](payload.normalized.json)",
        f"- Rendered report: [report.html](report.html)",
        "",
        "## Key Facts",
        "",
        f"- APN: `{actual['apn']}`",
        f"- PIN: `{actual['pin']}`",
        f"- Zoning: `{actual['zoning']}`",
        f"- General Plan: `{actual['general_plan_land_use']}`",
        f"- Community Plan: `{actual['community_plan_area']}`",
        f"- Permit count: `{actual['permit_count']}`",
        f"- Record count: `{actual['record_count']}`",
        f"- PDF-link count: `{actual['pdf_link_count']}`",
        "",
        "## Representative IDs",
        "",
        f"- Permits: {', '.join(summary['representative_permits']) if summary['representative_permits'] else 'None'}",
        f"- Documents: {', '.join(summary['representative_documents']) if summary['representative_documents'] else 'None'}",
        "",
        "## Sources",
        "",
    ]
    for name, state in source_states.items():
        lines.append(f"- {name}: `{state.get('source')}`")

    lines.extend(
        [
            "",
            "## Report Checks",
            "",
            f"- Section order matches: `{report_checks['section_order_matches']}`",
            f"- Property header present: `{report_checks['property_header_present']}`",
            f"- Rendered permit items: `{report_checks['permit_items_rendered']}`",
            f"- Rendered record items: `{report_checks['record_items_rendered']}`",
            f"- Rendered PDF links: `{report_checks['pdf_links_rendered']}`",
            f"- Raw None text present: `{report_checks['contains_none']}`",
            f"- Raw null text present: `{report_checks['contains_null']}`",
            f"- Mojibake present: `{report_checks['contains_mojibake']}`",
            "",
            "## Review Flags",
            "",
        ]
    )
    if review_flags:
        for flag in review_flags:
            lines.append(f"- `{flag.get('code')}`: {flag.get('message')}")
    else:
        lines.append("- None")

    lines.extend(["", "## Data Notes", ""])
    if summary["data_notes"]:
        for note in summary["data_notes"]:
            lines.append(f"- {note}")
    else:
        lines.append("- None")

    lines.extend(["", "## Questionable Items", ""])
    if summary["questionable_items"]:
        for item in summary["questionable_items"]:
            lines.append(f"- {item}")
    else:
        lines.append("- None")

    lines.extend(["", "## Mismatches / Issues", ""])
    if summary["fact_mismatches"] or summary["report_issues"]:
        for item in summary["fact_mismatches"]:
            lines.append(f"- Fact mismatch: {item}")
        for item in summary["report_issues"]:
            lines.append(f"- Report issue: {item}")
    else:
        lines.append("- None")

    return "\n".join(lines) + "\n"


def _write_bundle(bundle_root: Path, payload: Dict[str, Any], report_html: str, summary: Dict[str, Any]) -> None:
    bundle_dir = bundle_root / summary["name"]
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "payload.normalized.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (bundle_dir / "report.html").write_text(report_html, encoding="utf-8")
    (bundle_dir / "summary.md").write_text(
        _build_property_summary_markdown(summary, bundle_dir),
        encoding="utf-8",
    )


def _build_index_markdown(bundle_root: Path, summaries: List[Dict[str, Any]]) -> str:
    lines = [
        "# Report Review Index",
        "",
        "| Property | Role | Verdict | Address | Key Facts | Flags | Bundle |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for summary in summaries:
        facts = summary["actual_facts"]
        flags = ", ".join(flag.get("code") or "review" for flag in summary["review_flags"]) or "none"
        bundle_path = bundle_root / summary["name"]
        lines.append(
            "| "
            + f"{summary['name']} | "
            + f"{summary.get('role') or 'review'} | "
            + f"`{summary['verdict']}` | "
            + f"{summary['address']} | "
            + f"PIN `{facts['pin']}` / APN `{facts['apn']}` / permits `{facts['permit_count']}` / records `{facts['record_count']}` | "
            + f"{flags} | "
            + f"[summary](./{bundle_path.as_posix().replace((BASE_DIR.as_posix() + '/'), '')}/summary.md) / "
            + f"[payload](./{bundle_path.as_posix().replace((BASE_DIR.as_posix() + '/'), '')}/payload.normalized.json) / "
            + f"[html](./{bundle_path.as_posix().replace((BASE_DIR.as_posix() + '/'), '')}/report.html) |"
        )

    lines.extend(["", "## Questionable Items", ""])
    for summary in summaries:
        if not summary["questionable_items"]:
            continue
        lines.append(f"### {summary['name']}")
        for item in summary["questionable_items"]:
            lines.append(f"- {item}")
        lines.append("")

    if lines[-1] != "":
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    bundle_root = Path(args.output_dir)
    bundle_root.mkdir(parents=True, exist_ok=True)
    cases = _load_property_file(args.property_file)

    summaries: List[Dict[str, Any]] = []
    for case in cases:
        payload = apply_payload_contract(run_full_comp_pipeline(case["redfin_url"]))
        report_html = _render_report_html(payload)
        report_checks = _extract_report_checks(payload, report_html)
        summary = _evaluate_property(case, payload, report_checks)
        summaries.append(summary)
        _write_bundle(bundle_root, payload, report_html, summary)

    review_index = _build_index_markdown(bundle_root, summaries)
    (BASE_DIR / "REVIEW_INDEX.md").write_text(review_index, encoding="utf-8")

    if args.json:
        print(json.dumps({"properties": summaries}, indent=2, sort_keys=True))
    else:
        for summary in summaries:
            print(f"[REVIEW] name={summary['name']!r}")
            print(f"[REVIEW] verdict={summary['verdict']!r}")
            print(f"[REVIEW] address={summary['address']!r}")
            print("[REVIEW] facts=" + json.dumps(summary["actual_facts"], sort_keys=True))
            print("[REVIEW] report_checks=" + json.dumps(summary["report_checks"], sort_keys=True))
            if summary["fact_mismatches"]:
                print(f"[REVIEW] fact_mismatches={summary['fact_mismatches']}")
            if summary["report_issues"]:
                print(f"[REVIEW] report_issues={summary['report_issues']}")
            if summary["questionable_items"]:
                print(f"[REVIEW] questionable_items={summary['questionable_items']}")

    return 0 if all(summary["verdict"] != "needs-fix" for summary in summaries) else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict

from app.ladbs_records_client import get_ladbs_records
from app.ladbs_scraper import get_ladbs_data
from app.redfin_scraper import get_redfin_data
from app.zimas_client import get_zimas_profile

DEFAULT_LUCERNE_URL = "https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003"
DEFAULT_LUCERNE_ADDRESS = "1120 S Lucerne Blvd, Los Angeles, CA 90019"
SUCCESS_SOURCES = {
    "zimas_profile_v1",
    "ladbs_records_v1",
    "ladbs_records_no_results",
    "ladbs_pin_v1",
    "ladbs_pin_no_results",
    "ladbs_plr_v6",
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a repeatable Lucerne-style smoke test for Redfin, ZIMAS, LADBS permits, and LADBS records."
    )
    parser.add_argument("--redfin-url", help="Redfin property URL to use as the primary smoke target.")
    parser.add_argument("--address", help="Optional direct address override for ZIMAS and LADBS records matching.")
    parser.add_argument("--json", action="store_true", help="Print the full smoke payload as JSON.")
    return parser


def _summarize_result(payload: Dict[str, Any]) -> None:
    redfin = payload["redfin"]
    zimas = payload["zimas"]
    permits = payload["ladbs_permits"]
    records = payload["ladbs_records"]

    print(f"[SMOKE] address={payload.get('address')!r}")
    print(f"[SMOKE] redfin_source={redfin.get('source')!r}")
    print(f"[SMOKE] zimas_source={zimas.get('source')!r}")
    print(f"[SMOKE] zimas_transport={zimas.get('transport')!r}")
    print(f"[SMOKE] zimas_pin={zimas.get('pin')!r}")
    print(f"[SMOKE] zimas_apn={zimas.get('apn')!r}")
    print(f"[SMOKE] zoning={((zimas.get('zoning_profile') or {}).get('zoning'))!r}")
    print(f"[SMOKE] general_plan={((zimas.get('zoning_profile') or {}).get('general_plan_land_use'))!r}")
    print(f"[SMOKE] community_plan={((zimas.get('planning_context') or {}).get('community_plan_area'))!r}")
    print(f"[SMOKE] nearest_fault={((zimas.get('hazard_profile') or {}).get('nearest_fault'))!r}")
    print(f"[SMOKE] permits_source={permits.get('source')!r}")
    print(f"[SMOKE] permits_count={len(permits.get('permits') or [])}")
    print(f"[SMOKE] records_source={records.get('source')!r}")
    print(f"[SMOKE] records_transport={records.get('transport')!r}")
    print(f"[SMOKE] records_count={len(records.get('documents') or [])}")
    print(
        f"[SMOKE] records_digital_count="
        f"{sum(1 for doc in (records.get('documents') or []) if doc.get('has_digital_image'))}"
    )
    print(
        f"[SMOKE] records_pdf_count="
        f"{sum(1 for doc in (records.get('documents') or []) if doc.get('pdf_url'))}"
    )
    for doc in (records.get("documents") or [])[:3]:
        print(
            "[SMOKE] record="
            + json.dumps(
                {
                    "doc_number": doc.get("doc_number"),
                    "doc_type": doc.get("doc_type"),
                    "doc_date": doc.get("doc_date"),
                    "pdf_url": doc.get("pdf_url"),
                },
                sort_keys=True,
            )
        )


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    redfin_url = args.redfin_url or DEFAULT_LUCERNE_URL
    address_override = args.address or DEFAULT_LUCERNE_ADDRESS

    redfin_data = get_redfin_data(redfin_url)
    address = redfin_data.get("address") or address_override
    apn = ((redfin_data.get("tax") or {}) or {}).get("apn")

    zimas_data = get_zimas_profile(apn=apn, address=address, redfin_url=redfin_url)
    permits_data = get_ladbs_data(apn=apn, address=address, redfin_url=redfin_url)
    records_data = get_ladbs_records(
        apn=apn,
        pin=zimas_data.get("pin"),
        address=address,
        redfin_url=redfin_url,
        zimas_profile=zimas_data,
    )

    payload = {
        "redfin_url": redfin_url,
        "address": address,
        "redfin": redfin_data,
        "zimas": zimas_data,
        "ladbs_permits": permits_data,
        "ladbs_records": records_data,
    }

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _summarize_result(payload)

    ok = (
        zimas_data.get("source") in SUCCESS_SOURCES
        and permits_data.get("source") in SUCCESS_SOURCES
        and records_data.get("source") in SUCCESS_SOURCES
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

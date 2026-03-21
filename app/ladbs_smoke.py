from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict

from app.ladbs_scraper import diagnose_browser_startup, get_driver_settings, get_ladbs_data

DEFAULT_LUCERNE_URL = "https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003"
DEFAULT_LUCERNE_ADDRESS = "1120 S Lucerne Blvd, Los Angeles, CA 90019"
SUCCESS_SOURCES = {
    "ladbs_pin_v1",
    "ladbs_pin_no_results",
    "ladbs_plr_v6",
    "ladbs_no_permits_found",
    "ladbs_no_results_page",
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a repeatable LADBS smoke test with either a Redfin URL or a direct address."
    )
    parser.add_argument(
        "--redfin-url",
        help="Redfin property URL to derive the LADBS search address from. Defaults to the Lucerne smoke case.",
    )
    parser.add_argument(
        "--address",
        help="Direct address input for isolating LADBS search behavior without Redfin address parsing.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Force LADBS_HEADLESS=0 for this smoke run.",
    )
    parser.add_argument(
        "--show-diagnostics",
        action="store_true",
        help="Run direct browser startup probes before the LADBS smoke.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the final LADBS result payload as JSON.",
    )
    parser.add_argument(
        "--strategy",
        choices=("pin-first", "plr"),
        default="pin-first",
        help="Choose the LADBS retrieval strategy. Defaults to the new pin-first path with PLR fallback.",
    )
    return parser


def _print_json_block(label: str, payload: Dict[str, Any]) -> None:
    print(f"[SMOKE] {label}")
    print(json.dumps(payload, indent=2, sort_keys=True))


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.redfin_url or args.address:
        redfin_url = args.redfin_url
        address = args.address
    else:
        redfin_url = DEFAULT_LUCERNE_URL
        address = DEFAULT_LUCERNE_ADDRESS

    if args.headed:
        os.environ["LADBS_HEADLESS"] = "0"

    print(f"[SMOKE] redfin_url={redfin_url!r}")
    print(f"[SMOKE] address={address!r}")
    print(f"[SMOKE] strategy={args.strategy!r}")
    _print_json_block("driver_settings", get_driver_settings())

    if args.show_diagnostics:
        _print_json_block("browser_startup_diagnostics", diagnose_browser_startup())

    result = get_ladbs_data(apn=None, address=address, redfin_url=redfin_url, strategy=args.strategy)
    if args.json:
        _print_json_block("ladbs_result", result)
    else:
        print(f"[SMOKE] source={result.get('source')}")
        print(f"[SMOKE] retrieval_strategy={result.get('retrieval_strategy')}")
        print(f"[SMOKE] fallback_used={result.get('fallback_used')}")
        print(f"[SMOKE] pin={result.get('pin')!r}")
        print(f"[SMOKE] pin_source={result.get('pin_source')!r}")
        print(f"[SMOKE] pin_route_source={result.get('pin_route_source')!r}")
        print(f"[SMOKE] note={result.get('note')}")
        print(f"[SMOKE] permit_count={len(result.get('permits', []))}")
        for permit in (result.get("permits") or [])[:3]:
            print(
                "[SMOKE] permit="
                + json.dumps(
                    {
                        "permit_number": permit.get("permit_number"),
                        "Type": permit.get("Type"),
                        "Status": permit.get("Status"),
                    },
                    sort_keys=True,
                )
            )

    if result.get("source") == "ladbs_stub_driver_error":
        _print_json_block("browser_startup_diagnostics", diagnose_browser_startup())

    return 0 if result.get("source") in SUCCESS_SOURCES else 1


if __name__ == "__main__":
    raise SystemExit(main())

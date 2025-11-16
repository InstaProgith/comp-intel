# app/cslb_lookup.py

from __future__ import annotations
from typing import Dict, Any, Optional

import requests
from bs4 import BeautifulSoup

# CSLB license-detail URL (license number interpolated into querystring).
# If CSLB changes this structure, only this file needs to be updated.
CSLB_DETAIL_URL = (
    "https://www2.cslb.ca.gov/OnlineServices/CheckLicenseII/LicenseDetail.aspx?LicNum={lic}"
)


def lookup_cslb_license(lic: str) -> Optional[Dict[str, Any]]:
    """
    Look up a CA contractor license on CSLB and extract:
      - business_name
      - phone
      - address
      - detail_url

    Returns None if the lookup fails or if we can't parse the expected layout.
    """
    if not lic:
        return None

    lic = lic.strip()
    url = CSLB_DETAIL_URL.format(lic=lic)

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"[WARN] CSLB lookup failed: {e}")
        return None

    try:
        soup = BeautifulSoup(resp.text, "lxml")

        # CSLB uses labels like "Business Information" in a heading above the block.
        h2 = soup.find("h2", string=lambda s: s and "Business Information" in s)
        if not h2:
            return None

        container = h2.find_next("div")
        if not container:
            return None

        text = container.get_text("\n", strip=True)
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        if not lines:
            return None

        # First line is usually the business name.
        name = lines[0]
        phone = ""
        address_lines = []

        for ln in lines[1:]:
            if "Business Phone Number:" in ln:
                phone = ln.split("Business Phone Number:")[-1].strip()
            else:
                address_lines.append(ln)

        address = ", ".join(address_lines) if address_lines else ""

        return {
            "source": "cslb",
            "license_number": lic,
            "business_name": name,
            "phone": phone,
            "address": address,
            "detail_url": url,
        }
    except Exception as e:
        print(f"[WARN] CSLB parsing failed: {e}")
        return None

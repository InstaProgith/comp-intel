from __future__ import annotations

from pathlib import Path
import shutil
from unittest import TestCase, mock

from app import redfin_scraper

TEST_TMP_ROOT = Path(__file__).resolve().parent.parent / "data" / "test-temp"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)


SAMPLE_REDfin_HTML = """
<html>
  <body>
    <div data-rf-test-id="abp-streetLine">3440 Cattaraugus Ave, Culver City, CA 90232</div>
    <div data-rf-test-id="abp-beds">4 Beds</div>
    <div data-rf-test-id="abp-baths">3 Baths</div>
    <div data-rf-test-id="abp-sqFt">3,595 Sq. Ft.</div>
    <div data-rf-test-id="abp-price">$3,932,090</div>
    <div>6,494 Sq. Ft. Lot</div>
    <div>Property Type: Single Family Residential</div>
    <div>Year Built: 2025</div>
    <div>APN: 123-456-789</div>
  </body>
</html>
"""

SAMPLE_SOLD_REDFIN_HTML = """
<html>
  <head>
    <meta
      name="description"
      content="Sold: 2 beds, 1 bath, 1008 sq. ft. house located at 1120 S Lucerne Blvd, Los Angeles, CA 90019 sold for $800,000 on Sep 5, 2025."
    />
  </head>
  <body>
    <div data-rf-test-id="abp-streetLine">1120 S Lucerne Blvd, Los Angeles, CA 90019</div>
    <div data-rf-test-id="abp-beds">2 Beds</div>
    <div data-rf-test-id="abp-baths">1 Bath</div>
    <div data-rf-test-id="abp-sqFt">1,008 Sq. Ft.</div>
    <div data-rf-test-id="abp-price">$1,057,509</div>
    <div>8,379 Sq. Ft. Lot</div>
    <div>Property Type: Single Family Residential</div>
    <div>Built in 1922</div>
    <div>OFF MARKET</div>
    <div>SOLD SEP 5, 2025</div>
  </body>
</html>
"""


class RedfinScraperTests(TestCase):
    def test_get_redfin_data_keeps_listing_lot_size_when_public_record_lot_is_missing(self) -> None:
        test_dir = TEST_TMP_ROOT / "redfin-scraper-test"
        shutil.rmtree(test_dir, ignore_errors=True)
        test_dir.mkdir(parents=True, exist_ok=True)
        html_path = test_dir / "sample_redfin.html"
        try:
            html_path.write_text(SAMPLE_REDfin_HTML, encoding="utf-8")

            with mock.patch.object(redfin_scraper, "fetch_redfin_html", return_value=html_path):
                data = redfin_scraper.get_redfin_data(
                    "https://www.redfin.com/CA/Culver-City/3440-Cattaraugus-Ave-90232/home/6721247"
                )
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

        self.assertEqual(data["lot_sf"], 6494.0)
        self.assertEqual(data["list_price"], 3932090.0)
        self.assertEqual(data["address"], "3440 Cattaraugus Ave, Culver City, CA 90232")
        self.assertEqual(data["lot_summary"], "Lot: 6,494 SF (0.15 acres)")

    def test_get_redfin_data_ignores_estimate_banner_on_sold_pages(self) -> None:
        test_dir = TEST_TMP_ROOT / "redfin-sold-test"
        shutil.rmtree(test_dir, ignore_errors=True)
        test_dir.mkdir(parents=True, exist_ok=True)
        html_path = test_dir / "sold_redfin.html"
        try:
            html_path.write_text(SAMPLE_SOLD_REDFIN_HTML, encoding="utf-8")

            with mock.patch.object(redfin_scraper, "fetch_redfin_html", return_value=html_path):
                data = redfin_scraper.get_redfin_data(
                    "https://www.redfin.com/CA/Los-Angeles/1120-S-Lucerne-Blvd-90019/home/6911003"
                )
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

        self.assertIsNone(data["list_price"])
        self.assertEqual(data["sold_banner"], "SEP 5, 2025")
        self.assertEqual(data["timeline"][0]["event"], "sold")
        self.assertEqual(data["timeline"][0]["price"], 800000)
        self.assertEqual(data["address"], "1120 S Lucerne Blvd, Los Angeles, CA 90019")
        self.assertEqual(data["year_built"], 1922)

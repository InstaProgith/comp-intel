from __future__ import annotations

from unittest import TestCase

from app import ladbs_records_client


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text
        self.status_code = 200
        self.url = "https://ladbsdoc.lacity.org/IDISPublic_Records/idis/DocumentSearch.aspx?SearchType=DCMT_ASSR_NEW"

    def raise_for_status(self) -> None:
        return None


class _FakeSession:
    def __init__(self, responses):
        self.headers = {}
        self.responses = list(responses)
        self.calls = []

    def get(self, url: str, timeout=None, allow_redirects=True):  # type: ignore[override]
        self.calls.append({"method": "GET", "url": url, "timeout": timeout})
        return _FakeResponse(self.responses.pop(0))

    def post(self, url: str, data=None, timeout=None):  # type: ignore[override]
        self.calls.append({"method": "POST", "url": url, "data": data, "timeout": timeout})
        return _FakeResponse(self.responses.pop(0))


SEARCH_FORM_HTML = """
<html>
  <body>
    <form id="DocSearch">
      <input type="hidden" name="__VIEWSTATE" value="vs-search" />
      <input type="hidden" name="__EVENTVALIDATION" value="ev-search" />
      <input type="hidden" name="rptPanel" value="no" />
      <input type="hidden" name="AllSelected" value="None" />
      <input type="hidden" name="PageNavigate" value="false" />
      <input type="hidden" name="ShowNavBarOnly" value="false" />
      <input type="hidden" name="BlockNumber" value="0" />
      <input type="hidden" name="TotBlocks" value="0" />
      <input type="hidden" name="PrinterFriendlyVisible" value="false" />
      <input type="hidden" name="NoStrName" value="false" />
      <input type="hidden" name="HistAddr" value="False" />
      <input type="hidden" name="SortByRbf" value="False" />
      <input type="hidden" name="__EVENTTARGET" value="" />
      <input type="hidden" name="__EVENTARGUMENT" value="" />
      <input type="text" name="Assessor$txtAssessorNoBook" value="" />
      <input type="text" name="Assessor$txtAssessorNoPage" value="" />
      <input type="text" name="Assessor$txtAssessorNoParcel" value="" />
      <select name="DocDateAssessorFrom$cboMonth"><option selected="selected" value="    ">    </option></select>
      <select name="DocDateAssessorFrom$cboDay"><option selected="selected" value="    ">    </option></select>
      <select name="DocDateAssessorFrom$cboYear"><option selected="selected" value=" "> </option></select>
      <input type="submit" name="btnSearchAssessor" value="Search" />
      <input type="submit" name="btnAssessorClear" value="Clear" />
      <input type="submit" name="DocDateAssessorFrom$btnClearDate" value="Clear Date" />
    </form>
  </body>
</html>
"""

ADDRESS_SELECTION_HTML = """
<html>
  <body>
    <form id="DocSearch">
      <input type="hidden" name="__VIEWSTATE" value="vs-address" />
      <input type="hidden" name="__EVENTVALIDATION" value="ev-address" />
      <input type="hidden" name="SortByRbf" value="False" />
      <input type="checkbox" name="chkAddress1All" />
      <table id="dgAddress1">
        <tr><td></td><td>Beg Nbr</td><td>End Nbr</td><td>Dir</td><td>Str Name</td><td>Str Type</td></tr>
        <tr>
          <td><input type="checkbox" name="chkAddress1" value="AR1120~~~~~~~~~~~~S~LUCERNE~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~BLVD~~~~~~~~~~~~~~~~~~~~~~~~~~~~~" /></td>
          <td>1120</td><td></td><td>S</td><td>LUCERNE</td><td>BLVD</td>
        </tr>
      </table>
      <input type="submit" name="btnNext2" value="Continue" />
      <input type="submit" name="btnNext3" value="Continue" />
    </form>
  </body>
</html>
"""

RESULTS_HTML = """
<html>
  <body>
    <span id="lblSearchCriteria">BOOK NUMBER: 5082 PAGE NUMBER: 004 PARCEL NUMBER: 025</span>
    <select><option>All</option><option selected="selected">1120 S LUCERNE BLVD</option></select>
    <table id="grdIdisResult">
      <tr>
        <td><input name="grdIdisResult$ctl01$chkCheckAll" type="checkbox" /></td>
        <td>Document Type</td><td>Sub Type</td><td>Doc Date</td><td>User Doc Number</td><td>Digital Image</td>
      </tr>
      <tr>
        <td><input name="grdIdisResult$ctl02$chkReportPrint" type="checkbox" /></td>
        <td>
          <a href="JavaScript:OpenWindow('51122062','Visible','{45aef7c1-7e3f-49ef-973d-f7f9d57c6e6b},')">BUILDING PERMIT</a>
          <input type="hidden" name="grdIdisResult$ctl02$hidComments" value="ADDITION OF 56 SQ FT CLOSET TO AN EXISTING SINGLE FAMILY DWELLING." />
        </td>
        <td><a href="JavaScript:OpenWindow('51122062','Visible','{45aef7c1-7e3f-49ef-973d-f7f9d57c6e6b},')">BLDG-ADDITION</a></td>
        <td><a href="JavaScript:OpenWindow('51122062','Visible','{45aef7c1-7e3f-49ef-973d-f7f9d57c6e6b},')">10/27/2006</a></td>
        <td><a href="JavaScript:OpenWindow('51122062','Visible','{45aef7c1-7e3f-49ef-973d-f7f9d57c6e6b},')">06014-70000-09673</a></td>
        <td><a href="JavaScript:OpenDocument('{45aef7c1-7e3f-49ef-973d-f7f9d57c6e6b},')">image</a></td>
      </tr>
    </table>
    Page 1 of 1
  </body>
</html>
"""

IMAGE_LIST_HTML = """
<html>
  <body onload="javascript:JavaViewDocument('{45aef7c1-7e3f-49ef-973d-f7f9d57c6e6b}','IDIS',800,600);">
    <form id="ImageList"></form>
  </body>
</html>
"""


class LadbsRecordsClientTests(TestCase):
    def test_split_apn_returns_book_page_parcel(self) -> None:
        self.assertEqual(
            ladbs_records_client.split_apn("5082004025"),
            {"book": "5082", "page": "004", "parcel": "025"},
        )

    def test_collect_form_payload_excludes_unclicked_submit_controls(self) -> None:
        soup = ladbs_records_client.BeautifulSoup(SEARCH_FORM_HTML, "lxml")
        payload = ladbs_records_client._collect_form_payload(
            soup.find("form"),
            clicked_button_name="btnSearchAssessor",
            clicked_button_value="Search",
        )

        self.assertNotIn("btnAssessorClear", payload)
        self.assertNotIn("DocDateAssessorFrom$btnClearDate", payload)
        self.assertEqual(payload["btnSearchAssessor"], "Search")

    def test_parse_address_candidates_extracts_checkbox_and_label(self) -> None:
        candidates = ladbs_records_client._parse_address_candidates(ADDRESS_SELECTION_HTML)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["checkbox_name"], "chkAddress1")
        self.assertEqual(candidates[0]["label"], "1120 S LUCERNE BLVD")

    def test_parse_records_results_extracts_links_and_description(self) -> None:
        parsed = ladbs_records_client._parse_records_results(RESULTS_HTML)

        self.assertEqual(len(parsed["documents"]), 1)
        self.assertEqual(parsed["documents"][0]["doc_number"], "06014-70000-09673")
        self.assertEqual(parsed["documents"][0]["record_id"], "51122062")
        self.assertTrue(parsed["documents"][0]["has_digital_image"])
        self.assertIn("Report.aspx", parsed["documents"][0]["summary_url"])

    def test_get_ladbs_records_runs_browserless_flow(self) -> None:
        session = _FakeSession(
            [
                "<html></html>",
                SEARCH_FORM_HTML,
                ADDRESS_SELECTION_HTML,
                RESULTS_HTML,
                "<html></html>",
                IMAGE_LIST_HTML,
            ]
        )

        result = ladbs_records_client.get_ladbs_records(
            apn="5082004025",
            address="1120 S Lucerne Blvd, Los Angeles, CA 90019",
            pin="129B185   131",
            session=session,
        )

        self.assertEqual(result["source"], "ladbs_records_v1")
        self.assertEqual(len(result["documents"]), 1)
        self.assertEqual(result["documents"][0]["doc_number"], "06014-70000-09673")
        self.assertIn("StPdfViewer.aspx", result["documents"][0]["pdf_url"])

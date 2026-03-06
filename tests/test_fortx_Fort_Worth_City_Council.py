from datetime import datetime
from os.path import dirname, join

import pytest
import requests
import scrapy
from city_scrapers_core.constants import CITY_COUNCIL
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.fortx_Fort_Worth_City_Council import (
    FortxFortWorthCityCouncilSpider,
)

meetings_items = file_response(
    join(
        dirname(__file__), "files", "fortx_Fort_Worth_City_Council_meeting_items.json"
    ),
    url="https://www.fortworthtexas.gov/ocapi/calendars/getcalendaritems",
)

meetings_detail = file_response(
    join(
        dirname(__file__), "files", "fortx_Fort_Worth_City_Council_meeting_details.json"
    ),
    url=(
        "https://www.fortworthtexas.gov/ocapi/get/contentinfo?calendarId=8a8add9a-3fd0-4b39-9a3e-d58e98e27acc"  # noqa
        "&contentId=57212572-47cc-44e2-9da3-8e0d88b7c003&language=en-US&currentDateTime=14/10/2025%2009:00:00%20AM"  # noqa
        "&mainContentId=57212572-47cc-44e2-9da3-8e0d88b7c003"
    ),
)

spider = FortxFortWorthCityCouncilSpider()


class MockDetailPageResponse:
    def __init__(self, text):
        self.text = text


DETAIL_HTML = """
<div class="side-box consultation-snapshot">
    <h2 class="side-box-title">
        Current Agenda
    </h2>
    <div class="side-box-content">
        <div class="side-box-section body-content">
            <p><a title="12-02-2025 Audit and Finance Committee Agenda" href="/files/assets/public/v/2/city-secretary/documents/calendar/2025-agendas/city-council/committee/audit-ampfinance/12-02-2025-audit-and-finance-committee-agenda.pdf" target="_self" class="document ext-pdf"><i aria-hidden="true"></i>12-02-2025 Audit and Finance Committee Agenda<span class="file-info">(PDF,&nbsp;174KB)</span></a></p> # noqa
        </div>
    </div>
</div>
"""

original_get = requests.get
requests.get = lambda *args, **kwargs: MockDetailPageResponse(DETAIL_HTML)

freezer = freeze_time("2026-03-06")
freezer.start()

parsed_items = []

for req in spider.parse(meetings_items):
    if isinstance(req, scrapy.Request):
        meeting_detail_item = spider.parse_meeting(
            meetings_detail, req.cb_kwargs["item"]
        )
        parsed_items.extend(meeting_detail_item)

freezer.stop()
requests.get = original_get

"""
The spider for this site is set to fetch meeting items for the entire year.
To make the test less time consuming, the number of meetings to be tested is
limited to 13 items.
"""


def test_count():
    assert len(parsed_items) == 13


def test_title():
    assert parsed_items[0]["title"] == "Audit & Finance Committee"


def test_description():
    assert (
        parsed_items[0]["description"]
        == "Audit & Finance Committee Meeting. Veiw agenda and meeting details."
    )


def test_start():
    assert parsed_items[0]["start"] == datetime(2025, 10, 14, 9, 0)


def test_end():
    assert parsed_items[0]["end"] is None


def test_time_notes():
    assert (
        parsed_items[0]["time_notes"]
        == "Please check the meeting description for details on the start time"
    )


def test_id():
    assert (
        parsed_items[0]["id"]
        == "fortx_Fort_Worth_City_Council/202510140900/x/audit_finance_committee"
    )


def test_status():
    assert parsed_items[0]["status"] == "passed"


def test_location():
    assert parsed_items[0]["location"] == {
        "name": "New City Hall",
        "address": "100 Fort Worth Trail, Fort Worth, 76102",
    }


def test_source():
    assert parsed_items[0]["source"] == (
        "https://www.fortworthtexas.gov/departments/citysecretary/"
        "events/audit-committee-2025"
    )


def test_links():
    assert parsed_items[0]["links"] == [
        {
            "href": "https://www.fortworthtexas.gov//files/assets/public/v/2/city-secretary/documents/calendar/2025-agendas/city-council/committee/audit-ampfinance/12-02-2025-audit-and-finance-committee-agenda.pdf",  # noqa
            "title": "Agenda",
        }
    ]


def test_classification():
    assert parsed_items[0]["classification"] == CITY_COUNCIL


@pytest.mark.parametrize("item", parsed_items)
def test_all_day(item):
    assert item["all_day"] is False

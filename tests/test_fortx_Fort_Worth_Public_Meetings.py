from datetime import datetime
from os.path import dirname, join

import pytest
import scrapy
from city_scrapers_core.constants import CITY_COUNCIL
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.fortx_Fort_Worth_Public_Meetings import (
    FortxFortWorthPublicMeetingsSpider,
)

meetings_items = file_response(
    join(
        dirname(__file__),
        "files",
        "fortx_Fort_Worth_Public_Meetings_meeting_items.json",
    ),
    url="https://www.fortworthtexas.gov/ocapi/calendars/getcalendaritems",
)

meetings_detail = file_response(
    join(
        dirname(__file__),
        "files",
        "fortx_Fort_Worth_Public_Meetings_meeting_details.json",
    ),
    url=(
        "https://www.fortworthtexas.gov/ocapi/get/contentinfo?calendarId=8efac0b6-9ea3-402e-b7d9-e9e71a2a34a0"  # noqa
        "&contentId=9c1c703d-0beb-46b1-9776-4bd79b26cefc&language=en-US&currentDateTime=01/02/2024%2006:00:00%20PM"  # noqa
        "&mainContentId=00000000-0000-0000-0000-000000000000"
    ),
)

spider = FortxFortWorthPublicMeetingsSpider()

freezer = freeze_time("2024-12-19")
freezer.start()

parsed_items = []
for req in spider.parse(meetings_items):
    if isinstance(req, scrapy.Request):
        meeting_detail_item = spider.parse_meeting(
            meetings_detail, start_time=req.cb_kwargs["start_time"]
        )
        parsed_items.extend(meeting_detail_item)

freezer.stop()

"""
The spider for this site is set to fetch meeting items for the entire year.
To make the test less time consuming, the number of meetings to be tested is
limited to 6 items.
"""


def test_count():
    assert len(parsed_items) == 6


def test_title():
    assert parsed_items[0]["title"] == "TPW Meeting Glasgow and Oak Grove Roads"


def test_description():
    assert parsed_items[0]["description"] == (
        "Join us at the upcoming public meeting to learn about street upgrades. "
        "This project is located in Council District 8.The City of Fort Worth "
        "Transportation and Public Works (TPW) Department will present upcoming "
        "street improvements at theHighland Hills Neighborhood Association meeting."
        "Thursday, February 1, 2024 at 6:00 p.m."
    )


def test_start():
    assert parsed_items[0]["start"] == datetime(2024, 2, 1, 18, 0)


def test_end():
    assert parsed_items[0]["end"] is None


def test_time_notes():
    assert (
        parsed_items[0]["time_notes"]
        == "Please check the meeting description for details on the start time"
    )


def test_id():
    assert parsed_items[0]["id"] == (
        "fortx_Fort_Worth_Public_Meetings/202402011800/x/"
        "tpw_meeting_glasgow_and_oak_grove_roads"
    )


def test_status():
    assert parsed_items[0]["status"] == "passed"


def test_location():
    assert parsed_items[0]["location"] == {
        "name": "Highland Hills Community Center",
        "address": "1600 Glasgow Road, Fort Worth, 76134",
    }


def test_source():
    assert parsed_items[0]["source"] == (
        "https://www.fortworthtexas.gov/departments/cip/events/glasgow-oak-grove-meeting-tpw"  # noqa
    )


def test_links():
    assert parsed_items[0]["links"] == []


def test_classification():
    assert parsed_items[0]["classification"] == CITY_COUNCIL


@pytest.mark.parametrize("item", parsed_items)
def test_all_day(item):
    assert item["all_day"] is False

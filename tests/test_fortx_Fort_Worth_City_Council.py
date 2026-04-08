from datetime import datetime
from os.path import dirname, join

import pytest
import scrapy
from city_scrapers_core.constants import CITY_COUNCIL
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.fortx_Fort_Worth_City_Council import (
    FortxFortWorthCityCouncilSpider,
)


@pytest.fixture(scope="module")
def spider():
    return FortxFortWorthCityCouncilSpider()


@pytest.fixture(scope="module")
def meetings_items_response():
    return file_response(
        join(
            dirname(__file__),
            "files",
            "fortx_Fort_Worth_City_Council_meeting_items.json",
        ),
        url="https://www.fortworthtexas.gov/ocapi/calendars/getcalendaritems",
    )


@pytest.fixture(scope="module")
def meetings_detail_response():
    return file_response(
        join(
            dirname(__file__),
            "files",
            "fortx_Fort_Worth_City_Council_meeting_details.json",
        ),
        url=(
            "https://www.fortworthtexas.gov/ocapi/get/contentinfo"
            "?calendarId=8a8add9a-3fd0-4b39-9a3e-d58e98e27acc"
            "&contentId=57212572-47cc-44e2-9da3-8e0d88b7c003&language=en-US"
            "&currentDateTime=14/10/2025%2009:00:00%20AM"
            "&mainContentId=57212572-47cc-44e2-9da3-8e0d88b7c003"
        ),
    )


@pytest.fixture(scope="module")
def parsed_items(spider, meetings_items_response, meetings_detail_response):  # noqa
    items = []
    with freeze_time("2026-03-06"):
        for req in spider.parse(meetings_items_response.json()):
            if isinstance(req, scrapy.Request):
                meeting_detail_item = spider.parse_meeting(
                    meetings_detail_response, req.cb_kwargs["item"]
                )
                items.extend(meeting_detail_item)

    return items


def test_count(parsed_items):
    assert len(parsed_items) == 13


def test_title(parsed_items):
    assert parsed_items[0]["title"] == "Audit & Finance Committee"


def test_description(parsed_items):
    assert (
        parsed_items[0]["description"]
        == "Audit & Finance Committee Meeting. Veiw agenda and meeting details."
    )


def test_start(parsed_items):
    assert parsed_items[0]["start"] == datetime(2025, 10, 14, 9, 0)


def test_end(parsed_items):
    assert parsed_items[0]["end"] is None


def test_time_notes(parsed_items):
    assert (
        parsed_items[0]["time_notes"]
        == "Please check the meeting description for details on the start time"
    )


def test_id(parsed_items):
    assert (
        parsed_items[0]["id"]
        == "fortx_Fort_Worth_City_Council/202510140900/x/audit_finance_committee"
    )


def test_status(parsed_items):
    assert parsed_items[0]["status"] == "passed"


def test_location(parsed_items):
    assert parsed_items[0]["location"] == {
        "name": "New City Hall",
        "address": "100 Fort Worth Trail, Fort Worth, 76102",
    }


def test_source(parsed_items):
    assert (
        parsed_items[0]["source"]
        == "https://www.fortworthtexas.gov/departments/citysecretary/events/audit-committee-2025"  # noqa
    )


def test_links(parsed_items):
    assert parsed_items[0]["links"] == [
        {
            "title": "Meeting Details",
            "href": "https://www.fortworthtexas.gov/departments/citysecretary/events/audit-committee-2025",  # noqa
        }
    ]


def test_classification(parsed_items):
    assert parsed_items[0]["classification"] == CITY_COUNCIL


def test_all_day(parsed_items):
    for item in parsed_items:
        assert item["all_day"] is False

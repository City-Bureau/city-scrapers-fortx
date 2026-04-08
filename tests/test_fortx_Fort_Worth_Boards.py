from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import COMMISSION, PASSED
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.fortx_Fort_Worth_Boards import FortxFortWorthBoardsSpider

test_response = file_response(
    join(dirname(__file__), "files", "fortx_Fort_Worth_Boards.json"),
    url="https://www.fortworthtexas.gov/ocapi/calendars/getcalendaritems",  # noqa
)


test_response_detail = file_response(
    join(dirname(__file__), "files", "fortx_Fort_Worth_Boards_meeting_details.json"),
    url="https://www.fortworthtexas.gov/ocapi/calendars/getcalendaritems?Ids=788ffb59-05d1-457d-b9dd-423d4b95a06e&LanguageCode=en-US&startDate=2026-01-01&endDate=2026-12-31",  # noqa
)


@pytest.fixture
def spider():
    return FortxFortWorthBoardsSpider()


@pytest.fixture
def get_items(spider):
    with freeze_time("2026-03-09"):
        return [request.cb_kwargs["item"] for request in spider.parse(test_response)]


@pytest.fixture
def parsed_items(spider, get_items):
    return [
        item for item in spider.parse_meeting(test_response_detail, item=get_items[0])
    ]


def test_count(parsed_items):
    assert len(parsed_items) == 1


def test_title(parsed_items):
    assert parsed_items[0]["title"] == "2025 Building Standards Commission (BSC)"


def test_description(parsed_items):
    assert (
        parsed_items[0]["description"]
        == "2025 Meeting Calendar. View the past agendas and meeting details."
    )


def test_start(parsed_items):
    assert parsed_items[0]["start"] == datetime(
        2025, 6, 23, 9, 0, tzinfo=parsed_items[0]["start"].tzinfo
    )


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
        == "fortx_Fort_Worth_Boards/202506230900/x/2025_building_standards_commission_bsc_"  # noqa
    )


def test_status(parsed_items):
    assert parsed_items[0]["status"] == PASSED


def test_location(parsed_items):
    assert parsed_items[0]["location"] == {
        "name": "City Hall",
        "address": "200 Texas St., Fort Worth, 76102",
    }


def test_source(parsed_items):
    assert (
        parsed_items[0]["source"]
        == "https://www.fortworthtexas.gov/departments/citysecretary/events/building-standards-commission-meeting-2025"  # noqa
    )


def test_links(parsed_items):
    assert parsed_items[0]["links"] == [
        {
            "title": "Meeting Details",
            "href": "https://www.fortworthtexas.gov/departments/citysecretary/events/building-standards-commission-meeting-2025",  # noqa
        }
    ]


def test_classification(parsed_items):
    assert parsed_items[0]["classification"] == COMMISSION


def test_all_day(parsed_items):
    assert parsed_items[0]["all_day"] is False

from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import COMMISSION
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
    assert parsed_items[0]["start"] == datetime(2025, 6, 23, 9, 0)


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
    assert parsed_items[0]["status"] == "cancelled"


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
            "title": "10-27-2025 BSC Agenda",
            "href": "https://www.fortworthtexas.gov//files/assets/public/v/2/city-secretary/documents/calendar/2025-agendas/bampc/bsc/10-27-2025-bsc-agenda.pdf",  # noqa
        },
        {
            "title": "09-22-2025 BSC Agenda",
            "href": "https://www.fortworthtexas.gov//files/assets/public/v/3/city-secretary/documents/calendar/2025-agendas/bampc/bsc/09-22-2025-bsc-agenda.pdf",  # noqa
        },
        {
            "title": "08-25-2025 Canceled BSC Agenda",
            "href": "https://www.fortworthtexas.gov//files/assets/public/v/4/city-secretary/documents/calendar/2025-agendas/bampc/bsc/08-25-2025-canceled-bsc-stamped-agenda.pdf",  # noqa
        },
        {
            "title": "07-28-2025 BSC Agenda",
            "href": "https://www.fortworthtexas.gov//files/assets/public/v/6/city-secretary/documents/calendar/2025-agendas/bampc/bsc/07-28-2025-bsc-agenda.pdf",  # noqa
        },
        {
            "title": "06-23-2025 BSC Agenda",
            "href": "https://www.fortworthtexas.gov//files/assets/public/v/2/city-secretary/documents/calendar/2025-agendas/bampc/bsc/06-23-2025-bsc-agenda.pdf",  # noqa
        },
        {
            "title": "05-19-2025 BSC Agenda",
            "href": "https://www.fortworthtexas.gov//files/assets/public/v/5/city-secretary/documents/calendar/2025-agendas/bampc/bsc/05-19-2025-bsc-agenda.pdf",  # noqa
        },
        {
            "title": "04-28-2025 BSC Agenda",
            "href": "https://www.fortworthtexas.gov//files/assets/public/v/2/city-secretary/documents/calendar/2025-agendas/bampc/bsc/04-28-2025-bsc-agenda.pdf",  # noqa
        },
        {
            "title": "03-24-2025 BSC Agenda",
            "href": "https://www.fortworthtexas.gov//files/assets/public/v/2/city-secretary/documents/calendar/2025-agendas/bampc/bsc/03-24-2025-bsc-agenda.pdf",  # noqa
        },
        {
            "title": "01-27-2025-BSC-Agenda",
            "href": "https://www.fortworthtexas.gov//files/assets/public/v/4/city-secretary/documents/calendar/2025-agendas/bampc/bsc/01-27-2025-bsc-agenda.pdf",  # noqa
        },
        {
            "title": "02-24-2025 BSC Agenda",
            "href": "https://www.fortworthtexas.gov//files/assets/public/v/4/city-secretary/documents/calendar/2025-agendas/bampc/bsc/02-24-2025-bsc-agenda.pdf",  # noqa
        },
        {
            "title": "12-15-2025 BSC Agenda",
            "href": "https://www.fortworthtexas.gov//files/assets/public/v/3/city-secretary/documents/calendar/2025-agendas/bampc/bsc/12-15-2025-bsc-agenda.pdf",  # noqa
        },
    ]


def test_classification(parsed_items):
    assert parsed_items[0]["classification"] == COMMISSION


def test_all_day(parsed_items):
    assert parsed_items[0]["all_day"] is False

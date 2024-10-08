from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import COMMISSION
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.fortx_Fort_Worth_Boards import FortxFortWorthBoardsSpider

test_response = file_response(
    join(dirname(__file__), "files", "fortx_Fort_Worth_Boards.json"),
    url="https://www.fortworthtexas.gov/ocapi/calendars/getcalendaritems?Ids=788ffb59-05d1-457d-b9dd-423d4b95a06e&LanguageCode=en-US",  # noqa
)
spider = FortxFortWorthBoardsSpider()

freezer = freeze_time("2024-10-04")
freezer.start()

parsed_items = [item for item in spider.parse(test_response)]

freezer.stop()


def test_count():
    assert len(parsed_items) == 18


def test_title():
    assert (
        parsed_items[0]["title"] == "Notice of Public Comment for Brownsfields Program"
    )
    assert (
        parsed_items[1]["title"]
        == "DFW International Airport Board Operations Committee"
    )


def test_description():
    assert (
        parsed_items[0]["description"]
        == "Notice of Public Comment for Analysis of Brownfields Cleanup Alternatives (ABCA) document prepared by the Brownsfields Program"  # noqa
    )
    assert (
        parsed_items[1]["description"]
        == "DFW International Airport Board Operations Committee"
    )


def test_start():
    assert parsed_items[0]["start"] == datetime(2024, 10, 1, 0, 0)
    assert parsed_items[1]["start"] == datetime(2024, 10, 1, 12, 30)


def test_end():
    assert parsed_items[0]["end"] is None


def test_time_notes():
    assert parsed_items[0]["time_notes"] == ""


def test_id():
    assert (
        parsed_items[0]["id"]
        == "fortx_Fort_Worth_Boards/202410010000/x/notice_of_public_comment_for_brownsfields_program"  # noqa
    )


def test_status():
    assert parsed_items[0]["status"] == "passed"


def test_location():
    assert parsed_items[0]["location"] == {"name": "", "address": "Fort Worth, TX"}
    assert parsed_items[1]["location"] == {
        "name": "Board Room – DFW Headquarters Building",
        "address": "2400 Aviation Dr., DFW Airport, 75261, TX",
    }
    assert parsed_items[5]["location"] == {
        "name": "City Hall",
        "address": "200 Texas St, Fort Worth, 76102, TX",
    }


def test_source():
    assert (
        parsed_items[0]["source"]
        == "https://www.fortworthtexas.gov/calendar/boards-commission"
    )


def test_links():
    assert parsed_items[0]["links"] == [
        {
            "title": "Link",
            "href": "https://www.fortworthtexas.gov/departments/citysecretary/events/2024-Public-Notice-Public-Comment",  # noqa
        }
    ]


def test_classification():
    assert parsed_items[0]["classification"] == COMMISSION


@pytest.mark.parametrize("item", parsed_items)
def test_all_day(item):
    assert item["all_day"] is False

from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import BOARD
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.fortx_Castleberry_ISD import FortxCastleberryIsdSpider

test_response = file_response(
    join(dirname(__file__), "files", "fortx_Castleberry_ISD.html"),
    url="https://meetings.boardbook.org/Public/Organization/1090",
)
spider = FortxCastleberryIsdSpider()

freezer = freeze_time("2026-02-02")
freezer.start()

parsed_items = [item for item in spider.parse(test_response)]

freezer.stop()


def test_count():
    assert len(parsed_items) >= 347


def test_title():
    assert parsed_items[0]["title"] == "Special Meeting"


def test_description():
    assert parsed_items[0]["description"] == ""


def test_start():
    assert parsed_items[0]["start"] == datetime(2026, 1, 20, 18, 0)


def test_end():
    assert parsed_items[0]["end"] is None


@pytest.mark.parametrize(
    "item_index, expected_notes",
    [
        (0, ""),
        (
            1,
            "Will begin immediately following the Public Hearing; "
            "Start time not listed; estimated from same-day meeting",
        ),
    ],
)
def test_time_notes(item_index, expected_notes):
    assert parsed_items[item_index]["time_notes"] == expected_notes


def test_id():
    assert (
        parsed_items[0]["id"] == "fortx_Castleberry_ISD/202601201800/x/special_meeting"
    )


def test_status():
    assert parsed_items[0]["status"] == "passed"


def test_location():
    assert parsed_items[0]["location"] == {
        "name": "Castleberry Board Room",
        "address": "5228 Ohio Garden, Fort Worth, TX 76114",
    }


def test_source():
    assert (
        parsed_items[0]["source"]
        == "https://meetings.boardbook.org/Public/Organization/1090"
    )


def test_links():
    assert parsed_items[0]["links"] == [
        {
            "title": "Agenda",
            "href": "https://meetings.boardbook.org/Public/Agenda/1090?meeting=726957",  # noqa
        },
        {
            "title": "Projector",
            "href": "https://meetings.boardbook.org/Public/Projector/1090?meeting=726957",  # noqa
        },
    ]


def test_classification():
    assert parsed_items[0]["classification"] == BOARD


@pytest.mark.parametrize("item", parsed_items)
def test_all_day(item):
    assert item["all_day"] is False

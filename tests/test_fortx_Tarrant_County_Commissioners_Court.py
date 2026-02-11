from datetime import datetime
from os.path import dirname, join

import pytest
import scrapy
from city_scrapers_core.constants import COMMISSION
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.fortx_Tarrant_County_Commissioners_Court import (
    FortxTarrantCountyCommissionersCourtSpider,
)


@pytest.fixture(scope="module")
def spider():
    return FortxTarrantCountyCommissionersCourtSpider()


@pytest.fixture(scope="module")
def archived_meetings_data():
    response = file_response(
        join(
            dirname(__file__),
            "files",
            "fortx_Tarrant_County_Commissioners_Court_archived_meetings.json",
        ),
        url="https://tarrant-agendamanagement-public.techsharetx.gov/publicportal/api/meetings/readArchived",  # noqa
    )
    return response.json().get("data", [])


@pytest.fixture(scope="module")
def remaining_archived_meetings_data():
    return file_response(
        join(
            dirname(__file__),
            "files",
            "fortx_Tarrant_County_Commissioners_Court_remaining_archived_meetings.json",
        ),
        url="https://api-dev.agendalink.app/api/engage/agendas/tarrantcountytx?span=2025&department=6823a747b52fbb005d2ff78d",  # noqa
    ).json()


@pytest.fixture(scope="module")
def upcoming_meetings_response(
    archived_meetings_data, remaining_archived_meetings_data
):
    """This is the main response that parse() receives."""
    url = "https://api-dev.agendalink.app/api/engage/agendas/tarrantcountytx?span=2026&department=6823a747b52fbb005d2ff78d"  # noqa

    request = scrapy.Request(
        url=url,
        meta={
            "archived_meetings": archived_meetings_data,
            "remaining_archived_meetings": remaining_archived_meetings_data,
        },
    )

    response = file_response(
        join(
            dirname(__file__),
            "files",
            "fortx_Tarrant_County_Commissioners_Court_upcoming_meetings.json",
        ),
        url=url,
    )

    response.request = request

    return response


@pytest.fixture(scope="module")
def parsed_items(spider, upcoming_meetings_response):
    """Parse all meetings with frozen time and proper meta setup."""
    with freeze_time("2026-02-09"):
        items = list(spider.parse(upcoming_meetings_response))

    return items


def test_count(parsed_items):
    assert len(parsed_items) == 72


def test_title(parsed_items):
    assert parsed_items[0]["title"] == "Commissioners Court"


def test_description(parsed_items):
    assert parsed_items[0]["description"] == ""


def test_start(parsed_items):
    assert parsed_items[0]["start"] == datetime(2025, 9, 16, 10, 0)


def test_end(parsed_items):
    assert parsed_items[0]["end"] == datetime(2025, 9, 16, 17, 0)


def test_time_notes(parsed_items):
    assert parsed_items[0]["time_notes"] == ""


def test_id(parsed_items):
    assert (
        parsed_items[0]["id"]
        == "fortx_Tarrant_County_Commissioners_Court/202509161000/x/commissioners_court"
    )


def test_status(parsed_items):
    assert parsed_items[0]["status"] == "passed"


def test_location(parsed_items):
    assert parsed_items[0]["location"] == {
        "name": "Tarrant County Administration Building (check the agenda for room location)",  # noqa
        "address": "100 East Weatherford Street, 5th Floor, Fort Worth, Texas, 76196",
    }


def test_source(parsed_items):
    assert (
        parsed_items[0]["source"]
        == "https://www.tarrantcountytx.gov/en/commissioners-court/commissioners-court-agenda-videos.html"  # noqa
    )


def test_links(parsed_items):
    assert parsed_items[0]["links"] == []


def test_classification(parsed_items):
    assert parsed_items[0]["classification"] == COMMISSION


def test_all_day(parsed_items):
    for item in parsed_items:
        assert item["all_day"] is False

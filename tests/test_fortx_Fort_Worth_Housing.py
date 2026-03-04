from datetime import datetime
from os.path import dirname, join
from unittest.mock import MagicMock

import pytest
from city_scrapers_core.constants import BOARD
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.fortx_Fort_Worth_Housing import FortxFortWorthHousingSpider


@pytest.fixture
def spider():
    return FortxFortWorthHousingSpider()


@pytest.fixture
def event_response():
    """Standard board meeting event page."""
    return file_response(
        join(dirname(__file__), "files", "fortx_Fort_Worth_Housing_event.html"),
        url="https://fwhs.org/event/fwhs-board-of-commissioners-meeting/",
    )


@pytest.fixture
def calendar_response():
    """AJAX calendar response with event links (from JSON fixture)."""
    import json

    with open(
        join(dirname(__file__), "files", "fortx_Fort_Worth_Housing_calendar.json")
    ) as f:
        json_data = json.load(f)

    mock_response = MagicMock()
    mock_response.json.return_value = json_data
    mock_response.meta = {"month_url": "2026-01"}
    mock_response.urljoin = lambda url: url
    return mock_response


@pytest.fixture
def cancelled_event_response():
    return file_response(
        join(
            dirname(__file__), "files", "fortx_Fort_Worth_Housing_cancelled_event.html"
        ),
        url="https://fwhs.org/event/fwhs-board-of-commissioners-meeting-11/",
    )


@pytest.fixture
def parsed_item(spider, event_response):
    """Parse the event page and return the first item."""
    items = list(spider.parse_event_page(event_response))
    return items[0]


@freeze_time("2026-02-05")
class TestEventPage:
    """Tests for parsing a standard board meeting event page."""

    def test_title(self, parsed_item):
        assert parsed_item["title"] == "FWHS Board of Commissioners Meeting"

    def test_classification(self, parsed_item):
        assert parsed_item["classification"] == BOARD

    def test_start(self, parsed_item):
        assert parsed_item["start"] == datetime(2024, 2, 22, 12, 0)

    def test_end(self, parsed_item):
        assert parsed_item["end"] == datetime(2024, 2, 22, 13, 0)

    def test_location_name(self, parsed_item):
        assert (
            parsed_item["location"]["name"]
            == "Fort Worth Housing Solutions Administrative Office"
        )

    def test_location_address(self, parsed_item):
        assert "1407 Texas St" in parsed_item["location"]["address"]
        assert "Fort Worth" in parsed_item["location"]["address"]

    def test_links_normalized(self, parsed_item):
        """Test that 'Download Agenda PDF' is normalized to 'Agenda'."""
        assert len(parsed_item["links"]) >= 1
        assert parsed_item["links"][0]["title"] == "Agenda"
        assert ".pdf" in parsed_item["links"][0]["href"]

    def test_all_day_is_false(self, parsed_item):
        assert parsed_item["all_day"] is False

    def test_source(self, parsed_item):
        assert (
            parsed_item["source"]
            == "https://fwhs.org/event/fwhs-board-of-commissioners-meeting/"
        )

    def test_status_passed(self, parsed_item):
        assert parsed_item["status"] == "passed"

    def test_empty_description(self, parsed_item):
        """Standard meetings without description text should have empty description."""
        assert parsed_item["description"] == ""


@pytest.fixture
def cancelled_parsed_item(spider, cancelled_event_response):
    items = list(spider.parse_event_page(cancelled_event_response))
    return items[0]


@freeze_time("2026-02-05")
class TestCancelledEvent:

    def test_title_cleaned(self, cancelled_parsed_item):
        assert cancelled_parsed_item["title"] == "FWHS Board of Commissioners Meeting"

    def test_status_cancelled(self, cancelled_parsed_item):
        assert cancelled_parsed_item["status"] == "cancelled"

    def test_classification(self, cancelled_parsed_item):
        assert cancelled_parsed_item["classification"] == BOARD

    def test_start(self, cancelled_parsed_item):
        assert cancelled_parsed_item["start"] == datetime(2024, 9, 19, 17, 0)

    def test_end(self, cancelled_parsed_item):
        assert cancelled_parsed_item["end"] == datetime(2024, 9, 19, 18, 0)

    def test_cancellation_notice_link(self, cancelled_parsed_item):
        links = cancelled_parsed_item["links"]
        cancellation_links = [link for link in links if "Cancellation" in link["title"]]
        assert len(cancellation_links) == 1
        assert "Cancellation.pdf" in cancellation_links[0]["href"]


class TestCalendarParsing:
    """Tests for parsing AJAX calendar response to extract event URLs."""

    def test_extracts_event_urls(self, spider, calendar_response):
        """Test that event URLs are extracted from calendar HTML."""
        requests = list(spider.parse_ajax_response(calendar_response))
        assert len(requests) == 2

    def test_cancelled_meeting_url(self, spider, calendar_response):
        """Test that cancelled meeting URL is extracted."""
        requests = list(spider.parse_ajax_response(calendar_response))
        urls = [r.url for r in requests]
        assert "https://fwhs.org/event/regular-board-meeting-3/" in urls

    def test_regular_meeting_url(self, spider, calendar_response):
        """Test that regular meeting URL is extracted."""
        requests = list(spider.parse_ajax_response(calendar_response))
        urls = [r.url for r in requests]
        assert "https://fwhs.org/event/regular-board-meeting4/" in urls

    def test_deduplicates_urls(self, spider, calendar_response):
        """Test that duplicate URLs within same month are deduplicated."""
        # First call
        requests1 = list(spider.parse_ajax_response(calendar_response))
        # Second call should return no new requests (already seen)
        requests2 = list(spider.parse_ajax_response(calendar_response))
        assert len(requests1) == 2
        assert len(requests2) == 0

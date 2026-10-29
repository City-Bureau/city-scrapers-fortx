import json
from datetime import date, datetime
from os.path import dirname, join
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse

import pytest
import scrapy
from city_scrapers_core.constants import (
    CANCELLED,
    CITY_COUNCIL,
    COMMISSION,
    PASSED,
    TENTATIVE,
)
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.mixins.fort_worth import FortWorthMixin
from city_scrapers.spiders.fortx_fort_worth import (
    FortxFortWorthBoardsSpider,
    FortxFortWorthCityCouncilSpider,
    FortxFortWorthPublicMeetingsSpider,
)

FILES = join(dirname(__file__), "files")
LISTING_URL = "https://www.fortworthtexas.gov/ocapi/calendars/getcalendaritems"
DETAIL_URL = "https://www.fortworthtexas.gov/ocapi/get/contentinfo"


def fixture(name, url=DETAIL_URL):
    return file_response(join(FILES, name), url=url)


def run_meeting(spider, detail_response, start, page_response=None):
    """
    Runs one occurrence through parse_meeting and, when it asks for the
    event page, through parse_event_page. Returns the finished meetings.
    """
    meetings = []
    for result in spider.parse_meeting(detail_response, start=start):
        if isinstance(result, scrapy.Request):
            assert page_response is not None, "unexpected event page request"
            meetings.extend(spider.parse_event_page(page_response, **result.cb_kwargs))
        else:
            meetings.append(result)
    return meetings


def parse_listing(spider, listing_response, detail_response, page_response=None):
    """Feeds every occurrence of a listing through one shared detail fixture"""
    meetings = []
    for request in spider.parse(listing_response):
        meetings.extend(
            run_meeting(
                spider,
                detail_response,
                page_response=page_response,
                **request.cb_kwargs,
            )
        )
    return meetings


# Mixin


def test_mixin_requires_static_vars():
    with pytest.raises(NotImplementedError) as error:
        type(
            "IncompleteSpider",
            (FortWorthMixin,),
            {"name": "fortx_incomplete", "agency": "Incomplete"},
        )
    assert "calendar_id, calendar_url, classification" in str(error.value)


def test_spider_attributes():
    spider = FortxFortWorthBoardsSpider()
    assert isinstance(spider, CityScrapersSpider)
    assert spider.name == "fortx_Fort_Worth_Boards"
    assert spider.agency == "Fort Worth Boards and Commissions"
    assert spider.calendar_id == "788ffb59-05d1-457d-b9dd-423d4b95a06e"
    assert spider.timezone == "America/Chicago"


# Scraping window


@freeze_time("2026-10-01 03:00:00")  # 22:00 on Sep 30 in Fort Worth
def test_date_ranges_use_fort_worth_date():
    assert FortxFortWorthCityCouncilSpider()._date_ranges() == [
        (date(2025, 9, 30), date(2025, 12, 31)),
        (date(2026, 1, 1), date(2026, 12, 31)),
        (date(2027, 1, 1), date(2027, 9, 30)),
    ]


@freeze_time("2026-01-01 12:00:00")
def test_date_ranges_at_start_of_year():
    assert FortxFortWorthCityCouncilSpider()._date_ranges() == [
        (date(2025, 1, 1), date(2025, 12, 31)),
        (date(2026, 1, 1), date(2026, 12, 31)),
        (date(2027, 1, 1), date(2027, 1, 1)),
    ]


@freeze_time("2026-10-01 15:00:00")
def test_start_requests():
    spider = FortxFortWorthPublicMeetingsSpider()
    requests = list(spider.start_requests())
    payloads = [json.loads(request.body) for request in requests]

    assert all(request.method == "POST" for request in requests)
    assert all(request.url == LISTING_URL for request in requests)
    assert [(p["StartDate"], p["EndDate"]) for p in payloads] == [
        ("2025-10-01", "2025-12-31"),
        ("2026-01-01", "2026-12-31"),
        ("2027-01-01", "2027-10-01"),
    ]
    assert all(p["Ids"] == ["8efac0b6-9ea3-402e-b7d9-e9e71a2a34a0"] for p in payloads)


# Status


@freeze_time("2026-10-01 15:30:00")  # 10:30 in Fort Worth, 15:30 on a UTC runner
def test_status_compares_against_fort_worth_time():
    spider = FortxFortWorthCityCouncilSpider()
    meeting = {"title": "City Council Meeting", "start": datetime(2026, 10, 1, 11)}
    assert spider._parse_status(meeting, False) == TENTATIVE
    meeting["start"] = datetime(2026, 10, 1, 10)
    assert spider._parse_status(meeting, False) == PASSED


def test_status_ignores_description():
    spider = FortxFortWorthCityCouncilSpider()
    meeting = Meeting(
        title="City Council Meeting",
        description="Meetings may be cancelled due to weather",
        start=datetime(2020, 1, 1),
    )
    assert spider._parse_status(meeting, False) == PASSED
    assert spider._parse_status(meeting, True) == CANCELLED


# Location


@pytest.mark.parametrize(
    "address,expected",
    [
        (
            {
                "Venue": "CITY HALL TRAINING ROOM CH_MZ10_16",
                "Street": "100 FORT WORTH TRAIL, FORT WORTH, TEXAS 76102",
                "Suburb": "Fort Worth",
                "PostCode": "76115",
                "Formatted": "CITY HALL TRAINING ROOM CH_MZ10_16, 100 FORT WORTH TRAIL, FORT WORTH, TEXAS 76102, Fort Worth, 76115",  # noqa
            },
            {
                "name": "CITY HALL TRAINING ROOM CH_MZ10_16",
                "address": "100 FORT WORTH TRAIL, FORT WORTH, TEXAS 76102",
            },
        ),
        (
            {
                "Venue": "DFW Headquarters Building",
                "Street": "2400 Aviation Dr., DFW Airport",
                "Suburb": "Other",
                "PostCode": "75261",
                "Formatted": "DFW Headquarters Building, 2400 Aviation Dr., DFW Airport, Other, 75261",  # noqa
            },
            {
                "name": "DFW Headquarters Building",
                "address": "2400 Aviation Dr., DFW Airport, 75261",
            },
        ),
        (
            {
                "Venue": "City Hall, City Council Work Session Room",
                "Street": "100 Fort Worth Trail",
                "Suburb": "Fort Worth",
                "PostCode": "76102",
                "Formatted": "City Hall, City Council Work Session Room, 100 Fort Worth Trail, Fort Worth, 76102",  # noqa
            },
            {
                "name": "City Hall, City Council Work Session Room",
                "address": "100 Fort Worth Trail, Fort Worth, 76102",
            },
        ),
        (
            {
                "Venue": "Lena Pope Amon Carter Center",
                "Street": "3200 Sanguinet St,",
                "Suburb": "Fort Worth",
                "PostCode": "76107",
                "Formatted": "Lena Pope Amon Carter Center, 3200 Sanguinet St,, Fort Worth, 76107",  # noqa
            },
            {
                "name": "Lena Pope Amon Carter Center",
                "address": "3200 Sanguinet St, Fort Worth, 76107",
            },
        ),
        (
            {
                "Venue": "City Hall",
                "Street": "100 Fort  Worth Trail",
                "Suburb": "Fort Worth",
                "PostCode": "76102",
                "Formatted": "City Hall, 100 Fort  Worth Trail, Fort Worth, 76102",
            },
            {"name": "City Hall", "address": "100 Fort Worth Trail, Fort Worth, 76102"},
        ),
        (
            {
                "Venue": "",
                "Street": "801 Grove Street",
                "Suburb": "Fort Worth",
                "PostCode": "76102",
                "Formatted": " 801 Grove Street, Fort Worth, 76102",
            },
            {"name": "", "address": "801 Grove Street, Fort Worth, 76102"},
        ),
        (
            {
                "Venue": "",
                "Street": "",
                "Suburb": "Fort Worth",
                "PostCode": "",
                "Formatted": " Fort Worth",
            },
            {"name": "TBD", "address": ""},
        ),
        ({}, {"name": "TBD", "address": ""}),
    ],
)
def test_parse_location(address, expected):
    spider = FortxFortWorthBoardsSpider()
    assert spider._parse_location({"Address": address}) == expected


# Fort Worth City Council


@pytest.fixture(scope="module")
def city_council_items():
    spider = FortxFortWorthCityCouncilSpider()
    with freeze_time("2026-03-06"):
        return parse_listing(
            spider,
            fixture("fortx_Fort_Worth_City_Council_meeting_items.json", LISTING_URL),
            fixture("fortx_Fort_Worth_City_Council_meeting_details.json"),
            fixture("fortx_Fort_Worth_City_Council_detail_page.html"),
        )


def test_city_council_count(city_council_items):
    assert len(city_council_items) == 13


def test_city_council_title(city_council_items):
    assert city_council_items[0]["title"] == "Audit & Finance Committee"


def test_city_council_description(city_council_items):
    assert city_council_items[0]["description"] == "Audit & Finance Committee Meeting."


def test_city_council_start(city_council_items):
    assert city_council_items[0]["start"] == datetime(2025, 10, 14, 9, 0)


def test_city_council_end(city_council_items):
    assert city_council_items[0]["end"] is None


def test_city_council_time_notes(city_council_items):
    assert (
        city_council_items[0]["time_notes"]
        == "Please check the meeting source for details on the start time"
    )


def test_city_council_id(city_council_items):
    assert (
        city_council_items[0]["id"]
        == "fortx_Fort_Worth_City_Council/202510140900/x/audit_finance_committee"
    )


def test_city_council_status(city_council_items):
    assert city_council_items[0]["status"] == PASSED


def test_city_council_location(city_council_items):
    assert city_council_items[0]["location"] == {
        "name": "New City Hall",
        "address": "100 Fort Worth Trail, Fort Worth, 76102",
    }


def test_city_council_source(city_council_items):
    assert (
        city_council_items[0]["source"]
        == "https://www.fortworthtexas.gov/departments/citysecretary/events/audit-committee-2025"  # noqa
    )


def test_city_council_links(city_council_items):
    assert city_council_items[0]["links"] == [
        {
            "title": "Meeting Details",
            "href": "https://www.fortworthtexas.gov/departments/citysecretary/events/audit-committee-2025",  # noqa
        }
    ]


def test_city_council_classification(city_council_items):
    assert city_council_items[0]["classification"] == CITY_COUNCIL


def test_city_council_all_day(city_council_items):
    for item in city_council_items:
        assert item["all_day"] is False


def test_detail_requests():
    spider = FortxFortWorthCityCouncilSpider()
    requests = list(
        spider.parse(
            fixture("fortx_Fort_Worth_City_Council_meeting_items.json", LISTING_URL)
        )
    )
    assert len(requests) == 13
    assert requests[0].url == (
        "https://www.fortworthtexas.gov/ocapi/get/contentinfo"
        "?calendarId=8a8add9a-3fd0-4b39-9a3e-d58e98e27acc"
        "&contentId=57212572-47cc-44e2-9da3-8e0d88b7c003&language=en-US"
        "&currentDateTime=14%2F10%2F2025+9%3A00%3A00+AM"
        "&mainContentId=57212572-47cc-44e2-9da3-8e0d88b7c003"
    )
    assert requests[0].cb_kwargs == {"start": datetime(2025, 10, 14, 9, 0)}


# Fort Worth Boards and Commissions


@pytest.fixture(scope="module")
def boards_items():
    spider = FortxFortWorthBoardsSpider()
    listing = fixture("fortx_Fort_Worth_Boards.json", LISTING_URL)
    request = next(iter(spider.parse(listing)))
    with freeze_time("2026-03-09"):
        return run_meeting(
            spider,
            fixture("fortx_Fort_Worth_Boards_meeting_details.json"),
            page_response=fixture("fortx_Fort_Worth_City_Council_detail_page.html"),
            **request.cb_kwargs,
        )


def test_boards_count(boards_items):
    assert len(boards_items) == 1


def test_boards_title(boards_items):
    assert boards_items[0]["title"] == "2025 Building Standards Commission (BSC)"


def test_boards_description(boards_items):
    assert boards_items[0]["description"] == "2025 Meeting Calendar."


@pytest.mark.parametrize(
    "description,expected",
    [
        (
            "Park & Recreation Advisory Board Meeting. View agenda and meeting details.",  # noqa
            "Park & Recreation Advisory Board Meeting.",
        ),
        (
            "Public Safety Committee (PSC). View the agenda and meeting details.",
            "Public Safety Committee (PSC).",
        ),
        (
            "Audit & Finance Committee Meeting. Veiw agenda and meeting details.",
            "Audit & Finance Committee Meeting.",
        ),
        (
            "Tax Increment Reinvestment Zone No. 9 (Trinity River Vision TIF)"
            "\r\n\r\nView agenda and meeting details.",
            "Tax Increment Reinvestment Zone No. 9 (Trinity River Vision TIF)",
        ),
        (
            "Crime Control Prevention District meeting. Immediately following the "
            "Work Session starting at 1 p.m. View updated agendas here with the "
            "next scheduled meeting details.",
            "Crime Control Prevention District meeting. Immediately following the "
            "Work Session starting at 1 p.m.",
        ),
        ("View updated agendas here with the next scheduled meeting details.", ""),
        ("View past agendas and meeting details.", ""),
        (
            "Fort Worth City Council will consider approval of a tax abatement "
            "agreement as an agenda item at its regularly scheduled meeting",
            "Fort Worth City Council will consider approval of a tax abatement "
            "agreement as an agenda item at its regularly scheduled meeting",
        ),
        (
            "Meeting will be held at Eastside YMCA\r\nand begins at 10:00 a.m.",
            "Meeting will be held at Eastside YMCA and begins at 10:00 a.m.",
        ),
        (None, ""),
    ],
)
def test_parse_description(description, expected):
    spider = FortxFortWorthBoardsSpider()
    assert spider._parse_description({"Description": description}) == expected


def test_boards_start(boards_items):
    assert boards_items[0]["start"] == datetime(2025, 6, 23, 9, 0)


def test_boards_id(boards_items):
    assert (
        boards_items[0]["id"]
        == "fortx_Fort_Worth_Boards/202506230900/x/2025_building_standards_commission_bsc_"  # noqa
    )


def test_boards_status(boards_items):
    assert boards_items[0]["status"] == PASSED


def test_boards_location(boards_items):
    assert boards_items[0]["location"] == {"name": "TBD", "address": ""}


def test_boards_source(boards_items):
    assert (
        boards_items[0]["source"]
        == "https://www.fortworthtexas.gov/departments/citysecretary/events/building-standards-commission-meeting-2025"  # noqa
    )


def test_boards_links(boards_items):
    assert boards_items[0]["links"] == [
        {
            "title": "Meeting Details",
            "href": "https://www.fortworthtexas.gov/departments/citysecretary/events/building-standards-commission-meeting-2025",  # noqa
        }
    ]


def test_boards_classification(boards_items):
    assert boards_items[0]["classification"] == COMMISSION


# Fort Worth Public Meetings


@pytest.fixture(scope="module")
def public_meetings_items():
    spider = FortxFortWorthPublicMeetingsSpider()
    with freeze_time("2024-12-19"):
        return parse_listing(
            spider,
            fixture("fortx_Fort_Worth_Public_Meetings_meeting_items.json", LISTING_URL),
            fixture("fortx_Fort_Worth_Public_Meetings_meeting_details.json"),
            fixture("fortx_Fort_Worth_City_Council_detail_page.html"),
        )


def test_public_meetings_count(public_meetings_items):
    assert len(public_meetings_items) == 6


def test_public_meetings_title(public_meetings_items):
    assert (
        public_meetings_items[0]["title"] == "TPW Meeting Glasgow and Oak Grove Roads"
    )


def test_public_meetings_start(public_meetings_items):
    assert public_meetings_items[0]["start"] == datetime(2024, 2, 1, 18, 0)


def test_public_meetings_status(public_meetings_items):
    assert public_meetings_items[0]["status"] == PASSED


def test_public_meetings_location(public_meetings_items):
    assert public_meetings_items[0]["location"] == {
        "name": "Highland Hills Community Center",
        "address": "1600 Glasgow Road, Fort Worth, 76134",
    }


def test_public_meetings_classification(public_meetings_items):
    assert public_meetings_items[0]["classification"] == CITY_COUNCIL


def test_public_meetings_description_has_no_line_breaks(public_meetings_items):
    for item in public_meetings_items:
        assert "\n" not in item["description"]
        assert "\r" not in item["description"]


@freeze_time("2024-12-19")
def test_is_cancelled_flag():
    spider = FortxFortWorthPublicMeetingsSpider()
    meetings = run_meeting(
        spider,
        fixture("fortx_Fort_Worth_Public_Meetings_cancelled_meeting_details.json"),
        datetime(2025, 2, 4, 18, 0),
        page_response=fixture("fortx_Fort_Worth_City_Council_detail_page.html"),
    )
    assert meetings[0]["status"] == CANCELLED


# Cancellations and documents on the event page

DISCIPLINARY_URL = "https://www.fortworthtexas.gov/departments/citysecretary/events/Disciplinary-Hearings-2026"  # noqa


@freeze_time("2026-09-15")
def test_next_date_cancellation_only_applies_to_next_date():
    """
    The Disciplinary Hearings page lists 13 dates and shows "HEARING
    CANCELED" under "Next date: Thursday, October 01, 2026" while the API
    reports IsCancelled false for all of them.
    """
    spider = FortxFortWorthBoardsSpider()
    detail = fixture("fortx_Fort_Worth_Boards_disciplinary_details.json")
    page = fixture("fortx_Fort_Worth_Boards_disciplinary_page.html", DISCIPLINARY_URL)

    cancelled = run_meeting(spider, detail, datetime(2026, 10, 1, 9), page)
    # The page has been read, so the next occurrence doesn't request it again
    later = run_meeting(spider, detail, datetime(2026, 10, 15, 9))
    earlier = run_meeting(spider, detail, datetime(2026, 6, 10, 9))

    assert cancelled[0]["status"] == CANCELLED
    assert later[0]["status"] == TENTATIVE
    assert earlier[0]["status"] == PASSED
    assert cancelled[0]["location"] == {
        "name": "CITY HALL TRAINING ROOM CH_MZ10_16",
        "address": "100 FORT WORTH TRAIL, FORT WORTH, TEXAS 76102",
    }


@freeze_time("2026-09-15")
def test_pending_meetings_wait_for_shared_page():
    spider = FortxFortWorthBoardsSpider()
    detail = fixture("fortx_Fort_Worth_Boards_disciplinary_details.json")
    first = list(spider.parse_meeting(detail, start=datetime(2026, 10, 1, 9)))
    second = list(spider.parse_meeting(detail, start=datetime(2026, 6, 10, 9)))

    assert len(first) == 1 and isinstance(first[0], scrapy.Request)
    assert first[0].dont_filter is True
    assert second == []

    page = fixture("fortx_Fort_Worth_Boards_disciplinary_page.html")
    meetings = list(spider.parse_event_page(page, **first[0].cb_kwargs))
    assert [m["status"] for m in meetings] == [CANCELLED, PASSED]


@freeze_time("2026-09-15")
def test_dated_cancellation_notice():
    """The Art Commission page says "12/15/2025 Art Commission meeting CANCELED!" """
    spider = FortxFortWorthBoardsSpider()
    detail = fixture("fortx_Fort_Worth_Boards_art_commission_details.json")
    page = fixture("fortx_Fort_Worth_Boards_art_commission_page.html")

    cancelled = run_meeting(spider, detail, datetime(2025, 12, 15, 17, 30), page)
    held = run_meeting(spider, detail, datetime(2025, 11, 17, 17, 30))

    assert cancelled[0]["status"] == CANCELLED
    assert held[0]["status"] == PASSED
    assert held[0]["title"] == "Fort Worth Art Commission Meeting (FWAC)"
    assert held[0]["location"] == {
        "name": "Ella Mae Shambley Library",
        "address": "1062 Evans Avenue Fort Worth, TX 76104",
    }


@freeze_time("2026-10-02")
def test_attachment_cancellations_after_next_date_is_gone():
    """
    Once Oct 1 passed, the page kept "HEARING CANCELED" but dropped its
    "Next date" line. The attachment names still mark the cancelled dates.
    """
    spider = FortxFortWorthBoardsSpider()
    page = fixture(
        "fortx_Fort_Worth_Boards_disciplinary_page_after_next_date.html",
        DISCIPLINARY_URL,
    )
    cancelled_dates = spider._parse_event_page(page)
    assert cancelled_dates == {
        date(2026, 1, 28),
        date(2026, 1, 29),
        date(2026, 3, 12),
        date(2026, 3, 13),
        date(2026, 3, 26),
        date(2026, 6, 4),
        date(2026, 8, 12),
        date(2026, 10, 1),
    }


@freeze_time("2026-10-02")
def test_attachments_are_not_added_to_links():
    spider = FortxFortWorthBoardsSpider()
    detail = fixture("fortx_Fort_Worth_Boards_disciplinary_details.json")
    page = fixture(
        "fortx_Fort_Worth_Boards_disciplinary_page_after_next_date.html",
        DISCIPLINARY_URL,
    )
    meeting = run_meeting(spider, detail, datetime(2026, 6, 10, 9), page)[0]

    assert meeting["status"] == PASSED
    assert meeting["links"] == [{"title": "Meeting Details", "href": DISCIPLINARY_URL}]


def event_page(body):
    return scrapy.http.HtmlResponse(
        url="https://www.fortworthtexas.gov/events/commission",
        body=f"""<div><h1 class="oc-page-title">Commission</h1>{body}</div>""",
        encoding="utf-8",
    )


def test_attachment_cancellations():
    spider = FortxFortWorthBoardsSpider()
    cancelled_dates = spider._parse_event_page(event_page("""
        <a class="document" href="/files/a.pdf">10-16-2025 CANCELED TIF 13 Agenda</a>
        <a class="document" href="/files/b.pdf">6-9-25 HCLC Minutes</a>
        <a class="document" href="/files/01-26-2026-bsc-canceled-revised-agenda.pdf"
            title="01-26-2026 BSC Canceled Revised Agenda">01-26-2026 BSC Agenda</a>
        <a class="document" href="/files/03-31-2026-hfc-agenda-canceled.pdf"
            >03-31-2026 HFC Agenda</a>
        <a class="document" href="/files/c.pdf"
            >01-28-2026-01 -29-2026 Canceled Ronald Clements Hearing</a>
        <a class="document" href="/files/d.pdf">6-4-26 Canceled Notice</a>
        <a class="document" href="/files/e.pdf">Canceled Guide for Speakers</a>
        <a class="document" href="/files/f.pdf">12-02-202 Canceled Agenda</a>
        """))
    assert cancelled_dates == {
        date(2025, 10, 16),
        date(2026, 1, 26),
        date(2026, 3, 31),
        date(2026, 1, 28),
        date(2026, 1, 29),
        date(2026, 6, 4),
    }


@freeze_time("2026-10-05")
def test_rescheduled_notice_only_cancels_the_source_date():
    spider = FortxFortWorthBoardsSpider()
    detail = fixture("fortx_Fort_Worth_Boards_disciplinary_details.json")
    page = event_page(
        """<p class="event-date">Next date: Thursday, October 15, 2026 | 09:00 AM</p>
        <p>10/15/2026 hearing rescheduled to 10/22/2026</p>"""
    )
    request = next(iter(spider.parse_meeting(detail, start=datetime(2026, 10, 15, 9))))
    assert list(spider.parse_meeting(detail, start=datetime(2026, 10, 22, 9))) == []

    meetings = list(spider.parse_event_page(page, **request.cb_kwargs))
    assert [(m["start"].day, m["status"]) for m in meetings] == [
        (15, CANCELLED),
        (22, TENTATIVE),
    ]


def test_postponed_attachment_only_cancels_the_source_date():
    spider = FortxFortWorthBoardsSpider()
    cancelled_dates = spider._parse_event_page(
        event_page("""<a class="document" href="/files/a.pdf"
            >10-08-2026 Agenda Postponed to 10-22-2026</a>
        <a class="document" href="/files/b.pdf"
            >11-02-2026-11-03-2026 Canceled Hearing</a>""")
    )
    # A cancellation keeps every date it names
    assert cancelled_dates == {date(2026, 10, 8), date(2026, 11, 2), date(2026, 11, 3)}


def test_header_notice_without_date_uses_next_date():
    spider = FortxFortWorthBoardsSpider()
    cancelled_dates = spider._parse_event_page(
        event_page(
            """<p class="event-date">Next date: Monday, October 05, 2026 | 05:30 PM</p>
        <p>HEARING CANCELED</p>"""
        )
    )
    assert cancelled_dates == {date(2026, 10, 5)}


def test_header_ignores_body_text():
    spider = FortxFortWorthBoardsSpider()
    page = event_page(
        """<p class="event-date">Next date: Monday, October 05, 2026 | 05:30 PM</p>
        <h2 class="sub-title">Details</h2>
        <p>Meetings may be canceled for lack of a quorum.</p>"""
    )
    assert spider._parse_event_page(page) == set()


@freeze_time("2026-09-15")
def test_event_page_error_still_yields_meetings():
    spider = FortxFortWorthBoardsSpider()
    detail = fixture("fortx_Fort_Worth_Boards_disciplinary_details.json")
    request = next(iter(spider.parse_meeting(detail, start=datetime(2026, 10, 1, 9))))

    failure = MagicMock()
    failure.request = request
    meetings = list(spider._event_page_error(failure))

    assert len(meetings) == 1
    assert meetings[0]["status"] == TENTATIVE


# Exclusions


def make_spider(**attrs):
    return type(
        "ExclusionSpider",
        (FortWorthMixin,),
        {
            "name": "fortx_exclusion",
            "agency": "Exclusion",
            "calendar_id": "8a8add9a-3fd0-4b39-9a3e-d58e98e27acc",
            "calendar_url": "https://www.fortworthtexas.gov/calendar/city-council",
            "classification": CITY_COUNCIL,
            **attrs,
        },
    )()


def listing_names(spider, name="fortx_Fort_Worth_City_Council_meeting_items.json"):
    listing = fixture(name, LISTING_URL)
    names = {}
    for day in listing.json()["data"]:
        for item in day["Items"]:
            names[item["Id"]] = item["Name"]
    return [
        names[parse_qs(urlparse(request.url).query)["contentId"][0]]
        for request in spider.parse(listing)
    ]


def test_no_exclusions_by_default():
    assert len(listing_names(make_spider())) == 13


def test_exclude_ids():
    spider = make_spider(exclude_ids=["2F7F60E6-1873-40ED-85AD-FC214BD77582"])
    names = listing_names(spider)
    assert len(names) == 12
    assert "2026 Special Called Election Voting Dates & Election Notices" not in names


def test_exclude_title_patterns():
    spider = make_spider(exclude_title_patterns=[r"election voting dates"])
    names = listing_names(spider)
    assert len(names) == 12
    assert not any("Voting Dates" in name for name in names)


def test_null_content_id_never_excludes():
    spider = make_spider(exclude_ids=["00000000-0000-0000-0000-000000000000"])
    names = listing_names(spider, "fortx_Fort_Worth_Public_Meetings_meeting_items.json")
    assert len(names) == 6

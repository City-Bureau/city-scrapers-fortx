import json
import re
from collections import defaultdict
from datetime import date, datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import scrapy
from city_scrapers_core.constants import CANCELLED, PASSED, TENTATIVE
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from dateutil.relativedelta import relativedelta
from scrapy.http import TextResponse

NULL_CONTENT_ID = "00000000-0000-0000-0000-000000000000"


class FortWorthMixinMeta(type):
    """
    Metaclass that enforces the implementation of required static
    variables in child classes that inherit from FortWorthMixin.
    """

    def __init__(cls, name, bases, dct):
        required_static_vars = [
            "agency",
            "name",
            "calendar_id",
            "calendar_url",
            "classification",
        ]
        missing_vars = [var for var in required_static_vars if var not in dct]

        if missing_vars:
            missing_vars_str = ", ".join(missing_vars)
            raise NotImplementedError(
                f"{name} must define the following static variable(s): "
                f"{missing_vars_str}."
            )

        super().__init__(name, bases, dct)


class FortWorthMixin(CityScrapersSpider, metaclass=FortWorthMixinMeta):
    """
    Shared logic for the City of Fort Worth calendars on fortworthtexas.gov.

    Each calendar is scraped in three steps:
    1. The calendar items API returns every occurrence (id and local start
       time) within a date range.
    2. The content info API returns the details (title, address, link and
       an IsCancelled flag) for each occurrence.
    3. The event page behind "Link" is fetched once per page, because
       cancellations are mostly only posted there, in attachment names
       and header notices, while IsCancelled stays false.
    """

    name = None
    agency = None
    calendar_id = None
    calendar_url = None
    classification = None
    exclude_ids = ()
    exclude_title_patterns = ()

    timezone = "America/Chicago"
    tz = ZoneInfo(timezone)

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
    }

    meetings_url = "https://www.fortworthtexas.gov/ocapi/calendars/getcalendaritems"
    meeting_detail_url = "https://www.fortworthtexas.gov/ocapi/get/contentinfo"

    # The scraping window is one year back and one year ahead
    window_past = relativedelta(years=1)
    window_future = relativedelta(years=1)

    item_datetime_format = "%d/%m/%Y %I:%M:%S %p"
    time_notes = "Please check the meeting source for details on the start time"
    cancel_re = re.compile(r"cancel|postpone|reschedul", re.IGNORECASE)
    cancel_only_re = re.compile(r"cancel", re.IGNORECASE)
    # The sentence pointing to agendas, e.g. "View agenda and meeting
    # details.", "Veiw agenda", "View the past agendas", "View updated
    # agendas here with the next scheduled meeting details."
    agenda_pointer_re = re.compile(
        r"(?:\bv(?:iew|eiw)\b(?:\s+\w+){0,2}?\s+agendas?\b|\bagendas?\s+here\b)"
        r"[^.!?]*[.!?]?",
        re.IGNORECASE,
    )
    us_date_re = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
    # Attachment dates are written loosely: 6-4-2026, 01-28-26, 03- 10-25
    # and ranges like 01-28-2026-01 -29-2026
    document_date_re = re.compile(
        r"(?<!\d)(\d{1,2})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{4}|\d{2})(?!\d)"
    )
    long_date_re = re.compile(
        r"\b(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b",
        re.IGNORECASE,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Event pages are shared by every occurrence of a recurring
        # meeting, so each one is requested once and the occurrences
        # waiting on it are finished when it comes back.
        self._event_pages = {}
        self._pending_meetings = defaultdict(list)
        self._calendar_item_count = 0
        self._exclude_ids = {i.lower() for i in self.exclude_ids}
        self._exclude_title_res = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in self.exclude_title_patterns
        ]

    def start_requests(self):
        """
        The calendar items API only returns meetings from the year of
        StartDate, even when EndDate falls in a later year, so the
        scraping window is split into one request per calendar year.
        """
        for start_date, end_date in self._date_ranges():
            payload = {
                "LanguageCode": "en-US",
                "Ids": [self.calendar_id],
                "StartDate": start_date.isoformat(),
                "EndDate": end_date.isoformat(),
            }
            yield scrapy.Request(
                url=self.meetings_url,
                method="POST",
                body=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                callback=self.parse,
            )

    def parse(self, response):
        data = response.json()
        items = [item for day in data["data"] or [] for item in day["Items"]]
        self._calendar_item_count += len(items)

        for item in items:
            if self._is_excluded(item):
                continue
            start = self._parse_start(item)
            params = {
                "calendarId": item["CalendarId"],
                "contentId": item["Id"],
                "language": "en-US",
                "currentDateTime": item["DateTime"],
                "mainContentId": item["MainContentId"],
            }
            yield scrapy.Request(
                url=f"{self.meeting_detail_url}?{urlencode(params)}",
                callback=self.parse_meeting,
                cb_kwargs={"start": start},
            )

    def _is_excluded(self, item):
        """
        Public Meetings entries often share the null MainContentId
        00000000-0000-0000-0000-000000000000, so it can never exclude
        anything on its own.
        """
        item_ids = {
            (item.get(key) or "").lower() for key in ("MainContentId", "Id")
        } - {NULL_CONTENT_ID, ""}
        if item_ids & self._exclude_ids:
            return True
        name = item.get("Name") or ""
        return any(pattern.search(name) for pattern in self._exclude_title_res)

    def parse_meeting(self, response, start):
        meeting_data = response.json()["data"]
        link = meeting_data.get("Link")

        meeting = Meeting(
            title=meeting_data["Title"].strip(),
            description=self._parse_description(meeting_data),
            classification=self.classification,
            start=start,
            end=None,
            all_day=False,
            time_notes=self.time_notes,
            location=self._parse_location(meeting_data),
            links=self._parse_links(meeting_data),
            source=link or self.calendar_url,
        )
        is_cancelled = str(meeting_data.get("IsCancelled")).lower() == "true"

        if not link:
            yield self._finalize_meeting(meeting, is_cancelled)
        elif link in self._event_pages:
            yield self._finalize_meeting(meeting, is_cancelled, self._event_pages[link])
        else:
            first_request = link not in self._pending_meetings
            self._pending_meetings[link].append((meeting, is_cancelled))
            if first_request:
                yield scrapy.Request(
                    url=link,
                    callback=self.parse_event_page,
                    errback=self._event_page_error,
                    cb_kwargs={"link": link},
                    # Several links can redirect to the same page, and a
                    # filtered request would drop the meetings waiting on it
                    dont_filter=True,
                )

    def parse_event_page(self, response, link):
        event_page = self._parse_event_page(response)
        self._event_pages[link] = event_page
        for meeting, is_cancelled in self._pending_meetings.pop(link, []):
            yield self._finalize_meeting(meeting, is_cancelled, event_page)

    def closed(self, reason):
        # Ranges in the future are often empty, so only an empty window as
        # a whole is reported
        if self._calendar_item_count == 0:
            self.logger.warning(
                f"No calendar items were returned for calendar {self.calendar_id}"
            )

    def _event_page_error(self, failure):
        link = failure.request.cb_kwargs["link"]
        self.logger.warning(
            f"Could not load event page {link}, page cancellations were not "
            f"checked: {failure.value!r}"
        )
        self._event_pages[link] = None
        for meeting, is_cancelled in self._pending_meetings.pop(link, []):
            yield self._finalize_meeting(meeting, is_cancelled)

    def _finalize_meeting(self, meeting, is_cancelled, cancelled_dates=None):
        if cancelled_dates:
            is_cancelled = is_cancelled or meeting["start"].date() in cancelled_dates
        meeting["status"] = self._parse_status(meeting, is_cancelled)
        meeting["id"] = self._get_id(meeting)
        return meeting

    def _local_now(self):
        """
        The current naive datetime in Fort Worth. Scraped start times are
        naive local times, so comparing them against a bare datetime.now()
        would use the UTC clock of the GitHub Actions runner.
        """
        return datetime.now(tz=self.tz).replace(tzinfo=None)

    def _date_ranges(self):
        """
        Splits the scraping window (one year back and one year ahead of
        today in Fort Worth) into ranges that each stay within a single
        calendar year, the only kind the calendar items API honours.
        """
        today = self._local_now().date()
        window_start = today - self.window_past
        window_end = today + self.window_future

        ranges = []
        for year in range(window_start.year, window_end.year + 1):
            ranges.append(
                (
                    max(window_start, date(year, 1, 1)),
                    min(window_end, date(year, 12, 31)),
                )
            )
        return ranges

    def _parse_start(self, item):
        """Calendar items carry the local start time, e.g. 1/10/2026 9:00:00 AM"""
        return datetime.strptime(item["DateTime"], self.item_datetime_format)

    def _parse_description(self, meeting_data):
        # Agendas aren't scraped, so a sentence pointing to them misleads
        description = self.agenda_pointer_re.sub(
            "", meeting_data.get("Description") or ""
        )
        return " ".join(description.split())

    def _parse_status(self, meeting, is_cancelled):
        """
        Only the title is checked for cancellation keywords because some
        descriptions mention "cancelled" for meetings that are going ahead.
        The passed/tentative check is done against the local time in Fort
        Worth instead of the base class's datetime.now().
        """
        status = self._get_status(
            {"title": meeting["title"], "start": meeting["start"]},
            text="cancelled" if is_cancelled else "",
        )
        if status == CANCELLED:
            return CANCELLED
        if meeting["start"] < self._local_now():
            return PASSED
        return TENTATIVE

    def _parse_location(self, meeting_data):
        """
        Builds the address from the structured address fields rather than
        "Formatted", which repeats the city and postcode when the Street
        field already holds a full address, e.g. "100 FORT WORTH TRAIL,
        FORT WORTH, TEXAS 76102, Fort Worth, 76115", and contains the
        placeholder suburb "Other" for meetings outside Fort Worth.
        """
        address = meeting_data.get("Address") or {}
        venue = self._clean_location_part(address.get("Venue"))
        street = self._clean_location_part(address.get("Street"))
        suburb = self._clean_location_part(address.get("Suburb"))
        postcode = self._clean_location_part(address.get("PostCode"))

        if not venue and not street:
            return {"name": "TBD", "address": ""}

        if re.search(r"\b\d{5}(-\d{4})?$", street):
            # Street already holds a complete address
            full_address = street
        else:
            if suburb.lower() == "other":
                suburb = ""
            full_address = ", ".join(
                part for part in [street, suburb, postcode] if part
            )

        return {"name": venue, "address": full_address}

    def _clean_location_part(self, value):
        return " ".join((value or "").split()).strip(" ,")

    def _parse_links(self, meeting_data):
        if href := meeting_data.get("Link"):
            return [{"title": "Meeting Details", "href": href}]
        return []

    def _parse_event_page(self, response):
        """
        Returns the set of cancelled dates on an event page.

        The page is shared by every date of the event. A date counts as
        cancelled when an attachment for it says so, e.g. "10-16-2025
        CANCELED TIF 13 Agenda", or when a header notice names it, e.g.
        "12/15/2025 Art Commission meeting CANCELED!". A header notice
        without a date, e.g. "HEARING CANCELED", applies to the "Next date"
        shown above it. A postponed or rescheduled notice only cancels its
        first date, not the date it moved to.
        """
        if not isinstance(response, TextResponse):
            return None

        cancelled_dates = set()
        for doc in response.css("a.document"):
            text = " ".join(" ".join(doc.xpath("./text()").getall()).split())
            title = doc.attrib.get("title", "")
            href = doc.attrib.get("href", "")
            filename = href.rsplit("/", 1)[-1]

            parts = (text, title, filename)
            if any(self.cancel_re.search(part) for part in parts):
                doc_dates = (
                    self._parse_document_dates(text)
                    or self._parse_document_dates(title)
                    or self._parse_document_dates(filename)
                )
                cancelled_dates.update(self._source_dates(doc_dates, parts))

        header = response.xpath("//h1[contains(@class, 'oc-page-title')]/..")
        if header:
            notices = [
                " ".join(" ".join(p.css("*::text").getall()).split())
                for p in header[0].xpath(
                    "./p[not(contains(@class, 'event-date'))]"
                    "[not(preceding-sibling::h2)]"
                )
            ]
            next_date = self._parse_next_date(
                " ".join(header[0].css("p.event-date ::text").getall())
            )
            for notice in filter(self.cancel_re.search, notices):
                if notice_dates := self._parse_notice_dates(notice):
                    cancelled_dates.update(self._source_dates(notice_dates, [notice]))
                elif next_date:
                    cancelled_dates.add(next_date)
                elif not cancelled_dates:
                    self.logger.warning(
                        f"Cancellation notice {notice!r} on {response.url} could "
                        "not be matched to a meeting date"
                    )

        return cancelled_dates

    def _source_dates(self, dates, texts):
        # "10/15/2026 meeting rescheduled to 10/20/2026" moves the meeting
        # rather than cancelling 10/20
        if any(self.cancel_only_re.search(text) for text in texts):
            return dates
        return dates[:1]

    def _parse_document_dates(self, text):
        dates = []
        for month, day, year in self.document_date_re.findall(text):
            year = int(year) + 2000 if len(year) == 2 else int(year)
            try:
                dates.append(date(year, int(month), int(day)))
            except ValueError:
                self.logger.warning(f"Invalid date in {text!r}")
        return dates

    def _parse_notice_dates(self, text):
        dates = []
        for month, day, year in self.us_date_re.findall(text):
            try:
                dates.append(date(int(year), int(month), int(day)))
            except ValueError:
                self.logger.warning(f"Invalid date in {text!r}")
        return dates

    def _parse_next_date(self, text):
        if match := self.long_date_re.search(text):
            return datetime.strptime(" ".join(match.groups()), "%B %d %Y").date()
        return None

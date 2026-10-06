from datetime import datetime
from zoneinfo import ZoneInfo

import scrapy
from city_scrapers_core.constants import CANCELLED, CITY_COUNCIL, PASSED, TENTATIVE
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from curl_cffi import requests as curl_requests


class FortxFortWorthCityCouncilSpider(CityScrapersSpider):
    name = "fortx_Fort_Worth_City_Council"
    agency = "Fort Worth City Council"
    timezone = "America/Chicago"

    tz = ZoneInfo(timezone)

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
    }

    main_url = "https://www.fortworthtexas.gov/"

    meetings_url = "https://www.fortworthtexas.gov/ocapi/calendars/getcalendaritems"
    calendar_url = "https://www.fortworthtexas.gov/calendar/city-council"

    meetings_url_payload = {
        "LanguageCode": "en-US",
        "Ids": ["8a8add9a-3fd0-4b39-9a3e-d58e98e27acc"],
        "StartDate": "",
        "EndDate": "",
    }

    meeting_detail_url = (
        "https://www.fortworthtexas.gov/ocapi/get/contentinfo"
        "?calendarId={calendarId}&contentId={contentId}&language=en-US"
        "&currentDateTime={currentDateTime}&mainContentId={mainContentId}"
    )

    def start_requests(self):
        """
        The meeting items for this organization are
        fetched from two of its API endpoints. The
        main API endpoint allows fetching meeting
        items for the entirety of one year. The
        spider is set to fetch all meetings 6 months
        in the past and 6 months in the future.

        Uses curl_cffi for POST requests to bypass
        TLS fingerprinting / WAF bot protection.
        """
        current_date = datetime.now(tz=self.tz)
        payloads = self.construct_payloads(current_date)

        for payload in payloads:
            if payload["StartDate"] == payload["EndDate"]:
                continue

            response = curl_requests.post(
                self.meetings_url,
                json=payload,
                impersonate="chrome120",
            )

            if response.status_code != 200:
                self.logger.warning(
                    f"Unexpected response from {self.meetings_url}: "
                    f"status={response.status_code}"
                )
                continue

            yield from self.parse(response.json())

    def parse(self, data):
        items = []
        for meeting in data["data"]:
            items.extend(meeting["Items"])

        for item in items:
            date_obj = datetime.strptime(
                item["DateTime"], "%d/%m/%Y %I:%M:%S %p"
            ).replace(tzinfo=self.tz)
            currentDateTime = date_obj.strftime("%d/%m/%Y%%20%I:%M:%S%%20%p")

            meeting_detail_url = self.meeting_detail_url.format(
                calendarId=item["CalendarId"],
                contentId=item["Id"],
                currentDateTime=currentDateTime,
                mainContentId=item["MainContentId"],
            )

            yield scrapy.Request(
                url=meeting_detail_url,
                method="GET",
                callback=self.parse_meeting,
                cb_kwargs={"item": item},
            )

    def parse_meeting(self, response, item):
        data = response.json()
        meeting_data = data["data"]

        meeting_start = datetime.strptime(
            item["DateTime"], "%d/%m/%Y %I:%M:%S %p"
        ).replace(tzinfo=self.tz)

        meeting = Meeting(
            title=meeting_data["Title"],
            description=meeting_data["Description"],
            classification=CITY_COUNCIL,
            start=meeting_start.replace(tzinfo=None),
            end=None,
            all_day=False,
            time_notes="Please check the meeting description for details on the start time",  # noqa
            location=self._parse_location(meeting_data),
            links=self._parse_links(meeting_data),
            source=meeting_data.get("Link", self.calendar_url),
        )

        meeting["status"] = self._parse_status(meeting, meeting_data)
        meeting["id"] = self._get_id(meeting)

        yield meeting

    def _parse_status(self, meeting, item):
        """
        The get status method is overriden to only check the meeting
        title and not the description as some meetings have the word
        "cancelled" in the description but are not actually cancelled.
        """
        meeting_text = meeting.get("title", "").lower()
        is_cancelled = item.get("IsCancelled", False)

        if (
            any(word in meeting_text for word in ["cancel", "rescheduled", "postpone"])
            or is_cancelled
        ):
            return CANCELLED
        if meeting["start"] < datetime.now():
            return PASSED
        return TENTATIVE

    def _parse_location(self, item):
        """
        Some meeting items' Address fields are returned empty.
        In such cases, the meeting is set to the default address.
        """
        location = item["Address"]
        name = location.get("Venue") or location.get("Suburb")
        address = location.get("Formatted").split(", ")
        address.pop(0) if len(address) > 1 else None
        address = ", ".join(address)

        if name == "Fort Worth":
            return {"name": "City Hall", "address": "200 Texas St., Fort Worth, 76102"}
        return {"name": name, "address": address}

    def _parse_links(self, meeting_data):
        if href := meeting_data["Link"]:
            return [
                {"title": "Meeting Details", "href": href},
            ]
        return []

    def construct_payloads(self, current_date):
        """
        The start and end dates parameters for this organization main
        API endpoint requires the dates to be within the same year.
        This means it can't be used to fetch meetings spanning months
        from different years. This method constructs date ranges for the
        current year, one year to the past and one year to the future.
        """
        payloads = []

        for year in range(current_date.year - 1, current_date.year + 2):
            payload = self.meetings_url_payload.copy()
            payload["StartDate"] = str(datetime(year, 1, 1, tzinfo=self.tz))
            payload["EndDate"] = str(datetime(year, 12, 31, tzinfo=self.tz))
            payloads.append(payload)

        return payloads

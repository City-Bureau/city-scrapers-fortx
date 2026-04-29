import json
from datetime import datetime
from zoneinfo import ZoneInfo

import scrapy
from city_scrapers_core.constants import CANCELLED, CITY_COUNCIL, PASSED, TENTATIVE
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider


class FortxFortWorthPublicMeetingsSpider(CityScrapersSpider):
    name = "fortx_Fort_Worth_Public_Meetings"
    agency = "Fort Worth Public Meetings"
    timezone = "America/Chicago"
    custom_settings = {
        "ROBOTSTXT_OBEY": False,
    }

    tz = ZoneInfo(timezone)

    meetings_url = "https://www.fortworthtexas.gov/ocapi/calendars/getcalendaritems"

    calendar_url = "https://www.fortworthtexas.gov/calendar/public-meetings"

    meetings_url_payload = {
        "LanguageCode": "en-US",
        "Ids": ["8efac0b6-9ea3-402e-b7d9-e9e71a2a34a0"],
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
        being fetched from two of its API endpoints.
        The main API endpoint allows fetching meeting
        items for the entirety of one year. The
        spider is set to fetch all meetings for the
        current year, one year to the past and one
        year to the future.
        """
        current_date = datetime.now(tz=self.tz)
        payloads = self.construct_payloads(current_date)
        for payload in payloads:
            yield scrapy.Request(
                url=self.meetings_url,
                method="POST",
                body=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                callback=self.parse,
            )

    def parse(self, response):
        data = response.json()

        items = [item for meeting in data["data"] for item in meeting["Items"]]

        for item in items:
            date_obj = datetime.strptime(item["DateTime"], "%d/%m/%Y %I:%M:%S %p")
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
                cb_kwargs={"start_time": date_obj},
            )

    def parse_meeting(self, response, start_time):
        data = response.json()
        meeting_data = data["data"]

        meeting = Meeting(
            title=meeting_data["Title"],
            description=self._parse_description(meeting_data),
            classification=CITY_COUNCIL,
            start=start_time,
            end=None,
            all_day=False,
            time_notes="Please check the meeting description for details on the start time",  # noqa
            location=self._parse_location(meeting_data),
            links=self._parse_links(meeting_data),
            source=meeting_data.get("Link") or self.calendar_url,
        )

        meeting["status"] = self._parse_status(meeting, meeting_data)
        meeting["id"] = self._get_id(meeting)

        yield meeting

    def _parse_status(self, meeting, item):
        """
        The get status method is overridden to only check the meeting
        title and not the description as some meetings have the word
        "cancelled" in the description but are not actually cancelled.
        """
        meeting_text = meeting.get("title", "").lower()
        is_cancelled = item.get("IsCancelled", False)

        if (
            any(word in meeting_text for word in ["cancel", "rescheduled", "postpone"])
            or is_cancelled is True
        ):
            return CANCELLED
        if meeting["start"] < datetime.now():
            return PASSED
        return TENTATIVE

    def _parse_description(self, item):
        description = item.get("Description") or ""
        return description.replace("\r", "").replace("\n", "")

    def _parse_location(self, item):
        """
        Some meeting items' Address fields are returned empty.
        In such cases, the meeting is held via WebEx.
        """
        location = item["Address"]
        name = location.get("Venue") or location.get("Suburb")
        address = location.get("Formatted", "").split(", ")
        if len(address) > 1:
            address.pop(0)
        address = ", ".join(address)

        if not name and not address:
            return {"name": "WebEx", "address": "WebEx"}
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

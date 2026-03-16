import json
from datetime import datetime

import scrapy
from city_scrapers_core.constants import CITY_COUNCIL
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from dateutil.relativedelta import relativedelta


class FortxFortWorthPublicMeetingsSpider(CityScrapersSpider):
    name = "fortx_Fort_Worth_Public_Meetings"
    agency = "Fort Worth Public Meetings"
    timezone = "America/Chicago"
    custom_settings = {
        "ROBOTSTXT_OBEY": False,
    }

    main_url = "https://www.fortworthtexas.gov/"

    meetings_url = "https://www.fortworthtexas.gov/ocapi/calendars/getcalendaritems"

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
        spider is set to fetch all meetings 6 months
        in the past and 6 months in the future.
        """
        current_date = datetime.now()
        payloads = self.construct_payloads(current_date)
        for payload in payloads:
            if payload["StartDate"] == payload["EndDate"]:
                continue
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
            links=[],
            source=meeting_data.get("Link", response.url),
        )

        meeting["status"] = self._parse_status(meeting, meeting_data)
        meeting["id"] = self._get_id(meeting)

        yield meeting

    def _parse_status(self, meeting, item):
        if item["IsCancelled"]:
            return "cancelled"
        return self._get_status(meeting)

    def _parse_description(self, item):
        description = item["Description"]
        description = description.replace("\r", "").replace("\n", "")
        return description

    def _parse_location(self, item):
        """
        Some meeting items' Address fields are returned empty.
        In such cases, the meeting is held via WebEx.
        """
        location = item["Address"]
        name = location.get("Venue") or location.get("Suburb")
        address = location.get("Formatted").split(", ")
        if len(address) > 1:
            address.pop(0)
        address = ", ".join(address)

        if not name and not address:
            return {"name": "WebEx", "address": "WebEx"}
        return {"name": name, "address": address}

    def construct_payloads(self, current_date):
        """
        The start and end dates parameters for this organization main
        API endpoint requires the dates to be within the same year.
        This means it can't be used to fetch meetings spanning months
        from different years. This method constructs start and end date
        ranges covering 6 months in the past through the end of the
        current year, splitting into separate payloads per year.
        """
        past = current_date - relativedelta(months=6)

        def _create_payload(start_date, end_date):
            payload = self.meetings_url_payload.copy()
            payload["StartDate"] = start_date
            payload["EndDate"] = end_date
            return payload

        payloads = [_create_payload(past.strftime("%Y-%m-%d"), f"{past.year}-12-31")]

        # Add current year if it differs from the past year
        if current_date.year != past.year:
            payloads.append(
                _create_payload(
                    f"{current_date.year}-01-01", f"{current_date.year}-12-31"
                )
            )

        return payloads

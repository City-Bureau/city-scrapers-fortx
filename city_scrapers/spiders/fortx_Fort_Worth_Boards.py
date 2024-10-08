import requests
from city_scrapers_core.constants import COMMISSION
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from dateutil.parser import parse


class FortxFortWorthBoardsSpider(CityScrapersSpider):
    name = "fortx_Fort_Worth_Boards"
    agency = "Fort Worth Boards and Commissions"
    timezone = "America/Chicago"
    # original URL
    # https://www.fortworthtexas.gov/calendar/boards-commission
    # API endpoint after initial page load
    # https://www.fortworthtexas.gov/ocapi/calendars/getcalendaritems?Ids=788ffb59-05d1-457d-b9dd-423d4b95a06e&LanguageCode=en-US
    # API endpoint when clicking on calendar
    # https://www.fortworthtexas.gov/ocapi/get/contentinfo?calendarId=788ffb59-05d1-457d-b9dd-423d4b95a06e&contentId=e3182d81-2385-4796-809f-8a330d1c7ec9&language=en-US&mainContentId=e3182d81-2385-4796-809f-8a330d1c7ec9
    start_urls = [
        "https://www.fortworthtexas.gov/ocapi/calendars/getcalendaritems?Ids=788ffb59-05d1-457d-b9dd-423d4b95a06e&LanguageCode=en-US"  # noqa
    ]

    def parse(self, response):
        """
        Parse meetings from multiple API responses.
        """

        data = response.json()

        for calendar_day in data["data"]:
            for item in calendar_day["Items"]:
                # make another API requests to get more info about meeting
                info_url = f"https://www.fortworthtexas.gov/ocapi/get/contentinfo?calendarId={item['CalendarId']}&contentId={item['Id']}&language=en-US&mainContentId={item['Id']}"  # noqa
                headers = {"User-Agent": ""}
                info = requests.get(info_url, headers=headers).json()["data"]

                meeting = Meeting(
                    title=item["Name"],
                    description=info["Description"],
                    classification=COMMISSION,
                    start=parse(item["DateTime"], dayfirst=True),
                    end=None,
                    all_day=False,
                    time_notes="",
                    location=self._parse_location(info),
                    links=self._parse_links(info),
                    source=self._parse_source(response),
                )

                meeting["status"] = self._get_status(meeting)
                meeting["id"] = self._get_id(meeting)

                yield meeting

    def _parse_location(self, info):
        """
        Generate location from another API call.
        The API call is triggered by clicking on a calendar item on the page.
        """
        obj = info["Address"]
        venue = obj["Venue"]
        street = obj["Street"]
        suburb = obj["Suburb"]
        zip = obj["PostCode"]
        values = [street, suburb, zip, "TX"]

        # filter out empty strings
        address = ", ".join(value for value in values if value)

        return {"name": venue, "address": address}

    def _parse_links(self, info):
        """Parse or generate links."""
        links = []
        link = info["Link"]
        if link:
            links.append({"title": "Link", "href": link})
        return links

    def _parse_source(self, response):
        """
        Hardcode source since actual source is an API endpoint and is not user friendly.
        """
        return "https://www.fortworthtexas.gov/calendar/boards-commission"

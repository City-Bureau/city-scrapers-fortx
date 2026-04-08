import json
import re
from datetime import datetime

import scrapy
from city_scrapers_core.constants import BOARD, COMMISSION, COMMITTEE, NOT_CLASSIFIED
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from dateutil.parser import parse as dateparse


class FortxTarrantCountyCommissionersCourtSpider(CityScrapersSpider):
    name = "fortx_Tarrant_County_Commissioners_Court"
    agency = "Tarrant County Commissioners Court"
    timezone = "America/Chicago"

    """
    The scraper gathers meeting information from two separate endpoints
    specified below. One endpoint provides archived meetings, and the
    other provides current and upcoming meetings.

    The archived data is taken through a POST request with a payload
    containing the committee ID. The upcoming meetings are accessed
    through a GET request that requires a Bearer token for authentication.
    The upcoming meetings are fetched first for the year of the last archived
    and then on an yearly basis.
    """

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
    }

    archived_url = "https://tarrant-agendamanagement-public.techsharetx.gov/publicportal/api/meetings/readArchived"  # noqa
    upcoming_url = "https://api-dev.agendalink.app/api/engage/agendas/tarrantcountytx?span={year}&department=all"  # noqa
    attachments_url = "https://tarrant-agendamanagement-public.techsharetx.gov/publicportal/api/meetingattachments/download?id="  # noqa
    source_url = "https://www.tarrantcountytx.gov/en/commissioners-court/commissioners-court-agenda-videos.html"  # noqa
    youtube_url = "https://www.youtube.com/watch?v={video_id}"  # noqa

    committee_id = "fe6aa5cc-7448-4194-ac6e-08dc95f79ccc"
    bearer_token = "eyJhbGciOiJIUzI1NiJ9.eyJSb2xlIjoiQWRtaW4iLCJJc3N1ZXIiOiJJc3N1ZXIiLCJVc2VybmFtZSI6IkphdmFJblVzZSIsImV4cCI6MTY0MzIzMzY5NCwiaWF0IjoxNjQzMjMzNjk0fQ.5C2WIXm6xGY63E_6k3wnCcT3YstnTj-J2UWdZuuJbW8"  # noqa

    location = {
        "address": "100 East Weatherford Street, 5th Floor, Fort Worth, Texas, 76196",  # noqa
        "name": "Tarrant County Administration Building (check the agenda for room location)",  # noqa
    }

    def start_requests(self):
        payload = {"committeeId": self.committee_id}
        yield scrapy.Request(
            url=self.archived_url,
            method="POST",
            body=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            callback=self.parse_archived,
        )

    def parse_archived(self, response):
        archived_response = response.json()
        archived_meetings = archived_response.get("data", [])

        last_archived_meeting = self._parse_datetime(
            archived_meetings[0].get("meetingStartDateTime")
        )

        yield scrapy.Request(
            url=self.upcoming_url.format(year=last_archived_meeting.year),
            headers={"Authorization": f"Bearer {self.bearer_token}"},
            callback=self.parse_upcoming,
            meta={
                "archived_meetings": archived_meetings,
            },
        )

    def parse_upcoming(self, response):
        upcoming_response = response.json()
        archived_meetings = response.meta["archived_meetings"]

        current_year = datetime.now().year

        yield scrapy.Request(
            url=self.upcoming_url.format(year=current_year),
            headers={"Authorization": f"Bearer {self.bearer_token}"},
            callback=self.parse,
            meta={
                "archived_meetings": archived_meetings,
                "remaining_archived_meetings": upcoming_response,
            },
        )

    def parse(self, response):
        upcoming = response.json()
        archived_meetings = (
            response.meta["archived_meetings"]
            + response.meta["remaining_archived_meetings"]
        )
        meetings = self._filtered_meetings(archived_meetings, upcoming)
        for item in meetings:
            title = item.get("title", "Commissioners Court")
            classification = self._parse_classification(title)
            meeting = Meeting(
                title=title,
                description="",
                classification=classification,
                start=item.get("start"),
                end=item.get("end"),
                all_day=False,
                time_notes="",
                location=item.get("location"),
                links=item.get("links", []),
                source=self.source_url,
            )

            meeting["status"] = self._get_status(meeting)
            meeting["id"] = self._get_id(meeting)

            yield meeting

    def _parse_classification(self, title):
        classification_map = {
            "commission": COMMISSION,
            "committee": COMMITTEE,
            "board": BOARD,
        }
        for key, classification in classification_map.items():
            if key in title.lower():
                return classification
        return NOT_CLASSIFIED

    def _filtered_meetings(self, archived, upcoming):
        meetings = []
        for item in archived + upcoming:
            # Upcoming meetings have '_id', archived have 'id'
            if item.get("_id"):
                meeting = self._parse_upcoming_meeting(item)
            else:
                meeting = self._parse_archived_meeting(item)
            meetings.append(meeting)
        return meetings

    def _parse_upcoming_meeting(self, item):
        department = item.get("department", {})
        return {
            "id": item["_id"],
            "title": department.get("name", "Commissioners Court"),
            "start": self._parse_datetime(item.get("scheduleDate")),
            "end": None,
            "location": self._parse_upcoming_location(item.get("room")),
            "links": self._parse_upcoming_links(item),
        }

    def _parse_archived_meeting(self, item):
        return {
            "id": item["id"],
            "title": item.get("description", "Commissioners Court"),
            "start": self._parse_datetime(item.get("meetingStartDateTime")),
            "end": self._parse_datetime(item.get("meetingEndDateTime")),
            "location": self.location,
            "links": self._parse_links(item),
        }

    def _parse_datetime(self, datetime_str):
        """
        Parse the datetime string into a datetime object.
        """
        if datetime_str:
            parsed_datetime = dateparse(datetime_str)
            if parsed_datetime.tzinfo is not None:
                return parsed_datetime.replace(tzinfo=None)
            return parsed_datetime
        return None

    def _parse_links(self, item):
        link_config = [
            ("agendaAttachmentId", "Agenda", lambda id: self.attachments_url + id),
            ("minutesAttachmentId", "Minutes", lambda id: self.attachments_url + id),
            ("videoId", "Video", lambda id: self.youtube_url.format(video_id=id)),
        ]
        links = []
        for key, title, url_builder in link_config:
            if attachment_id := item.get(key):
                links.append(
                    {
                        "title": title,
                        "href": url_builder(attachment_id),
                    }
                )
        return links

    def _parse_video_link(self, video_url):
        video_id = re.search(r"embed/(.+?)\?", video_url)
        if video_id:
            return self.youtube_url.format(video_id=video_id.group(1))

    def _parse_upcoming_links(self, item):
        link_config = [
            ("agendaPdfUrl", "Agenda", lambda url: url),
            ("agendaPacketUrl", "Agenda Packet", lambda url: url),
            ("minutesPdfUrl", "Minutes", lambda url: url),
            ("videoUrl", "Video", self._parse_video_link),
        ]
        links = []
        for key, title, url_builder in link_config:
            if url := item.get(key):
                links.append(
                    {
                        "title": title,
                        "href": url_builder(url),
                    }
                )
        return links

    def _parse_upcoming_location(self, room_obj):
        if room_obj:
            address = room_obj.get("address", "")
            address_parts = [
                address.get("street", ""),
                address.get("city", ""),
                address.get("state", ""),
                address.get("zipCode", ""),
            ]
            full_address = ", ".join(part for part in address_parts if part)
            return {
                "address": full_address.strip(),
                "name": room_obj.get("roomName", ""),
            }

        return self.location

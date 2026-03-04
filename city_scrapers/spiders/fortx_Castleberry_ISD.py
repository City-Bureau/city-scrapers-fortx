import re
from collections import defaultdict
from urllib.parse import urljoin

from city_scrapers_core.constants import BOARD
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from dateutil.parser import parse


class FortxCastleberryIsdSpider(CityScrapersSpider):
    name = "fortx_Castleberry_ISD"
    agency = "Castleberry ISD Board"
    timezone = "America/Chicago"
    start_urls = ["https://meetings.boardbook.org/Public/Organization/1090"]
    base_url = "https://meetings.boardbook.org"

    def _clean_text(self, text):
        return re.sub(r"\s+", " ", text).strip() if text else ""

    def parse(self, response):
        raw_meetings = []
        for item in response.css("table tbody tr[class*='row-for-board']"):
            start, has_explicit_time = self._parse_start(item)
            if not start:
                continue
            raw_meetings.append(
                {
                    "title": self._parse_title(item),
                    "start": start,
                    "has_explicit_time": has_explicit_time,
                    "time_notes": self._parse_time_notes(item),
                    "location": self._parse_location(item),
                    "links": self._parse_links(item),
                    "source": response.url,
                }
            )

        date_groups = defaultdict(list)
        for i, m in enumerate(raw_meetings):
            date_groups[m["start"].date()].append(i)

        for indices in date_groups.values():
            explicit_times = [
                raw_meetings[i]["start"]
                for i in indices
                if raw_meetings[i]["has_explicit_time"]
            ]
            if explicit_times:
                shared_time = explicit_times[0]
                for i in indices:
                    if not raw_meetings[i]["has_explicit_time"]:
                        orig = raw_meetings[i]["start"]
                        raw_meetings[i]["start"] = orig.replace(
                            hour=shared_time.hour,
                            minute=shared_time.minute,
                            second=shared_time.second,
                        )

        for m in raw_meetings:
            time_notes = m["time_notes"]
            if not m["has_explicit_time"]:
                note = "Start time not listed; estimated from same-day meeting"
                time_notes = f"{time_notes}; {note}" if time_notes else note

            meeting = Meeting(
                title=m["title"],
                description="",
                classification=BOARD,
                start=m["start"],
                end=None,
                all_day=False,
                time_notes=time_notes,
                location=m["location"],
                links=m["links"],
                source=m["source"],
            )
            meeting["status"] = self._get_status(meeting)
            meeting["id"] = self._get_id(meeting)
            yield meeting

    def _parse_title(self, item):
        text = item.css("td")[0].css("div").xpath("string()").get()
        if not text:
            return ""
        text = text.strip()
        if " - " in text:
            return text.split(" - ", 1)[1].strip()
        return text

    def _parse_start(self, item):
        text = item.css("td")[0].css("div").xpath("string()").get()
        if not text:
            return None, False
        text = text.strip()
        match = re.search(r"(\w+ \d+, \d{4})", text)
        if match:
            date_str = match.group(1)
            time_match = re.search(r"at (\d+:\d+ [AP]M)", text)
            if time_match:
                return parse(f"{date_str} {time_match.group(1)}"), True
            return parse(f"{date_str} 12:00 AM"), False
        return None, False

    def _parse_time_notes(self, item):
        text = item.css("td")[0].css("div").xpath("string()").get()
        if not text:
            return ""
        text = text.strip()
        if "Will begin immediately following" in text:
            match = re.search(r"(Will begin immediately following[^-]+)", text)
            if match:
                return match.group(1).strip()
        return ""

    def _parse_location(self, item):
        location_td = item.css("td")[1]
        spans = [self._clean_text(t) for t in location_td.css("span::text").getall()]
        name = spans[0] if spans else ""
        line1 = spans[1] if len(spans) > 1 else ""
        line2 = spans[2] if len(spans) > 2 else ""
        address = ", ".join([part for part in (line1, line2) if part])
        return {"name": name, "address": address}

    def _parse_links(self, item):
        output = []
        links = item.css("td")[2].css("a")
        for link in links:
            title = link.css("::text").get()
            if title:
                title = title.strip()
            href = link.css("::attr(href)").get()
            if href:
                href = urljoin(self.base_url, href)
                output.append({"title": title, "href": href})
        return output

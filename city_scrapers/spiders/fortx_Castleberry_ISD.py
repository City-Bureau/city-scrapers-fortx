import re
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

    def _clean_text(self, text):
        return re.sub(r"\s+", " ", text).strip() if text else ""

    def parse(self, response):
        for item in response.css("table tbody tr[class*='row-for-board']"):
            start = self._parse_start(item)
            if not start:
                continue
            meeting = Meeting(
                title=self._parse_title(item),
                description="",
                classification=BOARD,
                start=start,
                end=None,
                all_day=False,
                time_notes=self._parse_time_notes(item),
                location=self._parse_location(item),
                links=self._parse_links(item),
                source=self._parse_source(response),
            )

            meeting["status"] = self._get_status(meeting)
            meeting["id"] = self._get_id(meeting)

            yield meeting

    def _parse_title(self, item):
        text = item.css("td")[0].css("div::text").get()
        if not text:
            return ""
        text = text.strip()
        if " - " in text:
            parts = text.split(" - ", 1)
            return parts[1].strip() if len(parts) > 1 else text
        return text

    def _parse_start(self, item):
        text = item.css("td")[0].css("div::text").get()
        if not text:
            return None
        text = text.strip()
        match = re.search(r"(\w+ \d+, \d{4})", text)
        if match:
            date_str = match.group(1)
            time_match = re.search(r"at (\d+:\d+ [AP]M)", text)
            time_str = time_match.group(1) if time_match else "12:00 AM"
            return parse(f"{date_str} {time_str}")
        return None

    def _parse_time_notes(self, item):
        text = item.css("td")[0].css("div::text").get()
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
        base_url = "https://meetings.boardbook.org"
        output = []
        map_link = item.css("td")[1].css("a")
        for link in map_link:
            title = link.css("::text").get()
            if title:
                title = title.strip()
            if "map it" in title:
                title = "Map Link"
            href = link.css("::attr(href)").get()
            if href:
                output.append({"title": title, "href": href})
        links = item.css("td")[2].css("a")
        for link in links:
            title = link.css("::text").get()
            if title:
                title = title.strip()
            href = link.css("::attr(href)").get()
            if href:
                href = urljoin(base_url, href)
                output.append({"title": title, "href": href})
        return output

    def _parse_source(self, response):
        return response.url

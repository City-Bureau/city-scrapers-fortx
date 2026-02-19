import json
import re
from datetime import datetime

import scrapy
from city_scrapers_core.constants import BOARD, CANCELLED
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from scrapy import Selector


class FortxFortWorthHousingSpider(CityScrapersSpider):
    name = "fortx_fort_worth_housing"
    agency = "Fort Worth Housing Solutions (FWHS) Board of Commissioners"
    timezone = "America/Chicago"

    api_url = "https://fwhs.org/wp-json/tribe/views/v2/html"
    source_url = "https://fwhs.org/about-fwhs/events-calendar/"
    custom_settings = {"ROBOTSTXT_OBEY": False}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seen_event_urls = set()  # Dedupe event URLs across all months
        self.seen_meeting_ids = (
            set()
        )  # Dedupe meetings by ID (same event, different URLs) # noqa

    def start_requests(self):
        # First, visit the calendar page to get fresh nonce values
        yield scrapy.Request(
            url=self.source_url, callback=self.parse_calendar_page
        )  # noqa

    def parse_calendar_page(self, response):
        """Extract fresh nonce values from the calendar page, then make API request."""  # noqa
        # Initialize token values
        tvn1 = None
        tvn2 = None

        # Method 1: Look for the specific nonce data script
        nonce_script = response.css(
            'script[data-js="tribe-events-view-nonce-data"]::text'
        ).get()

        if nonce_script:
            try:
                nonce_data = json.loads(nonce_script)
                tvn1 = nonce_data.get("tvn1")
                tvn2 = nonce_data.get("tvn2")
            except Exception as e:
                self.logger.error(f"Error parsing nonce data: {e}")

        # Validate that we have the required tokens
        if not tvn1:
            self.logger.error("Could not extract tvn1 token from page")
            return

        # Use empty string for tvn2 if not found
        tvn2 = tvn2 or ""

        # Build AJAX payloads for multiple months (including past meetings)
        # Generate months from start_date to end_date automatically
        start_date = datetime(2024, 2, 1)  # Start from February 2024
        end_date = datetime(2026, 3, 31)  # End at March 2026

        months_to_scrape = []
        current = start_date

        while current <= end_date:
            months_to_scrape.append(
                f"/events/month/{current.year}-{current.month:02d}/"
            )
            # Move to next month
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
            current = current.replace(day=1)  # Reset to 1st day

        for month_url in months_to_scrape:
            payload = {
                "tribe_filter_bar_state": 1,
                "tribe_filters_state": 0,
                "u": month_url,
                "shortcode": "475d705f",
                "tvn1": tvn1,
                "tvn2": tvn2,
                "smu": "false",
            }

            # Make POST request to get AJAX content for each month
            yield scrapy.Request(
                url=self.api_url,
                method="POST",
                body=json.dumps(payload),
                headers={
                    "Content-Type": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                },
                callback=self.parse_ajax_response,
                meta={"month_url": month_url},  # Pass month info for debugging
                dont_filter=True,
            )

    def parse_ajax_response(self, response):
        """Parse all data from AJAX response and extract event URLs dynamically."""  # noqa
        month_url = response.meta.get("month_url", "unknown")
        data = response.json()

        html_content = data.get("html", "")
        if not html_content:
            self.logger.info(f"Parsed month {month_url}: no HTML content")
            return

        selector = Selector(text=html_content)

        # Extract event URLs from the AJAX HTML response
        event_links = selector.css('a[href*="/event/"]::attr(href)').getall()

        self.logger.info(
            f"Parsed month {month_url}: found {len(event_links)} event links"
        )

        # Dedupe within this month first
        unique_links = set(event_links)

        for href in unique_links:
            if not href:
                continue

            # Convert relative URLs to absolute URLs
            event_url = response.urljoin(href).split("#")[0]

            # Deduplicate across ALL months
            if event_url in self.seen_event_urls:
                continue
            self.seen_event_urls.add(event_url)

            yield scrapy.Request(url=event_url, callback=self.parse_event_page)

    def parse_event_page(self, response):
        """Parse all data from individual event page."""
        # Do not scrape any events that have "Community Events" in the category
        category = response.css("span.category::text").get()
        if category and category.strip() == "Community Events":
            return

        # Parse everything from the event page
        title = self._parse_title_from_page(response)
        description = self._parse_description_from_page(response)
        start_time = self._parse_start_from_page(response)
        if not start_time:
            return
        end_time = self._parse_end_from_page(response)
        location = self._parse_location_from_page(response)
        links = self._parse_links_from_page(response)

        time_notes = ""
        if description and "cancel" in description.lower():
            time_notes = description
            description = ""

        cancel_info = response.css("p.cancel-info::text, p.canel-info::text").get()
        is_cancelled = cancel_info and "cancel" in cancel_info.lower()

        meeting = Meeting(
            title=title,
            description=description,
            classification=BOARD,
            start=start_time,
            end=end_time,
            all_day=False,
            time_notes=time_notes,
            location=location,
            links=links,
            source=response.url,
        )

        meeting["status"] = CANCELLED if is_cancelled else self._get_status(meeting)
        meeting["id"] = self._get_id(meeting)

        # Dedupe by meeting ID
        if meeting["id"] in self.seen_meeting_ids:
            return
        self.seen_meeting_ids.add(meeting["id"])

        yield meeting

    def _clean_title(self, text: str) -> str:
        if not text:
            return ""
        return text.replace("\u2013", "-").strip()

    def _parse_title_from_page(self, response):
        """Parse title from individual event page."""
        title = response.css("h2::text").get()
        return self._clean_title(title) if title else ""

    def _parse_start_from_page(self, response):
        """Parse start datetime from p.date element using strptime()."""
        date_text = " ".join(response.css("p.date::text").getall())

        # Split at dash to isolate start datetime: "Thursday, January 27, 2026 12:00 PM" # noqa
        parts = re.split(r"\s*[–-]\s*", date_text)
        if parts:
            start_str = parts[0].strip()
            try:
                return datetime.strptime(start_str, "%A, %B %d, %Y %I:%M %p")
            except ValueError:
                return None
        return None

    def _parse_end_from_page(self, response):
        """Parse end datetime from p.date element using strptime()."""
        date_text = " ".join(response.css("p.date::text").getall())

        # Split at dash: ["Thursday, January 27, 2026 12:00 PM", "01:30 PM"]
        parts = re.split(r"\s*[–-]\s*", date_text)
        if len(parts) >= 2:
            end_time_str = parts[1].strip()
            start_dt = self._parse_start_from_page(response)
            if start_dt:
                try:
                    end_time = datetime.strptime(end_time_str, "%I:%M %p")
                    return datetime(
                        start_dt.year,
                        start_dt.month,
                        start_dt.day,
                        end_time.hour,
                        end_time.minute,
                    )
                except ValueError:
                    return None
        return None

    def _parse_location_from_page(self, response):
        """Parse location from individual event page."""
        location_name = response.css(".location p strong::text").get()

        # Get full address from <a> title attribute
        address = response.css(".location p a::attr(title)").get()

        return {
            "name": location_name.strip() if location_name else "",
            "address": address.strip() if address else "",
        }

    def _parse_description_from_page(self, response):
        """Parse description from div.evt_left p element (excluding p.date)."""
        # Get p elements that are NOT the date paragraph
        paragraphs = response.css("div.evt_left p:not(.date)::text").getall()
        for p_text in paragraphs:
            text = p_text.strip()
            if (
                text
                and len(text) > 30
                and "\u2026" not in text
                and not text.startswith(
                    (
                        "Monday",
                        "Tuesday",
                        "Wednesday",
                        "Thursday",
                        "Friday",
                        "Saturday",
                        "Sunday",
                    )
                )
                and "please email" not in text.lower()
            ):
                return text
        return ""

    def _parse_links_from_page(self, response):
        """Parse relevant links from individual event page - agendas and supplemental docs."""  # noqa
        links = []
        seen_hrefs = set()

        # Supplemental documents from document_era section
        doc_links = response.css("div.document_era a.doc_block")
        for link in doc_links:
            href = link.css("::attr(href)").get()
            title = link.css("span::text").get()

            # Skip broken links (those with HTML content in href)
            if href and not href.startswith("<") and ".pdf" in href.lower():
                if href not in seen_hrefs:
                    seen_hrefs.add(href)
                    normalized_title = title.strip() if title else "Document"
                    if normalized_title.lower().startswith("download agenda pdf"):
                        normalized_title = normalized_title.replace(
                            "Download Agenda PDF", "Agenda"
                        ).replace("download agenda pdf", "Agenda")
                    links.append(
                        {
                            "title": normalized_title,
                            "href": response.urljoin(href.strip()),
                        }
                    )

        # Also check for agenda links in other sections
        agenda_links = response.css(
            "a[href*='agenda'][href$='.pdf'], a[href*='Agenda'][href$='.pdf']"
        )
        for link in agenda_links:
            href = link.css("::attr(href)").get()
            title = link.css("::text").get() or link.css("span::text").get()

            if href and href not in seen_hrefs:
                seen_hrefs.add(href)
                normalized_title = title.strip() if title else "Agenda"
                if normalized_title.lower().startswith("download agenda pdf"):
                    normalized_title = normalized_title.replace(
                        "Download Agenda PDF", "Agenda"
                    ).replace("download agenda pdf", "Agenda")
                links.append(
                    {
                        "title": normalized_title,
                        "href": response.urljoin(href.strip()),
                    }
                )
        return links

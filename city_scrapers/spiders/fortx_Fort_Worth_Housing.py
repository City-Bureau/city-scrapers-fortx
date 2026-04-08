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
    WEEKDAYS = (
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    )

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

        # Extract nonce from script tag
        nonce_script = response.css(
            'script[data-js="tribe-events-view-nonce-data"]::text'
        ).get()

        if nonce_script:
            try:
                nonce_data = json.loads(nonce_script)
                tvn1 = nonce_data.get("tvn1")
                tvn2 = nonce_data.get("tvn2")
            except json.JSONDecodeError as e:
                self.logger.error(f"Error parsing nonce data: {e}")

        # Validate that we have the required tokens
        if not tvn1:
            self.logger.error("Could not extract tvn1 token from page")
            return

        # Extract shortcode dynamically from the calendar page
        shortcode = response.css(
            'div[data-js="tribe-events-view"]::attr(data-view-shortcode)'
        ).get()  # noqa
        if not shortcode:
            self.logger.error("Could not extract shortcode from page")
            return

        # Use empty string for tvn2 if not found
        tvn2 = tvn2 or ""

        # Build AJAX payloads for multiple months (including past meetings)
        # Generate months from start_date to end_date automatically
        start_date = datetime(2024, 2, 1)  # Start from February 2024
        now = datetime.now()
        end_date = datetime(now.year + 1, now.month, 1)

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

        for month_url in months_to_scrape:
            payload = {
                "tribe_filter_bar_state": 1,
                "tribe_filters_state": 0,
                "u": month_url,
                "shortcode": shortcode,
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

        # Extract event URLs from JSON-LD structured data
        json_ld_text = selector.css('script[type="application/ld+json"]::text').get()
        events = json.loads(json_ld_text) if json_ld_text else []
        event_links = [
            event["url"] for event in events if event.get("@type") == "Event"
        ]
        for href in event_links:
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
        start_time, end_time = self._parse_start_end_from_page(response)
        if not start_time:
            return
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
        text = re.sub(r"^(CANCELLED|POSTPONED|RESCHEDULED):\s*", "", text.strip())
        return text.replace("\u2013", "-").strip()

    def _parse_title_from_page(self, response):
        """Parse title from individual event page."""
        title = response.css("h2::text").get()
        return self._clean_title(title) if title else ""

    def _parse_start_end_from_page(self, response):
        """Parse start and end datetimes from p.date element."""
        date_text = " ".join(response.css("p.date::text").getall())
        parts = re.split(r"\s*[–-]\s*", date_text)
        if not parts:
            return None, None

        start_str = parts[0].strip()
        try:
            start_dt = datetime.strptime(start_str, "%A, %B %d, %Y %I:%M %p")
        except ValueError:
            return None, None

        end_dt = None
        if len(parts) >= 2:
            end_time_str = parts[1].strip()
            try:
                end_time = datetime.strptime(end_time_str, "%I:%M %p")
                end_dt = start_dt.replace(hour=end_time.hour, minute=end_time.minute)
            except ValueError:
                pass  # end_dt remains None
        return start_dt, end_dt

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
                and not text.startswith(self.WEEKDAYS)
                and "please email" not in text.lower()
            ):
                return text
        return ""

    def _process_link(self, link, response, seen_hrefs, default_title="Document"):
        """Process a single link element and return link dict if valid."""
        href = link.css("::attr(href)").get()
        title = link.css("span::text").get() or link.css("::text").get()

        # Skip broken links (those with HTML content in href)
        if not href or href.startswith("<") or ".pdf" not in href.lower():
            return None

        # Skip duplicates
        if href in seen_hrefs:
            return None

        seen_hrefs.add(href)
        normalized_title = title.strip() if title else default_title
        if normalized_title.lower().startswith("download agenda pdf"):
            normalized_title = "Agenda"
        return {
            "title": normalized_title,
            "href": response.urljoin(href.strip()),
        }

    def _parse_links_from_page(self, response):
        """Parse relevant links from individual event page - agendas and supplemental docs."""  # noqa
        links = []
        seen_hrefs = set()

        # Supplemental documents from document_era section
        doc_links = response.css("div.document_era a.doc_block")
        for link in doc_links:
            processed_link = self._process_link(link, response, seen_hrefs)
            if processed_link:
                links.append(processed_link)

        # Also check for agenda links in other sections
        agenda_links = response.css(
            "a[href*='agenda'][href$='.pdf'], a[href*='Agenda'][href$='.pdf']"
        )
        for link in agenda_links:
            processed_link = self._process_link(link, response, seen_hrefs, "Agenda")
            if processed_link:
                links.append(processed_link)

        return links

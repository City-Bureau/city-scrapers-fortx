# Tutorial: Building the fortx_Castleberry_ISD Spider

This comprehensive guide walks you through building a Scrapy spider for **Castleberry ISD Board** meetings from scratch.

---

## Prerequisites

- Python 3.11+
- `pipenv` installed globally
- Git configured with GitHub access
- Access to the `city-scrapers-fortx` repository

---

## Phase 1: Environment Setup

### Step 1.1: Navigate to the Project Directory

```bash
cd /Users/ao/ctd/apprenticeship/city-scrapers/city-scrapers-fortx
```

### Step 1.2: Activate the Virtual Environment

```bash
pipenv shell
```

This activates the project's isolated Python environment. You should see `(city-scrapers-fortx)` in your terminal prompt.

### Step 1.3: Install Dependencies (if needed)

```bash
pipenv install --dev
```

This installs all required packages from `Pipfile.lock`.

### Step 1.4: Verify Installation

```bash
pipenv run scrapy --version
```

Expected output: `Scrapy 2.11.1` (or similar)

---

## Phase 2: Create a Feature Branch

### Step 2.1: Ensure You're on Main Branch

```bash
git checkout main
git pull origin main
```

### Step 2.2: Create and Switch to Feature Branch

```bash
git checkout -b feature/spider-fortx_Castleberry_ISD
```

**Naming Convention:** `feature/spider-{spider_name}`

---

## Phase 3: Fetch the HTML Fixture

The fixture is a saved copy of the target webpage used for testing without hitting the live site.

### Step 3.1: Download the HTML

```bash
curl -o tests/files/fortx_Castleberry_ISD.html \
  "https://meetings.boardbook.org/Public/Organization/1090"
```

### Step 3.2: Verify the File

```bash
head -20 tests/files/fortx_Castleberry_ISD.html
```

You should see HTML content starting with `<!DOCTYPE html>`.

---

## Phase 4: Analyze the HTML Structure

Before writing code, understand the data structure.

### Step 4.1: Open the URL in Browser

Visit: https://meetings.boardbook.org/Public/Organization/1090

### Step 4.2: Inspect the HTML (Developer Tools)

Key observations:

- Meetings are in a `<table>` with `<tbody>`
- Each meeting is a `<tr>` row with class `row-for-board`
- Each row has 3 `<td>` columns:
  1. **Column 1 (td[0])**: Date, time, and title in a `<div>`
  2. **Column 2 (td[1])**: Location in `<span>` elements + map link
  3. **Column 3 (td[2])**: Agenda/Projector links

### Step 4.3: Examine Sample Data

```html
<tr class=" row-for-board">
  <td>
    <div>January 20, 2026 at 6:00 PM - Special Meeting</div>
  </td>
  <td>
    <span>Castleberry Board Room</span>
    <span>5228 Ohio Garden</span>
    <span>Fort Worth, TX 76114</span>
    <a href="https://maps.google.com/...">map it</a>
  </td>
  <td>
    <a href="/Public/Agenda/1090?meeting=726957">Agenda</a>
    <a href="/Public/Projector/1090?meeting=726957">Projector</a>
  </td>
</tr>
```

---

## Phase 5: Create the Spider File

### Step 5.1: Create the File

```bash
touch city_scrapers/spiders/fortx_Castleberry_ISD.py
```

### Step 5.2: Add Imports

Open the file and add:

```python
import re
from urllib.parse import urljoin

from city_scrapers_core.constants import BOARD
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from dateutil.parser import parse
```

**Explanation:**

- `re`: Regular expressions for parsing text
- `urljoin`: Construct absolute URLs from relative paths
- `BOARD`: Classification constant for board meetings
- `Meeting`: The data structure for scraped meetings
- `CityScrapersSpider`: Base class with helper methods
- `parse`: Parses date strings into datetime objects

### Step 5.3: Define the Spider Class

```python
class FortxCastleberryIsdSpider(CityScrapersSpider):
    name = "fortx_Castleberry_ISD"
    agency = "Castleberry ISD Board"
    timezone = "America/Chicago"
    start_urls = ["https://meetings.boardbook.org/Public/Organization/1090"]
```

**Explanation:**

- `name`: Unique identifier (used with `scrapy crawl`)
- `agency`: Human-readable name
- `timezone`: For datetime localization
- `start_urls`: Entry point(s) for the spider

### Step 5.4: Add the Main Parse Method

```python
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
```

**Explanation:**

- CSS selector `tr[class*='row-for-board']` matches rows with that class (handles leading space)
- Skip rows where date parsing fails (`if not start: continue`)
- `_get_status` and `_get_id` are inherited helper methods

### Step 5.5: Add `_parse_title` Method

```python
    def _parse_title(self, item):
        text = item.css("td")[0].css("div::text").get()
        if not text:
            return ""
        text = text.strip()
        if " - " in text:
            parts = text.split(" - ", 1)
            return parts[1].strip() if len(parts) > 1 else text
        return text
```

**Logic:**

- Get text from first `<td>`'s `<div>`
- Split on " - " to extract title after the date/time
- Example: `"January 20, 2026 at 6:00 PM - Special Meeting"` → `"Special Meeting"`

### Step 5.6: Add `_parse_start` Method

```python
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
```

**Logic:**

- Extract date using regex: `January 20, 2026`
- Extract time if present: `6:00 PM`
- Default to midnight if no time (e.g., "Will begin immediately following...")
- Use `dateutil.parser.parse()` to create datetime object

### Step 5.7: Add `_parse_time_notes` Method

```python
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
```

**Logic:**

- Capture special timing notes when exact time isn't specified

### Step 5.8: Add `_parse_location` Method

```python
    def _parse_location(self, item):
        location_td = item.css("td")[1]
        name = location_td.css("span::text").get()
        spans = location_td.css("span::text").getall()
        if len(spans) >= 3:
            line1 = spans[1] if len(spans) > 1 else ""
            line2 = spans[2] if len(spans) > 2 else ""
            return {
                "name": name if name else "",
                "address": f"{line1}, {line2}" if line1 and line2 else "",
            }
        return {"name": name if name else "", "address": ""}
```

**Logic:**

- First span = location name
- Second span = street address
- Third span = city, state, zip
- Combine address parts with comma

### Step 5.9: Add `_parse_links` Method

```python
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
```

**Logic:**

- Map link is in column 2 (location column)
- Agenda/Projector links are in column 3
- Use `urljoin` to make relative URLs absolute

### Step 5.10: Add `_parse_source` Method

```python
    def _parse_source(self, response):
        return response.url
```

---

## Phase 6: Create the Test File

### Step 6.1: Create the File

```bash
touch tests/test_fortx_Castleberry_ISD.py
```

### Step 6.2: Add Imports and Setup

```python
from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import BOARD
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.fortx_Castleberry_ISD import (
    FortxCastleberryIsdSpider,
)

test_response = file_response(
    join(dirname(__file__), "files", "fortx_Castleberry_ISD.html"),
    url="https://meetings.boardbook.org/Public/Organization/1090",
)
spider = FortxCastleberryIsdSpider()

freezer = freeze_time("2024-10-31")
freezer.start()

parsed_items = [item for item in spider.parse(test_response)]

freezer.stop()
```

**Explanation:**

- `file_response`: Loads local HTML fixture as a fake Scrapy response
- `freeze_time`: Locks the current date for consistent status calculations
- `parsed_items`: List of all meetings parsed from the fixture

### Step 6.3: Add Test Functions

```python
def test_count():
    assert len(parsed_items) >= 1


def test_title():
    assert parsed_items[0]["title"] == "Special Meeting"


def test_description():
    assert parsed_items[0]["description"] == ""


def test_start():
    assert parsed_items[0]["start"] == datetime(2026, 1, 20, 18, 0)


def test_end():
    assert parsed_items[0]["end"] is None


def test_time_notes():
    assert parsed_items[0]["time_notes"] == ""


def test_id():
    assert (
        parsed_items[0]["id"]
        == "fortx_Castleberry_ISD/202601201800/x/special_meeting"
    )


def test_status():
    assert parsed_items[0]["status"] == "tentative"


def test_location():
    assert parsed_items[0]["location"] == {
        "name": "Castleberry Board Room",
        "address": "5228 Ohio Garden, Fort Worth, TX 76114",
    }


def test_source():
    assert (
        parsed_items[0]["source"]
        == "https://meetings.boardbook.org/Public/Organization/1090"
    )


def test_links():
    assert parsed_items[0]["links"] == [
        {
            "title": "Map Link",
            "href": "https://maps.google.com/?q=5228+Ohio+Garden%2c+Fort+Worth%2c+TX+76114",  # noqa
        },
        {
            "title": "Agenda",
            "href": "https://meetings.boardbook.org/Public/Agenda/1090?meeting=726957",  # noqa
        },
        {
            "title": "Projector",
            "href": "https://meetings.boardbook.org/Public/Projector/1090?meeting=726957",  # noqa
        },
    ]


def test_classification():
    assert parsed_items[0]["classification"] == BOARD


@pytest.mark.parametrize("item", parsed_items)
def test_all_day(item):
    assert item["all_day"] is False
```

**Note:** `# noqa` comments suppress flake8 line-length warnings for URLs.

---

## Phase 7: Verification

### Step 7.1: Run Tests

```bash
pipenv run pytest tests/test_fortx_Castleberry_ISD.py -v
```

**Expected:** All tests pass ✅

### Step 7.2: Run Linting

```bash
pipenv run flake8 city_scrapers/spiders/fortx_Castleberry_ISD.py tests/test_fortx_Castleberry_ISD.py
```

**Expected:** No output (no errors) ✅

### Step 7.3: Test Against Live Site

```bash
pipenv run scrapy crawl fortx_Castleberry_ISD -O output.json
```

Then verify:

```bash
head -50 output.json
rm output.json
```

---

## Phase 8: Commit and Push

### Step 8.1: Stage Files

```bash
git add city_scrapers/spiders/fortx_Castleberry_ISD.py \
        tests/test_fortx_Castleberry_ISD.py \
        tests/files/fortx_Castleberry_ISD.html
```

### Step 8.2: Commit

```bash
git commit -m "Add fortx_Castleberry_ISD spider for Castleberry ISD Board meetings"
```

### Step 8.3: Push

```bash
git push -u origin feature/spider-fortx_Castleberry_ISD
```

---

## Phase 9: Create Pull Request

1. Go to: https://github.com/City-Bureau/city-scrapers-fortx
2. Click "Compare & pull request"
3. Title: `Add spider: fortx_Castleberry_ISD`
4. Description:
   - Agency: Castleberry ISD Board
   - URL: https://meetings.boardbook.org/Public/Organization/1090
   - Closes: #[issue_number] (if applicable)

---

## Quick Reference: CSS Selectors Used

| Data               | Selector                                                           |
| ------------------ | ------------------------------------------------------------------ |
| Meeting rows       | `table tbody tr[class*='row-for-board']`                           |
| Date/Title text    | `td:first-child div::text` or `item.css("td")[0].css("div::text")` |
| Location name      | `item.css("td")[1].css("span::text").get()`                        |
| All location spans | `item.css("td")[1].css("span::text").getall()`                     |
| Map link           | `item.css("td")[1].css("a")`                                       |
| Other links        | `item.css("td")[2].css("a")`                                       |
| Link href          | `link.css("::attr(href)").get()`                                   |
| Link text          | `link.css("::text").get()`                                         |

---

## Troubleshooting

### Error: `TypeError: '<' not supported between instances of 'NoneType'`

- **Cause:** `_parse_start` returned `None`
- **Fix:** Add `if not start: continue` in parse method

### Error: `line too long (>88 characters)`

- **Fix:** Add `# noqa` comment at end of long lines

### Error: Wrong number of items parsed

- **Cause:** CSS selector too broad/narrow
- **Fix:** Use browser DevTools to verify selector matches correct elements

---

## Files Created

1. `city_scrapers/spiders/fortx_Castleberry_ISD.py` - The spider
2. `tests/test_fortx_Castleberry_ISD.py` - Test file
3. `tests/files/fortx_Castleberry_ISD.html` - HTML fixture

---

**Congratulations!** You've built a complete Scrapy spider following city-scrapers conventions.

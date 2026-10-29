from city_scrapers_core.constants import CITY_COUNCIL, COMMISSION

from city_scrapers.mixins.fort_worth import FortWorthMixin

# Optional per spider:
# - "exclude_ids": MainContentIds (or Ids) of calendar entries to skip.
#   An id covers every date of one event page, but most pages are
#   replaced each year, e.g. "2026 Election Voting Dates & Notices" is
#   "2f7f60e6-1873-40ed-85ad-fc214bd77582".
# - "exclude_title_patterns": case-insensitive regular expressions matched
#   against the entry name, e.g. r"election voting dates", which keep
#   matching after the yearly page is replaced.
spider_configs = [
    {
        "class_name": "FortxFortWorthCityCouncilSpider",
        "name": "fortx_Fort_Worth_City_Council",
        "agency": "Fort Worth City Council",
        "calendar_id": "8a8add9a-3fd0-4b39-9a3e-d58e98e27acc",
        "calendar_url": "https://www.fortworthtexas.gov/calendar/city-council",
        "classification": CITY_COUNCIL,
    },
    {
        "class_name": "FortxFortWorthBoardsSpider",
        "name": "fortx_Fort_Worth_Boards",
        "agency": "Fort Worth Boards and Commissions",
        "calendar_id": "788ffb59-05d1-457d-b9dd-423d4b95a06e",
        "calendar_url": "https://www.fortworthtexas.gov/calendar/boards-commission",
        "classification": COMMISSION,
    },
    {
        "class_name": "FortxFortWorthPublicMeetingsSpider",
        "name": "fortx_Fort_Worth_Public_Meetings",
        "agency": "Fort Worth Public Meetings",
        "calendar_id": "8efac0b6-9ea3-402e-b7d9-e9e71a2a34a0",
        "calendar_url": "https://www.fortworthtexas.gov/calendar/public-meetings",
        "classification": CITY_COUNCIL,
    },
]


def create_spiders():
    """
    Dynamically create spider classes using the spider_configs list
    and register them in the global namespace.
    """
    for config in spider_configs:
        class_name = config["class_name"]

        if class_name not in globals():
            # Build attributes dict without class_name to avoid duplication.
            # We make sure that the class_name is not already in the global
            # namespace, because some scrapy CLI commands like `scrapy list`
            # will inadvertently declare the spider class more than once
            # otherwise
            attrs = {k: v for k, v in config.items() if k != "class_name"}

            # Dynamically create the spider class
            spider_class = type(
                class_name,
                (FortWorthMixin,),
                {**attrs, "__module__": __name__},
            )

            globals()[class_name] = spider_class


# Create all spider classes at module load
create_spiders()

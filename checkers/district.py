"""
District (by Swiggy) Booking Checker
Checks if ticket bookings are open on District's platform (district.in).
"""

import json
import logging
import re
import requests
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from .date_utils import parse_target_date

logger = logging.getLogger(__name__)

DISTRICT_BASE = "https://www.district.in"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
}

# District city mappings
DISTRICT_CITIES = {
    "mumbai": "mumbai",
    "delhi": "delhi-ncr",
    "delhi-ncr": "delhi-ncr",
    "ncr": "delhi-ncr",
    "bangalore": "bengaluru",
    "bengaluru": "bengaluru",
    "chennai": "chennai",
    "hyderabad": "hyderabad",
    "kolkata": "kolkata",
    "pune": "pune",
    "ahmedabad": "ahmedabad",
    "kochi": "kochi",
    "lucknow": "lucknow",
    "chandigarh": "chandigarh",
    "jaipur": "jaipur",
    "indore": "indore",
    "coimbatore": "coimbatore",
    "goa": "goa",
    "nagpur": "nagpur",
    "bhopal": "bhopal",
    "vizag": "visakhapatnam",
    "visakhapatnam": "visakhapatnam",
    "mysore": "mysuru",
    "mysuru": "mysuru",
    "thiruvananthapuram": "thiruvananthapuram",
    "trivandrum": "thiruvananthapuram",
    "pondicherry": "puducherry",
    "puducherry": "puducherry",
    "guntur": "guntur",
    "madurai": "madurai",
    "trichy": "trichy",
    "salem": "salem",
}

GENERIC_THEATER_WORDS = {
    "pvr", "inox", "cinepolis", "mall", "cinema", "cinemas",
    "theatre", "theatres", "complex", "multiplex", "screen", "screens"
}


def _fuzzy_match(query: str, target: str, threshold: float = 0.5) -> bool:
    """Check if query fuzzy-matches target."""
    query_lower = query.lower().strip()
    target_lower = target.lower().strip()

    if query_lower in target_lower or target_lower in query_lower:
        return True

    ratio = SequenceMatcher(None, query_lower, target_lower).ratio()
    return ratio >= threshold


def _get_district_city(city: str) -> str:
    """Resolve city name to District city slug."""
    city_lower = city.lower().strip()
    if city_lower in DISTRICT_CITIES:
        return DISTRICT_CITIES[city_lower]

    for name, slug in DISTRICT_CITIES.items():
        if _fuzzy_match(city_lower, name, threshold=0.7):
            return slug

    return city_lower.replace(" ", "-")


def _search_movie(movie_name: str) -> dict | None:
    """Find movie slug and ID from District's live movies page."""
    try:
        url = f"{DISTRICT_BASE}/movies"
        resp = requests.get(url, headers=HEADERS, timeout=12)
        if resp.status_code == 200:
            matches = re.findall(
                r'/movies/([a-zA-Z0-9-]+)-movie-tickets(?:-in-[a-zA-Z0-9-]+)?-(MV\d+)',
                resp.text
            )
            catalog = {}
            for slug, m_id in matches:
                clean_title = slug.replace("-", " ")
                if m_id not in catalog:
                    catalog[m_id] = {"title": clean_title, "slug": slug, "id": m_id}

            # Find matching movie
            for m_id, info in catalog.items():
                if _fuzzy_match(movie_name, info["title"], threshold=0.55):
                    return info
        else:
            logger.info(f"[District] Catalog fetch returned HTTP {resp.status_code}")
    except Exception as e:
        logger.info(f"[District] Catalog fetch error: {e}")

    return None


def check(config: dict) -> dict:
    """
    Check District (by Swiggy) for ticket availability.
    """
    movie_name = config.get("movie", "")
    theater_name = config.get("theater", "")
    city = config.get("city", "")
    check_days = config.get("check_next_days", 7)

    result = {
        "available": False,
        "platform": "District",
        "movie": movie_name,
        "theater": theater_name,
        "showtimes": [],
        "booking_url": "",
        "dates": [],
        "reason": "",
    }

    if not movie_name or not theater_name or not city:
        result["reason"] = "Missing movie, theater, or city in config"
        return result

    city_slug = _get_district_city(city)
    logger.info(f"[District] Checking for '{movie_name}' at '{theater_name}' in {city}...")

    # Step 1: Find movie on District
    mid = config.get("district_id")
    slug = config.get("slug") or movie_name.lower().replace(" ", "-")
    film_title = movie_name

    if not mid:
        movie_info = _search_movie(movie_name)
        if movie_info:
            slug = movie_info["slug"]
            mid = movie_info["id"]
            film_title = movie_info["title"].title()

    if not mid:
        result["reason"] = f"Movie '{movie_name}' not found on District"
        logger.info(f"[District] {result['reason']}")
        return result

    logger.info(f"[District] Found movie on District: {film_title} ({mid})")

    # Step 2: Determine dates to check
    target_date_obj = parse_target_date(config.get("target_date", ""))
    target_date_str = target_date_obj.strftime("%Y-%m-%d") if target_date_obj else None

    if target_date_obj:
        logger.info(f"[District] 🎯 Filtering strictly for TARGET DATE: {target_date_str}")
        dates_to_check = [target_date_obj]
    else:
        dates_to_check = [datetime.now().date() + timedelta(days=d) for d in range(check_days)]

    # Distinctive keywords for the theater (e.g. "Providence")
    distinctive_parts = [
        p.lower() for p in re.split(r'[\s:,\.-]+', theater_name)
        if len(p) > 2 and p.lower() not in GENERIC_THEATER_WORDS
    ]

    found_dates = []
    all_showtimes = []
    final_booking_url = f"{DISTRICT_BASE}/movies/{slug}-movie-tickets-in-{city_slug}-{mid}"

    for check_d in dates_to_check:
        d_str = check_d.strftime("%Y-%m-%d")
        urls_to_try = [
            f"{DISTRICT_BASE}/movies/{slug}-movie-tickets-in-{city_slug}-{mid}?fromdate={d_str}",
            f"{DISTRICT_BASE}/movies/{slug}-movie-tickets-{mid}?fromdate={d_str}",
        ]

        screenings = []
        page_url = urls_to_try[0]

        for u in urls_to_try:
            try:
                resp = requests.get(u, headers=HEADERS, timeout=12)
                if resp.status_code == 200:
                    scripts = re.findall(
                        r'<script type="application/ld\+json"[^>]*>(.*?)</script>',
                        resp.text,
                        re.DOTALL
                    )
                    for s in scripts:
                        try:
                            data = json.loads(s.strip())
                            if isinstance(data, dict) and data.get("@type") == "ScreeningEvent":
                                screenings.append(data)
                        except Exception:
                            pass
                    if screenings:
                        page_url = u
                        break
            except Exception as e:
                logger.debug(f"[District] Error fetching {u}: {e}")

        # Check screenings for matching theater
        day_showtimes = []
        for sc in screenings:
            venue_name = sc.get("location", {}).get("name", "")
            venue_lower = venue_name.lower()

            is_match = False
            if distinctive_parts:
                if any(p in venue_lower for p in distinctive_parts):
                    is_match = True
            elif _fuzzy_match(theater_name, venue_name, threshold=0.55):
                is_match = True

            if is_match:
                start_iso = sc.get("startDate", "")
                time_str = ""
                if start_iso:
                    try:
                        dt = datetime.fromisoformat(start_iso)
                        time_str = dt.strftime("%I:%M %p")
                    except Exception:
                        time_str = start_iso
                if time_str and time_str not in day_showtimes:
                    day_showtimes.append(time_str)

        if day_showtimes:
            found_dates.append(d_str)
            final_booking_url = page_url
            for t in day_showtimes:
                all_showtimes.append(f"{check_d.strftime('%d %b')} - {t}")

    if found_dates:
        result["available"] = True
        result["movie"] = film_title
        result["showtimes"] = all_showtimes
        result["booking_url"] = final_booking_url
        result["dates"] = found_dates
        logger.info(f"[District] ✅ BOOKING OPEN! Shows found on {found_dates}: {', '.join(all_showtimes[:6])}")
    else:
        if target_date_str:
            result["reason"] = f"Bookings NOT open yet for '{theater_name}' on target date {target_date_str}"
        else:
            result["reason"] = f"No showtimes found for '{theater_name}' on District in next {check_days} days"
        logger.info(f"[District] {result['reason']}")

    return result

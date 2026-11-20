"""
BookMyShow (BMS) Booking Checker
Checks if ticket bookings are open for a specific movie at a specific theater.
Uses BMS internal API endpoints that their web frontend calls.
"""

import requests
import logging
from datetime import datetime, timedelta
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

BMS_BASE = "https://in.bookmyshow.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://in.bookmyshow.com/",
    "Origin": "https://in.bookmyshow.com",
}

# Major Indian cities with BMS region codes
CITY_CODES = {
    "mumbai": "MUMBAI",
    "delhi": "NCR",
    "delhi-ncr": "NCR",
    "ncr": "NCR",
    "bangalore": "BANG",
    "bengaluru": "BANG",
    "chennai": "CHEN",
    "hyderabad": "HYD",
    "kolkata": "KOLK",
    "pune": "PUNE",
    "ahmedabad": "AHMD",
    "kochi": "KOCH",
    "cochin": "KOCH",
    "jaipur": "JAIP",
    "chandigarh": "CHAND",
    "lucknow": "LUCK",
    "indore": "INDO",
    "coimbatore": "COIM",
    "thiruvananthapuram": "TRIV",
    "trivandrum": "TRIV",
    "vizag": "VIZAG",
    "visakhapatnam": "VIZAG",
    "nagpur": "NAGP",
    "bhopal": "BHOP",
    "goa": "GOA",
    "patna": "PATN",
    "vadodara": "VADO",
    "surat": "SURA",
    "guwahati": "GUWA",
    "mysore": "MYSO",
    "mysuru": "MYSO",
    "madurai": "MADU",
    "trichy": "TRIC",
    "tiruchirappalli": "TRIC",
}


def _fuzzy_match(query: str, target: str, threshold: float = 0.5) -> bool:
    """Check if query fuzzy-matches target."""
    query_lower = query.lower().strip()
    target_lower = target.lower().strip()

    # Exact substring match
    if query_lower in target_lower or target_lower in query_lower:
        return True

    # Fuzzy ratio match
    ratio = SequenceMatcher(None, query_lower, target_lower).ratio()
    return ratio >= threshold


def _get_city_code(city: str) -> str:
    """Resolve city name to BMS region code."""
    city_lower = city.lower().strip()

    # Direct lookup
    if city_lower in CITY_CODES:
        return CITY_CODES[city_lower]

    # Fuzzy match
    for name, code in CITY_CODES.items():
        if _fuzzy_match(city_lower, name, threshold=0.7):
            return code

    # Return as-is (user may have provided the code directly)
    return city.upper()


def _search_movie(city_code: str, movie_name: str) -> dict | None:
    """Search for a movie on BMS and return its details."""
    try:
        # Try the quicksearch API
        url = f"{BMS_BASE}/api/explore/v1/explore/quicksearch"
        params = {
            "q": movie_name,
            "city": city_code,
            "lang": "en",
            "type": "MT",
        }
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        # Search through results for a movie match
        results = data.get("docs", data.get("data", data.get("results", [])))
        if isinstance(results, list):
            for item in results:
                name = item.get("EventTitle", item.get("name", item.get("title", "")))
                if _fuzzy_match(movie_name, name, threshold=0.6):
                    return {
                        "code": item.get("EventCode", item.get("code", item.get("eventCode", ""))),
                        "name": name,
                        "slug": item.get("EventURLTitle", item.get("slug", "")),
                        "group": item.get("EventGroup", item.get("groupCode", "")),
                    }

    except Exception as e:
        logger.warning(f"BMS quicksearch failed: {e}")

    try:
        # Fallback: Try the movies listing API
        url = f"{BMS_BASE}/api/explore/v1/explore/getMoviesInCity"
        params = {
            "city": city_code,
            "lang": "en",
            "type": "MT",
        }
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        movies = data.get("moviesData", data.get("data", data.get("results", [])))
        if isinstance(movies, list):
            for movie in movies:
                name = movie.get("EventTitle", movie.get("name", movie.get("title", "")))
                if _fuzzy_match(movie_name, name, threshold=0.6):
                    return {
                        "code": movie.get("EventCode", movie.get("code", "")),
                        "name": name,
                        "slug": movie.get("EventURLTitle", movie.get("slug", "")),
                        "group": movie.get("EventGroup", movie.get("groupCode", "")),
                    }

    except Exception as e:
        logger.warning(f"BMS movies listing failed: {e}")

    return None


def _get_showtimes(city_code: str, event_code: str, date_str: str) -> list:
    """Get showtimes for a movie on a specific date. Returns list of venue dicts."""
    try:
        url = f"{BMS_BASE}/api/explore/v1/explore/getShowtimes"
        params = {
            "appCode": "MOBAND2",
            "appVersion": "14304",
            "city": city_code,
            "eventCode": event_code,
            "contentType": "MT",
            "date": date_str,
            "lang": "en",
        }
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        # BMS returns venue data in various formats
        venues = (
            data.get("ShowDetails", []) or
            data.get("venues", []) or
            data.get("cinemas", []) or
            data.get("data", {}).get("ShowDetails", []) or
            []
        )
        return venues if isinstance(venues, list) else []

    except Exception as e:
        logger.warning(f"BMS showtimes API failed for date {date_str}: {e}")
        return []


def _find_theater_in_venues(venues: list, theater_name: str) -> list:
    """Find matching theater in venue list."""
    matches = []
    for venue in venues:
        venue_name = venue.get("VenueName", venue.get("name", venue.get("cinemaName", "")))
        if _fuzzy_match(theater_name, venue_name, threshold=0.5):
            shows = venue.get("ShowTimes", venue.get("shows", venue.get("showtimes", [])))
            show_times = []
            if isinstance(shows, list):
                for show in shows:
                    time_str = show.get("ShowTime", show.get("time", show.get("showTime", "")))
                    if time_str:
                        show_times.append(time_str)
            matches.append({
                "venue_name": venue_name,
                "venue_code": venue.get("VenueCode", venue.get("code", "")),
                "showtimes": show_times,
            })
    return matches


def check(config: dict) -> dict:
    """
    Check BookMyShow for ticket availability.

    Args:
        config: Dict with keys: city, city_code, movie, theater, check_next_days

    Returns:
        Dict with keys: available (bool), platform, movie, theater,
                       showtimes, booking_url, dates, reason
    """
    movie_name = config.get("movie", "")
    theater_name = config.get("theater", "")
    city = config.get("city", "")
    city_code = config.get("city_code", "") or _get_city_code(city)
    check_days = config.get("check_next_days", 7)

    result = {
        "available": False,
        "platform": "BookMyShow",
        "movie": movie_name,
        "theater": theater_name,
        "showtimes": [],
        "booking_url": "",
        "dates": [],
        "reason": "",
    }

    if not movie_name or not theater_name or not city_code:
        result["reason"] = "Missing movie, theater, or city in config"
        return result

    logger.info(f"[BMS] Searching for '{movie_name}' in {city} ({city_code})...")

    # Step 1: Find the movie
    movie_info = _search_movie(city_code, movie_name)
    if not movie_info:
        result["reason"] = f"Movie '{movie_name}' not found on BMS for city {city_code}"
        logger.info(f"[BMS] {result['reason']}")
        return result

    event_code = movie_info["code"]
    logger.info(f"[BMS] Found movie: {movie_info['name']} (code: {event_code})")

    # Step 2: Check showtimes for the next N days
    found_dates = []
    all_showtimes = []

    for day_offset in range(check_days):
        check_date = datetime.now() + timedelta(days=day_offset)
        date_str = check_date.strftime("%Y%m%d")

        venues = _get_showtimes(city_code, event_code, date_str)
        if not venues:
            continue

        theater_matches = _find_theater_in_venues(venues, theater_name)
        if theater_matches:
            found_dates.append(check_date.strftime("%Y-%m-%d"))
            for match in theater_matches:
                for st in match["showtimes"]:
                    all_showtimes.append(f"{check_date.strftime('%d %b')} - {st}")

    if found_dates:
        slug = movie_info.get("slug", movie_name.lower().replace(" ", "-"))
        booking_url = f"{BMS_BASE}/buytickets/{slug}-{city.lower()}/movie-{city_code.lower()}-MT/{event_code}"

        result["available"] = True
        result["movie"] = movie_info["name"]
        result["showtimes"] = all_showtimes
        result["booking_url"] = booking_url
        result["dates"] = found_dates
        logger.info(f"[BMS] ✅ BOOKING OPEN! {len(all_showtimes)} shows found on {found_dates}")
    else:
        result["reason"] = f"No showtimes found for '{theater_name}' in next {check_days} days"
        logger.info(f"[BMS] {result['reason']}")

    return result

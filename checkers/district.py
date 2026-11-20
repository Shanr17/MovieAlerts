"""
District (by Swiggy) Booking Checker
Checks if ticket bookings are open on District's platform.
"""

import requests
import logging
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from .date_utils import parse_target_date

logger = logging.getLogger(__name__)

DISTRICT_BASE = "https://www.district.in"
DISTRICT_API = "https://www.district.in/api"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.district.in/",
    "Origin": "https://www.district.in",
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

    return city_lower


def _search_movies(city_slug: str, movie_name: str) -> dict | None:
    """Search for a movie on District."""
    urls_to_try = [
        f"{DISTRICT_API}/v1/movies/search",
        f"{DISTRICT_API}/v1/search",
        f"{DISTRICT_API}/movies/now-showing",
    ]

    for url in urls_to_try:
        try:
            params = {"q": movie_name, "city": city_slug}
            resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                results = (
                    data.get("movies", []) or
                    data.get("data", []) or
                    data.get("results", []) or
                    (data if isinstance(data, list) else [])
                )
                for item in results:
                    name = item.get("name", item.get("title", item.get("movieName", "")))
                    if _fuzzy_match(movie_name, name, threshold=0.6):
                        return {
                            "id": item.get("id", item.get("movieId", item.get("code", ""))),
                            "name": name,
                            "slug": item.get("slug", item.get("urlSlug", "")),
                        }
        except Exception as e:
            logger.debug(f"District search failed ({url}): {e}")
            continue

    # Fallback: try loading movie listing page
    try:
        url = f"{DISTRICT_API}/v1/movies"
        params = {"city": city_slug, "filter": "now-showing"}
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            movies = (
                data.get("movies", []) or
                data.get("data", []) or
                (data if isinstance(data, list) else [])
            )
            for item in movies:
                name = item.get("name", item.get("title", item.get("movieName", "")))
                if _fuzzy_match(movie_name, name, threshold=0.6):
                    return {
                        "id": item.get("id", item.get("movieId", "")),
                        "name": name,
                        "slug": item.get("slug", ""),
                    }
    except Exception as e:
        logger.debug(f"District movies listing failed: {e}")

    return None


def _get_showtimes(city_slug: str, movie_id: str, date_str: str) -> list:
    """Get showtimes for a movie at District cinemas."""
    urls_to_try = [
        f"{DISTRICT_API}/v1/showtimes",
        f"{DISTRICT_API}/v1/movies/{movie_id}/showtimes",
    ]

    for url in urls_to_try:
        try:
            params = {"city": city_slug, "movieId": movie_id, "date": date_str}
            resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                cinemas = (
                    data.get("cinemas", []) or
                    data.get("venues", []) or
                    data.get("theatres", []) or
                    data.get("data", {}).get("cinemas", []) or
                    (data if isinstance(data, list) else [])
                )
                if cinemas:
                    return cinemas
        except Exception as e:
            logger.debug(f"District showtimes failed ({url}): {e}")
            continue

    return []


def _find_theater(cinemas: list, theater_name: str) -> list:
    """Find matching theater in cinema list."""
    matches = []
    for cinema in cinemas:
        name = cinema.get("name", cinema.get("cinemaName", cinema.get("theatreName", "")))
        if _fuzzy_match(theater_name, name, threshold=0.5):
            shows = cinema.get("shows", cinema.get("showtimes", cinema.get("sessions", [])))
            show_times = []
            if isinstance(shows, list):
                for show in shows:
                    time_str = show.get("showTime", show.get("time", show.get("startTime", "")))
                    if time_str:
                        show_times.append(time_str)
            matches.append({
                "cinema_name": name,
                "showtimes": show_times,
            })
    return matches


def check(config: dict) -> dict:
    """
    Check District (by Swiggy) for ticket availability.

    Args:
        config: Dict with keys: city, movie, theater, check_next_days

    Returns:
        Dict with keys: available, platform, movie, theater,
                       showtimes, booking_url, dates, reason
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

    # Step 1: Find the movie
    movie_info = _search_movies(city_slug, movie_name)
    if not movie_info:
        result["reason"] = f"Movie '{movie_name}' not found on District for {city}"
        logger.info(f"[District] {result['reason']}")
        return result

    logger.info(f"[District] Found movie: {movie_info['name']} (id: {movie_info['id']})")

    # Step 2: Check showtimes
    target_date_obj = parse_target_date(config.get("target_date", ""))
    target_date_str = target_date_obj.strftime("%Y-%m-%d") if target_date_obj else None

    if target_date_obj:
        logger.info(f"[District] 🎯 Filtering strictly for TARGET DATE: {target_date_str}")
        dates_to_check = [target_date_obj]
    else:
        dates_to_check = [datetime.now().date() + timedelta(days=d) for d in range(check_days)]

    found_dates = []
    all_showtimes = []

    for check_d in dates_to_check:
        date_str = check_d.strftime("%Y-%m-%d")

        cinemas = _get_showtimes(city_slug, movie_info["id"], date_str)
        if not cinemas:
            continue

        theater_matches = _find_theater(cinemas, theater_name)
        if theater_matches:
            found_dates.append(date_str)
            for match in theater_matches:
                for st in match["showtimes"]:
                    all_showtimes.append(f"{check_d.strftime('%d %b')} - {st}")

    if found_dates:
        slug = movie_info.get("slug", movie_name.lower().replace(" ", "-"))
        booking_url = f"{DISTRICT_BASE}/movies/{slug}?city={city_slug}"

        result["available"] = True
        result["movie"] = movie_info["name"]
        result["showtimes"] = all_showtimes
        result["booking_url"] = booking_url
        result["dates"] = found_dates
        logger.info(f"[District] ✅ BOOKING OPEN! {len(all_showtimes)} shows on {found_dates}")
    else:
        if target_date_str:
            result["reason"] = f"Bookings NOT open yet for '{theater_name}' on target date {target_date_str}"
        else:
            result["reason"] = f"No showtimes found for '{theater_name}' in next {check_days} days"
        logger.info(f"[District] {result['reason']}")

    return result

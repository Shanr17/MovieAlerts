"""
PVR Cinemas Booking Checker
Checks if ticket bookings are open on PVR's own platform.
"""

import requests
import logging
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from .date_utils import parse_target_date

logger = logging.getLogger(__name__)

PVR_BASE = "https://api.pvrcinemas.com/api/v1"
PVR_WEB = "https://www.pvrcinemas.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.pvrcinemas.com/",
    "Origin": "https://www.pvrcinemas.com",
}

# PVR city mappings (city name -> PVR city slug/id)
PVR_CITIES = {
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
    "vadodara": "vadodara",
    "surat": "surat",
    "vizag": "visakhapatnam",
    "visakhapatnam": "visakhapatnam",
    "mysore": "mysore",
    "mysuru": "mysore",
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


def _get_pvr_city(city: str) -> str:
    """Resolve city name to PVR city slug."""
    city_lower = city.lower().strip()
    if city_lower in PVR_CITIES:
        return PVR_CITIES[city_lower]

    for name, slug in PVR_CITIES.items():
        if _fuzzy_match(city_lower, name, threshold=0.7):
            return slug

    return city_lower


def _get_movies(city_slug: str) -> list:
    """Get list of currently showing movies from PVR."""
    urls_to_try = [
        f"{PVR_BASE}/movies/now-showing?city={city_slug}",
        f"{PVR_BASE}/movies?city={city_slug}&filter=now-showing",
        f"{PVR_WEB}/api/movies/now-showing?city={city_slug}",
    ]

    for url in urls_to_try:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                movies = (
                    data.get("movies", []) or
                    data.get("data", []) or
                    data.get("results", []) or
                    (data if isinstance(data, list) else [])
                )
                if movies:
                    return movies
        except Exception as e:
            logger.debug(f"PVR movies endpoint failed ({url}): {e}")
            continue

    return []


def _get_showtimes(city_slug: str, movie_id: str, date_str: str) -> list:
    """Get showtimes for a movie at PVR cinemas."""
    urls_to_try = [
        f"{PVR_BASE}/showtimes?city={city_slug}&movieId={movie_id}&date={date_str}",
        f"{PVR_BASE}/movie-schedule?city={city_slug}&movieCode={movie_id}&date={date_str}",
        f"{PVR_WEB}/api/showtimes?city={city_slug}&movieId={movie_id}&date={date_str}",
    ]

    for url in urls_to_try:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
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
            logger.debug(f"PVR showtimes endpoint failed ({url}): {e}")
            continue

    return []


def _find_movie(movies: list, movie_name: str) -> dict | None:
    """Find matching movie in PVR movie list."""
    for movie in movies:
        name = movie.get("name", movie.get("title", movie.get("movieName", "")))
        if _fuzzy_match(movie_name, name, threshold=0.6):
            return {
                "id": movie.get("id", movie.get("movieId", movie.get("code", ""))),
                "name": name,
                "slug": movie.get("slug", movie.get("urlSlug", "")),
            }
    return None


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
                    time_str = show.get("showTime", show.get("time", show.get("sessionTime", "")))
                    if time_str:
                        show_times.append(time_str)
            matches.append({
                "cinema_name": name,
                "showtimes": show_times,
            })
    return matches


def check(config: dict) -> dict:
    """
    Check PVR Cinemas for ticket availability.

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
        "platform": "PVR Cinemas",
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

    city_slug = _get_pvr_city(city)
    logger.info(f"[PVR] Checking for '{movie_name}' at '{theater_name}' in {city}...")

    # Step 1: Get movie list and find our movie
    movies = _get_movies(city_slug)
    if not movies:
        result["reason"] = "Could not fetch PVR movie listings"
        logger.info(f"[PVR] {result['reason']}")
        return result

    movie_info = _find_movie(movies, movie_name)
    if not movie_info:
        result["reason"] = f"Movie '{movie_name}' not found on PVR for {city}"
        logger.info(f"[PVR] {result['reason']}")
        return result

    logger.info(f"[PVR] Found movie: {movie_info['name']} (id: {movie_info['id']})")

    # Step 2: Check showtimes
    target_date_obj = parse_target_date(config.get("target_date", ""))
    target_date_str = target_date_obj.strftime("%Y-%m-%d") if target_date_obj else None

    if target_date_obj:
        logger.info(f"[PVR] 🎯 Filtering strictly for TARGET DATE: {target_date_str}")
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
        booking_url = f"{PVR_WEB}/movies/{slug}"

        result["available"] = True
        result["movie"] = movie_info["name"]
        result["showtimes"] = all_showtimes
        result["booking_url"] = booking_url
        result["dates"] = found_dates
        logger.info(f"[PVR] ✅ BOOKING OPEN! {len(all_showtimes)} shows on {found_dates}")
    else:
        if target_date_str:
            result["reason"] = f"Bookings NOT open yet for '{theater_name}' on target date {target_date_str}"
        else:
            result["reason"] = f"No showtimes found for '{theater_name}' in next {check_days} days"
        logger.info(f"[PVR] {result['reason']}")

    return result

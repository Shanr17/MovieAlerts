"""
PVR Cinemas Booking Checker
Uses PVR INOX official API3 gateway: https://api3.pvrcinemas.com
"""

import json
import logging
import urllib.request
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from .date_utils import parse_target_date

logger = logging.getLogger(__name__)

PVR_API = "https://api3.pvrcinemas.com/api/v1/booking/content"
PVR_WEB = "https://www.pvrcinemas.com"


def _fuzzy_match(query: str, target: str, threshold: float = 0.5) -> bool:
    """Check if query fuzzy-matches target."""
    query_lower = query.lower().strip()
    target_lower = target.lower().strip()

    if query_lower in target_lower or target_lower in query_lower:
        return True

    ratio = SequenceMatcher(None, query_lower, target_lower).ratio()
    return ratio >= threshold


def _get_pvr_city(city: str) -> str:
    """Format city name with proper capitalization for PVR API header."""
    city_lower = city.lower().strip()
    mapping = {
        "pondicherry": "Pondicherry",
        "puducherry": "Pondicherry",
        "chennai": "Chennai",
        "bangalore": "Bengaluru",
        "bengaluru": "Bengaluru",
        "hyderabad": "Hyderabad",
        "mumbai": "Mumbai",
        "delhi-ncr": "Delhi-NCR",
        "delhi": "Delhi-NCR",
        "ncr": "Delhi-NCR",
        "coimbatore": "Coimbatore",
        "kochi": "Kochi",
        "madurai": "Madurai",
        "trichy": "Trichy",
        "salem": "Salem",
        "lucknow": "Lucknow",
        "chandigarh": "Chandigarh",
        "jaipur": "Jaipur",
        "indore": "Indore",
        "ahmedabad": "Ahmedabad",
        "pune": "Pune",
        "kolkata": "Kolkata",
    }
    return mapping.get(city_lower, city.capitalize())


def _get_cinemas(city_name: str) -> list:
    """Fetch all cinemas and active movie listings for a city from PVR API3."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json",
        "Authorization": "Bearer ",
        "chain": "PVR",
        "platform": "WEBSITE",
        "country": "INDIA",
        "appVersion": "1.0",
        "city": city_name,
        "Origin": "https://www.pvrcinemas.com",
        "Referer": "https://www.pvrcinemas.com/",
    }
    url = f"{PVR_API}/cinemas"
    payload = json.dumps({"city": city_name}).encode()
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read().decode())
            out = data.get("output", {})
            if isinstance(out, dict):
                return out.get("c", [])
    except Exception as e:
        logger.debug(f"[PVR] Error querying PVR cinemas endpoint: {e}")
    return []


def check(config: dict) -> dict:
    """
    Check PVR Cinemas for ticket availability.
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

    pvr_city = _get_pvr_city(city)
    logger.info(f"[PVR] Checking for '{movie_name}' at '{theater_name}' in {pvr_city}...")

    # Step 1: Fetch cinemas in this city
    cinemas = _get_cinemas(pvr_city)
    if not cinemas:
        result["reason"] = f"No PVR cinemas found in city '{pvr_city}'"
        logger.info(f"[PVR] {result['reason']}")
        return result

    # Step 2: Find the matching cinema
    matched_cinema = None
    for c in cinemas:
        c_name = c.get("name", "")
        if _fuzzy_match(theater_name, c_name, threshold=0.5):
            matched_cinema = c
            break

    if not matched_cinema:
        result["reason"] = f"Cinema '{theater_name}' not found under PVR in {pvr_city}"
        logger.info(f"[PVR] {result['reason']}")
        return result

    cinema_id = matched_cinema.get("theatreId", "")
    cinema_name = matched_cinema.get("name", theater_name)
    logger.info(f"[PVR] Found Cinema: {cinema_name} (ID: {cinema_id})")

    # Step 3: Check movies in this cinema
    movie_list = matched_cinema.get("movieRes", [])
    matched_movie = None

    for m in movie_list:
        m_title = m.get("filmName", m.get("n", ""))
        if _fuzzy_match(movie_name, m_title, threshold=0.6):
            matched_movie = m
            break

    if not matched_movie:
        result["reason"] = f"Movie '{movie_name}' not listed yet at {cinema_name}"
        logger.info(f"[PVR] {result['reason']}")
        return result

    show_count = matched_movie.get("showCount", 0)
    film_name = matched_movie.get("filmName", movie_name)
    logger.info(f"[PVR] Found Movie: {film_name} with {show_count} shows listed")

    # Step 4: Target date check
    target_date_obj = parse_target_date(config.get("target_date", ""))
    target_date_str = target_date_obj.strftime("%Y-%m-%d") if target_date_obj else None

    if show_count > 0:
        result["available"] = True
        result["movie"] = film_name
        result["showtimes"] = [f"{show_count} shows open"]
        result["booking_url"] = f"{PVR_WEB}"
        if target_date_str:
            result["dates"] = [target_date_str]
        logger.info(f"[PVR] ✅ BOOKING OPEN at {cinema_name}! ({show_count} shows available)")
    else:
        result["reason"] = f"Bookings not open yet for '{movie_name}' at {cinema_name}"
        logger.info(f"[PVR] {result['reason']}")

    return result

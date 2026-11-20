"""
PVR Cinemas Booking Checker
Uses PVR INOX official API3 gateway: https://api3.pvrcinemas.com
"""

import logging
import requests
from datetime import datetime
from difflib import SequenceMatcher
from .date_utils import parse_target_date

logger = logging.getLogger(__name__)

PVR_API = "https://api3.pvrcinemas.com/api/v1/booking/content"
PVR_WEB = "https://www.pvrcinemas.com"

# Known fallback IDs for common PVR cinemas if datacenter IP blocks initial discovery
KNOWN_PVR_CINEMAS = {
    "pondicherry": [
        {"theatreId": "539", "name": "PVR Providence Mall Pondicherry", "city": "Pondicherry"}
    ],
    "chennai": [
        {"theatreId": "12", "name": "PVR SPI Palazzo Nexus Vijaya Mall", "city": "Chennai"},
        {"theatreId": "11", "name": "PVR SPI Escape Express Avenue", "city": "Chennai"},
        {"theatreId": "10", "name": "PVR SPI Sathyam Royapettah", "city": "Chennai"},
        {"theatreId": "23", "name": "PVR VR Chennai Anna Nagar", "city": "Chennai"}
    ],
    "bangalore": [
        {"theatreId": "1", "name": "PVR Forum Mall Koramangala", "city": "Bengaluru"},
        {"theatreId": "2", "name": "PVR Vega City Bannerghatta", "city": "Bengaluru"},
        {"theatreId": "3", "name": "PVR Orion Mall Rajajinagar", "city": "Bengaluru"}
    ],
    "hyderabad": [
        {"theatreId": "5", "name": "PVR Next Galleria Panjagutta", "city": "Hyderabad"},
        {"theatreId": "6", "name": "PVR Inorbit Mall Madhapur", "city": "Hyderabad"}
    ]
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


def _get_headers(city_name: str) -> dict:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
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


def _get_cinemas(city_name: str) -> list:
    """Fetch all cinemas for a city from PVR API3 with fallback."""
    headers = _get_headers(city_name)
    url = f"{PVR_API}/cinemas"
    payload = {"city": city_name, "lat": "0.000", "lng": "0.000", "text": ""}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=12)
        if resp.status_code == 200:
            data = resp.json()
            out = data.get("output", {})
            if isinstance(out, dict):
                cinemas = out.get("c", [])
                if cinemas:
                    return cinemas
        else:
            logger.debug(f"[PVR] /cinemas endpoint returned status {resp.status_code}")
    except Exception as e:
        logger.debug(f"[PVR] Error querying /cinemas: {e}")

    # Fallback to known local cinema mappings
    city_key = city_name.lower()
    return KNOWN_PVR_CINEMAS.get(city_key, [])


def check(config: dict) -> dict:
    """
    Check PVR Cinemas for ticket availability and specific target dates.
    """
    movie_name = config.get("movie", "")
    theater_name = config.get("theater", "")
    city = config.get("city", "")

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

    # Step 1: Find matching cinema
    cinemas = _get_cinemas(pvr_city)
    if not cinemas:
        result["reason"] = f"No PVR cinemas found in city '{pvr_city}'"
        logger.info(f"[PVR] {result['reason']}")
        return result

    matched_cinema = None
    for c in cinemas:
        c_name = c.get("name", "")
        if _fuzzy_match(theater_name, c_name, threshold=0.45):
            matched_cinema = c
            break

    if not matched_cinema:
        result["reason"] = f"Cinema '{theater_name}' not found under PVR in {pvr_city}"
        logger.info(f"[PVR] {result['reason']}")
        return result

    cinema_id = str(matched_cinema.get("theatreId", ""))
    cinema_name = matched_cinema.get("name", theater_name)
    logger.info(f"[PVR] Found Cinema: {cinema_name} (ID: {cinema_id})")

    # Step 2: Query session endpoint (/csessions)
    target_date_obj = parse_target_date(config.get("target_date", ""))
    target_date_str = target_date_obj.strftime("%Y-%m-%d") if target_date_obj else None
    query_date = target_date_str if target_date_str else datetime.now().strftime("%Y-%m-%d")

    headers = _get_headers(pvr_city)
    session_url = f"{PVR_API}/csessions"
    session_payload = {
        "city": pvr_city,
        "cid": cinema_id,
        "date": query_date
    }

    try:
        sess_resp = requests.post(session_url, json=session_payload, headers=headers, timeout=12)
        if sess_resp.status_code != 200:
            if sess_resp.status_code == 403:
                result["reason"] = "PVR direct API geo-blocked on foreign runner (covered by BookMyShow & District)"
                logger.info("[PVR] ℹ️ PVR direct gateway is geo-blocked on foreign runner. Covered automatically via BookMyShow & District.")
            else:
                result["reason"] = f"PVR session API returned HTTP {sess_resp.status_code}"
                logger.info(f"[PVR] {result['reason']}")
            return result

        sess_data = sess_resp.json()
        out = sess_data.get("output", {})
        if not out or not isinstance(out, dict):
            result["reason"] = f"No show data returned for {cinema_name}"
            logger.info(f"[PVR] {result['reason']}")
            return result

        days = out.get("days", [])
        open_dates = [d.get("dt") for d in days if d.get("enable") and d.get("dt")]

        # Step 3: Date Filtering
        if target_date_str:
            if target_date_str not in open_dates:
                result["reason"] = f"Bookings NOT open yet for target date {target_date_str} at {cinema_name}"
                logger.info(f"[PVR] 🎯 Filtering strictly for TARGET DATE: {target_date_str}")
                logger.info(f"[PVR] ❌ Bookings NOT open yet for '{cinema_name}' on target date {target_date_str}")
                return result
            logger.info(f"[PVR] 🎯 Target date {target_date_str} is ACTIVE in booking calendar!")

        # Step 4: Find movie in cinemaMovieSessions
        cms_list = out.get("cinemaMovieSessions", [])
        matched_movie = None

        for cms in cms_list:
            movie_re = cms.get("movieRe", {})
            m_title = movie_re.get("filmName", cms.get("filmName", ""))
            if _fuzzy_match(movie_name, m_title, threshold=0.6):
                matched_movie = cms
                break

        if not matched_movie:
            result["reason"] = f"Movie '{movie_name}' not listed in schedule at {cinema_name}"
            logger.info(f"[PVR] ❌ {result['reason']}")
            return result

        # Step 5: Extract showtimes
        film_name = matched_movie.get("movieRe", {}).get("filmName", movie_name)
        showtimes = []
        for exp in matched_movie.get("experienceSessions", []):
            for sh in exp.get("shows", []):
                st = sh.get("showTime")
                if st:
                    showtimes.append(st)

        if showtimes:
            result["available"] = True
            result["movie"] = film_name
            result["showtimes"] = showtimes
            result["booking_url"] = f"{PVR_WEB}/cinemasessions/{city.lower()}/{cinema_name.replace(' ', '-')}/{cinema_id}"
            if target_date_str:
                result["dates"] = [target_date_str]
            logger.info(f"\n🎉 [PVR] BOOKING OPEN for '{film_name}' at {cinema_name}!")
            logger.info(f"   Showtimes: {', '.join(showtimes[:5])}")
        else:
            result["reason"] = f"Movie '{film_name}' listed but no showtimes available"
            logger.info(f"[PVR] ❌ {result['reason']}")

    except Exception as e:
        result["reason"] = f"PVR check error: {str(e)}"
        logger.warning(f"[PVR] ❌ Error checking PVR shows: {e}")

    return result

"""
BookMyShow (BMS) Booking Checker
Uses direct browser-grade web requests to avoid Cloudflare/Akamai bot detection.
"""

import json
import logging
import re
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from .date_utils import parse_target_date

logger = logging.getLogger(__name__)

BMS_BASE = "https://in.bookmyshow.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

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
    "pondicherry": "POND",
    "puducherry": "POND",
    "salem": "SALM",
    "vellore": "VELL",
    "tirunelveli": "TIRU",
}


def _fuzzy_match(query: str, target: str, threshold: float = 0.5) -> bool:
    """Check if query fuzzy-matches target."""
    query_lower = query.lower().strip()
    target_lower = target.lower().strip()

    if query_lower in target_lower or target_lower in query_lower:
        return True

    ratio = SequenceMatcher(None, query_lower, target_lower).ratio()
    return ratio >= threshold


def _get_city_code(city: str) -> str:
    """Resolve city name to BMS region code."""
    city_lower = city.lower().strip()
    if city_lower in CITY_CODES:
        return CITY_CODES[city_lower]
    for name, code in CITY_CODES.items():
        if _fuzzy_match(city_lower, name, threshold=0.7):
            return code
    return city.upper()


def _get_movies_from_url(url: str) -> list:
    """Fetch a BMS page and extract movie entries from schema.org ItemList."""
    movies = []
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        scripts = [s for s in html.split("<script") if "ld+json" in s]
        for s in scripts:
            content = s.split(">", 1)[1].split("</script>")[0]
            try:
                data = json.loads(content)
                if data.get("@type") == "ItemList":
                    for item in data.get("itemListElement", []):
                        name = item.get("name")
                        movie_url = item.get("url", "")
                        code_match = re.search(r"(ET\d+)", movie_url)
                        code = code_match.group(1) if code_match else ""
                        parts = [p for p in movie_url.split("/") if p]
                        slug = parts[-2] if len(parts) >= 2 and parts[-1].startswith("ET") else (parts[-1] if parts else "")
                        if name and code:
                            movies.append({
                                "name": name,
                                "code": code,
                                "slug": slug,
                                "url": movie_url
                            })
            except Exception:
                continue
    except Exception as e:
        logger.debug(f"[BMS] Error fetching {url}: {e}")
    return movies


def _search_movie(city: str, city_code: str, movie_name: str) -> dict | None:
    """Search for a movie on BMS in now-showing and upcoming listings."""
    city_slug = city.lower().replace(" ", "-")

    # Check 1: Now showing page
    now_url = f"{BMS_BASE}/explore/movies-{city_slug}"
    movies = _get_movies_from_url(now_url)
    for m in movies:
        if _fuzzy_match(movie_name, m["name"], threshold=0.55):
            return m

    # Check 2: Upcoming movies page
    up_url = f"{BMS_BASE}/explore/upcoming-movies-{city_slug}"
    up_movies = _get_movies_from_url(up_url)
    for m in up_movies:
        if _fuzzy_match(movie_name, m["name"], threshold=0.55):
            return m

    return None


def _check_showtimes_page(city: str, city_code: str, movie_info: dict, date_str: str, theater_name: str) -> dict:
    """Check BMS buytickets page for a movie on a specific date."""
    slug = movie_info.get("slug", movie_info["name"].lower().replace(" ", "-"))
    event_code = movie_info["code"]
    city_slug = city.lower().replace(" ", "-")

    # BookMyShow uses modern URL structure: /movies/{city}/{slug}/buytickets/{event_code}/{date}
    urls_to_try = [
        f"{BMS_BASE}/movies/{city_slug}/{slug}/buytickets/{event_code}/{date_str}",
        f"{BMS_BASE}/buytickets/{slug}-{city_slug}/movie-{city_code.lower()}-MT/{event_code}/{date_str}",
    ]

    for url in urls_to_try:
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=12) as resp:
                final_url = resp.geturl()
                # If redirected to BMS homepage, the URL is not a valid buytickets page
                if final_url.rstrip("/") == BMS_BASE.rstrip("/"):
                    continue

                html = resp.read().decode("utf-8", errors="ignore")

            # Check if theater matches in page
            th_parts = [p.lower() for p in re.split(r'[\s:,\.-]+', theater_name) if len(p) > 3]
            html_lower = html.lower()

            found_venue = False
            if _fuzzy_match(theater_name, html, threshold=0.6):
                found_venue = True
            elif any(p in html_lower for p in th_parts):
                found_venue = True

            if found_venue:
                times = []
                for p in th_parts:
                    pos = html_lower.find(p)
                    if pos != -1:
                        # Extract showtimes from the venue's section (approx 3500 chars)
                        sec = html[pos:pos + 3500]
                        sec_times = re.findall(r'\b(?:0?[1-9]|1[0-2]):[0-5][0-9]\s*(?:AM|PM)\b', sec, re.IGNORECASE)
                        if sec_times:
                            times = list(dict.fromkeys(sec_times))
                            break

                if not times:
                    all_times = re.findall(r'\b(?:0?[1-9]|1[0-2]):[0-5][0-9]\s*(?:AM|PM)\b', html, re.IGNORECASE)
                    times = list(dict.fromkeys(all_times))

                return {
                    "available": True,
                    "booking_url": url,
                    "showtimes": times
                }

        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            logger.debug(f"[BMS] Showtimes check HTTP {e.code} for {url}")
        except Exception as e:
            logger.debug(f"[BMS] Showtimes check error for {url}: {e}")

    return {"available": False, "booking_url": urls_to_try[0], "showtimes": []}


def check(config: dict) -> dict:
    """
    Check BookMyShow for ticket availability.
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

    if not movie_name or not theater_name or not city:
        result["reason"] = "Missing movie, theater, or city in config"
        return result

    logger.info(f"[BMS] Searching for '{movie_name}' in {city} ({city_code})...")

    # Step 1: Find the movie
    movie_info = _search_movie(city, city_code, movie_name)
    if not movie_info:
        result["reason"] = f"Movie '{movie_name}' not listed yet on BMS for {city}"
        logger.info(f"[BMS] {result['reason']}")
        return result

    logger.info(f"[BMS] Found movie on BMS: {movie_info['name']} ({movie_info['code']})")

    # Step 2: Determine which dates to check
    target_date_obj = parse_target_date(config.get("target_date", ""))
    target_date_str = target_date_obj.strftime("%Y-%m-%d") if target_date_obj else None

    if target_date_obj:
        logger.info(f"[BMS] 🎯 Filtering strictly for TARGET DATE: {target_date_str}")
        dates_to_check = [target_date_obj]
    else:
        dates_to_check = [datetime.now().date() + timedelta(days=d) for d in range(check_days)]

    found_dates = []
    all_showtimes = []
    final_booking_url = movie_info.get("url", "")

    for check_d in dates_to_check:
        date_str = check_d.strftime("%Y%m%d")
        show_info = _check_showtimes_page(city, city_code, movie_info, date_str, theater_name)
        if show_info["available"]:
            found_dates.append(check_d.strftime("%Y-%m-%d"))
            final_booking_url = show_info["booking_url"]
            for st in show_info["showtimes"]:
                all_showtimes.append(f"{check_d.strftime('%d %b')} - {st}")

    if found_dates:
        result["available"] = True
        result["movie"] = movie_info["name"]
        result["showtimes"] = all_showtimes
        result["booking_url"] = final_booking_url
        result["dates"] = found_dates
        logger.info(f"[BMS] ✅ BOOKING OPEN! Shows found on {found_dates}")
    else:
        if target_date_str:
            result["reason"] = f"Bookings NOT open yet for '{theater_name}' on target date {target_date_str}"
        else:
            result["reason"] = f"No showtimes found for '{theater_name}' in next {check_days} days"
        logger.info(f"[BMS] {result['reason']}")

    return result

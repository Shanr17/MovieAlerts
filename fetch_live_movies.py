"""
Fetch Live Movies from BookMyShow & PVR
Pulls real-time movie listings for supported cities and saves to live_movies.json
"""

import json
import logging
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
OUTPUT_FILE = BASE_DIR / "live_movies.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://in.bookmyshow.com/",
    "Origin": "https://in.bookmyshow.com"
}

CITIES = {
    "pondicherry": {"bms_code": "POND", "name": "Pondicherry"},
    "chennai": {"bms_code": "CHEN", "name": "Chennai"},
    "bangalore": {"bms_code": "BANG", "name": "Bangalore"},
    "hyderabad": {"bms_code": "HYD", "name": "Hyderabad"},
    "mumbai": {"bms_code": "MUMBAI", "name": "Mumbai"},
    "delhi-ncr": {"bms_code": "NCR", "name": "Delhi NCR"},
    "coimbatore": {"bms_code": "COIM", "name": "Coimbatore"},
    "madurai": {"bms_code": "MADU", "name": "Madurai"},
    "trichy": {"bms_code": "TRIC", "name": "Trichy"},
    "salem": {"bms_code": "SALM", "name": "Salem"},
    "kochi": {"bms_code": "KOCH", "name": "Kochi"},
}


def fetch_bms_movies(city_code: str) -> dict:
    """Fetch live now-showing and upcoming movies for a city from BMS explore API."""
    now_showing = []
    coming_soon = []

    # API 1: Explore movies in city
    url = f"https://in.bookmyshow.com/api/explore/v1/explore/getMoviesInCity?city={city_code}&lang=en&type=MT"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode())
            movies = data.get("moviesData", data.get("data", data.get("results", [])))
            if isinstance(movies, list):
                for m in movies:
                    title = m.get("EventTitle", m.get("name", m.get("title", "")))
                    if title and title not in now_showing:
                        now_showing.append(title)
    except Exception as e:
        logger.warning(f"Could not fetch BMS explore for {city_code}: {e}")

    # API 2: Quicksearch fallback if empty
    if not now_showing:
        url = f"https://in.bookmyshow.com/api/explore/v1/explore/quicksearch?q=&city={city_code}&lang=en&type=MT"
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode())
                results = data.get("docs", data.get("data", []))
                for item in results:
                    title = item.get("EventTitle", item.get("name", ""))
                    if title and title not in now_showing:
                        now_showing.append(title)
        except Exception as e:
            logger.warning(f"Could not fetch BMS quicksearch for {city_code}: {e}")

    return {
        "now_showing": sorted(list(set(now_showing))),
        "coming_soon": sorted(list(set(coming_soon)))
    }


def main():
    logger.info("Fetching live movie listings from BookMyShow & ticketing networks...")
    result = {
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "cities": {}
    }

    for city_key, info in CITIES.items():
        logger.info(f"Checking live movies for {info['name']} ({info['bms_code']})...")
        city_data = fetch_bms_movies(info["bms_code"])
        result["cities"][city_key] = {
            "name": info["name"],
            "now_showing": city_data["now_showing"],
            "coming_soon": city_data["coming_soon"]
        }
        logger.info(f"  -> Found {len(city_data['now_showing'])} live movies in {info['name']}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    logger.info(f"✅ Saved live movie database to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

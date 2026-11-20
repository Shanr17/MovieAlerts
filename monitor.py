"""
Movie Ticket Alert Monitor
Main orchestrator that runs checkers and sends notifications.
"""

import json
import logging
import sys
import os
import time
import argparse
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from checkers.bms import check as check_bms
from checkers.pvr import check as check_pvr
from checkers.district import check as check_district
from notifiers.telegram import send as send_telegram
from notifiers.discord import send as send_discord
from notifiers.ntfy import send as send_ntfy

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Paths
BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
STATE_PATH = BASE_DIR / "state.json"


def load_config() -> dict:
    """Load configuration from config.json or environment variables."""
    # Load base config from file
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)
    else:
        config = {}

    # Override with environment variables (for GitHub Actions secrets)
    env_mappings = {
        "MOVIE_NAME": "movie",
        "THEATER_NAME": "theater",
        "CITY": "city",
        "CITY_CODE": "city_code",
        "TELEGRAM_BOT_TOKEN": ("alerts", "telegram", "bot_token"),
        "TELEGRAM_CHAT_ID": ("alerts", "telegram", "chat_id"),
        "TELEGRAM_ENABLED": ("alerts", "telegram", "enabled"),
        "DISCORD_WEBHOOK_URL": ("alerts", "discord", "webhook_url"),
        "DISCORD_ENABLED": ("alerts", "discord", "enabled"),
        "NTFY_TOPIC": ("alerts", "ntfy", "topic"),
        "NTFY_SERVER": ("alerts", "ntfy", "server"),
        "NTFY_ENABLED": ("alerts", "ntfy", "enabled"),
        "CHECK_BMS": ("platforms", "bms"),
        "CHECK_PVR": ("platforms", "pvr"),
        "CHECK_DISTRICT": ("platforms", "district"),
        "CHECK_NEXT_DAYS": "check_next_days",
        "TARGET_DATE": "target_date",
        "ACTIVE": "active",
    }

    for env_key, config_path in env_mappings.items():
        value = os.environ.get(env_key)
        if value is not None and str(value).strip() != "":
            val_str = str(value).strip()
            # Convert string booleans
            if val_str.lower() in ("true", "1", "yes"):
                value = True
            elif val_str.lower() in ("false", "0", "no"):
                value = False
            else:
                value = val_str

            # Set nested config value
            if isinstance(config_path, tuple):
                obj = config
                for key in config_path[:-1]:
                    obj = obj.setdefault(key, {})
                obj[config_path[-1]] = value
            else:
                config[config_path] = value

    return config


def load_state() -> dict:
    """Load alert state to track what's already been notified."""
    if STATE_PATH.exists():
        with open(STATE_PATH, "r") as f:
            return json.load(f)
    return {"alerted": {}, "last_check": None}


def save_state(state: dict):
    """Save alert state."""
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def _make_alert_key(platform: str, movie: str, theater: str, target_date: str = "") -> str:
    """Create a unique key for tracking alerts."""
    return f"{platform}|{movie}|{theater}|{target_date}".lower()


def run_checkers(config: dict) -> list:
    """Run all enabled platform checkers."""
    results = []
    platforms = config.get("platforms", {})

    checkers = {
        "bms": ("BookMyShow", check_bms),
        "pvr": ("PVR Cinemas", check_pvr),
        "district": ("District", check_district),
    }

    for key, (name, checker_fn) in checkers.items():
        if platforms.get(key, False):
            logger.info(f"Checking {name}...")
            try:
                result = checker_fn(config)
                results.append(result)
                if result["available"]:
                    logger.info(f"🎉 {name}: BOOKING AVAILABLE!")
                else:
                    logger.info(f"❌ {name}: {result.get('reason', 'Not available')}")
            except Exception as e:
                logger.error(f"❌ {name} checker failed: {e}")
                results.append({
                    "available": False,
                    "platform": name,
                    "reason": f"Checker error: {str(e)}",
                })
        else:
            logger.info(f"⏭️ {name}: Disabled in config")

    return results


def send_notifications(config: dict, booking_info: dict) -> dict:
    """Send alerts through all enabled notification channels."""
    alerts_config = config.get("alerts", {})
    results = {}

    # Telegram
    tg_config = alerts_config.get("telegram", {})
    if tg_config.get("enabled", False):
        results["telegram"] = send_telegram(tg_config, booking_info)
    else:
        logger.info("⏭️ Telegram: Disabled")

    # Discord
    dc_config = alerts_config.get("discord", {})
    if dc_config.get("enabled", False):
        results["discord"] = send_discord(dc_config, booking_info)
    else:
        logger.info("⏭️ Discord: Disabled")

    # Ntfy
    ntfy_config = alerts_config.get("ntfy", {})
    if ntfy_config.get("enabled", False):
        results["ntfy"] = send_ntfy(ntfy_config, booking_info)
    else:
        logger.info("⏭️ Ntfy: Disabled")

    return results


def run_single_check(config: dict, state: dict) -> bool:
    """Run one pass of checkers and send notifications if tickets found."""
    results = run_checkers(config)
    any_available = False

    for result in results:
        if result["available"]:
            target_date = config.get("target_date", "")
            alert_key = _make_alert_key(
                result["platform"], result["movie"], result["theater"], target_date
            )

            # Check if we already alerted for this
            if alert_key in state.get("alerted", {}):
                last_alert = state["alerted"][alert_key]
                logger.info(
                    f"ℹ️ Already alerted for {result['platform']} "
                    f"on {last_alert['timestamp']}"
                )
                continue

            any_available = True
            logger.info(f"\n{'🎉' * 10}")
            logger.info(f"BOOKING OPEN on {result['platform']}!")
            logger.info(f"{'🎉' * 10}\n")

            # Send notifications
            notif_results = send_notifications(config, result)

            # Update state
            state.setdefault("alerted", {})[alert_key] = {
                "timestamp": datetime.now().isoformat(),
                "platform": result["platform"],
                "showtimes": result.get("showtimes", []),
                "booking_url": result.get("booking_url", ""),
                "notification_results": {
                    k: v for k, v in notif_results.items()
                },
            }

    state["last_check"] = datetime.now().isoformat()
    save_state(state)

    if not any_available:
        logger.info("📭 No new bookings found.")

    return any_available


def main():
    """Main entrypoint supporting multi-check intervals."""
    parser = argparse.ArgumentParser(description="Movie Ticket Alert Monitor")
    parser.add_argument(
        "--iterations",
        type=int,
        default=int(os.environ.get("RUN_ITERATIONS", 2)),
        help="Number of checks per job run (default: 2, for GitHub Actions)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=int(os.environ.get("CHECK_INTERVAL", 150)),
        help="Seconds to wait between checks (default: 150s = 2.5 mins)",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run continuously in an infinite loop (e.g. for local PC or Termux)",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("🎬 Movie Ticket Alert Monitor Started")
    logger.info("=" * 60)

    config = load_config()
    movie = config.get("movie", "")
    theater = config.get("theater", "")
    city = config.get("city", "")

    if not movie or not theater or not city:
        logger.error("❌ Missing required config: movie, theater, or city")
        logger.error("   Set them in config.json or as environment variables")
        sys.exit(1)

    if not config.get("active", True):
        logger.info("⏸️ Monitor is PAUSED (active=false). Exiting.")
        return

    logger.info(f"🎥 Movie:       {movie}")
    logger.info(f"🏢 Theater:     {theater}")
    logger.info(f"🏙️ City:        {city}")
    logger.info(f"🎯 Target Date: {config.get('target_date') or 'Any upcoming date'}")
    logger.info(f"⏱️ Interval:    {args.interval}s (2.5 mins)")
    logger.info("-" * 60)

    state = load_state()

    current_iter = 0
    total_iters = 0 if args.loop else max(1, args.iterations)

    while True:
        current_iter += 1
        iter_str = f"Run {current_iter}" if args.loop else f"Run {current_iter}/{total_iters}"
        logger.info(f"\n--- Checking now ({iter_str}) ---")

        run_single_check(config, state)

        # Stop if we reached iteration limit and not in infinite loop
        if not args.loop and current_iter >= total_iters:
            break

        logger.info(f"⏳ Waiting {args.interval} seconds (2.5 minutes) until next check...")
        time.sleep(args.interval)

    logger.info("\n" + "=" * 60)
    logger.info("✅ Finished scheduled checks for this cycle")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

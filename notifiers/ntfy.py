"""
Ntfy.sh Notifier
Sends booking alerts via ntfy.sh push notifications.
No account needed — just install the ntfy app and subscribe to your topic.
"""

import requests
import logging

logger = logging.getLogger(__name__)


def _format_message(booking_info: dict) -> str:
    """Format booking info into a plain text message."""
    platform = booking_info.get("platform", "Unknown")
    movie = booking_info.get("movie", "Unknown")
    theater = booking_info.get("theater", "Unknown")
    showtimes = booking_info.get("showtimes", [])
    dates = booking_info.get("dates", [])

    msg = f"Movie: {movie}\n"
    msg += f"Theater: {theater}\n"
    msg += f"Platform: {platform}\n"

    if dates:
        msg += f"Dates: {', '.join(dates)}\n"

    if showtimes:
        msg += f"\nShowtimes:\n"
        for st in showtimes[:8]:
            msg += f"  • {st}\n"
        if len(showtimes) > 8:
            msg += f"  ...and {len(showtimes) - 8} more\n"

    return msg


def _get_timestamp() -> str:
    """Get current timestamp string."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def send(config: dict, booking_info: dict) -> bool:
    """
    Send an ntfy.sh push notification.

    Args:
        config: Dict with keys: topic, server (optional, defaults to https://ntfy.sh)
        booking_info: Dict with booking details

    Returns:
        True if notification sent successfully
    """
    topic = config.get("topic", "")
    server = config.get("server", "https://ntfy.sh").rstrip("/")

    if not topic:
        logger.warning("[Ntfy] Missing topic — skipping")
        return False

    movie = booking_info.get("movie", "Unknown Movie")
    booking_url = booking_info.get("booking_url", "")
    message = _format_message(booking_info)

    try:
        url = f"{server}/{topic}"

        # Clean header values to avoid HTTP latin-1 encoding errors with emojis
        safe_title = f"Booking Open: {movie}".encode("ascii", "ignore").decode("ascii").strip()

        headers = {
            "Title": safe_title,
            "Priority": "urgent",
            "Tags": "clapper,tada,ticket",
        }

        # Add click action to open booking URL
        if booking_url:
            headers["Click"] = booking_url
            headers["Actions"] = f"view, Book Now, {booking_url}"

        resp = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=10)

        if resp.status_code == 200:
            logger.info(f"[Ntfy] ✅ Alert sent to topic '{topic}'")
            return True
        else:
            logger.error(f"[Ntfy] Failed: HTTP {resp.status_code} - {resp.text}")
            return False

    except requests.exceptions.RequestException as e:
        logger.error(f"[Ntfy] Failed to send alert: {e}")
        return False

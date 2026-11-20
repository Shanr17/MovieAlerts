"""
Discord Notifier
Sends booking alerts via a Discord Webhook.
"""

import requests
import logging

logger = logging.getLogger(__name__)


def _format_embed(booking_info: dict) -> dict:
    """Format booking info into a Discord embed."""
    platform = booking_info.get("platform", "Unknown")
    movie = booking_info.get("movie", "Unknown")
    theater = booking_info.get("theater", "Unknown")
    showtimes = booking_info.get("showtimes", [])
    booking_url = booking_info.get("booking_url", "")
    dates = booking_info.get("dates", [])

    fields = [
        {"name": "🎥 Movie", "value": movie, "inline": True},
        {"name": "🏢 Theater", "value": theater, "inline": True},
        {"name": "📱 Platform", "value": platform, "inline": True},
    ]

    if dates:
        fields.append({
            "name": "📅 Dates",
            "value": ", ".join(dates),
            "inline": False,
        })

    if showtimes:
        shows_text = "\n".join(f"• {st}" for st in showtimes[:10])
        if len(showtimes) > 10:
            shows_text += f"\n*...and {len(showtimes) - 10} more*"
        fields.append({
            "name": "🕐 Showtimes",
            "value": shows_text,
            "inline": False,
        })

    embed = {
        "title": "🎬 BOOKING ALERT!",
        "description": f"Ticket bookings are now open on **{platform}**!",
        "color": 0x00FF00,  # Green
        "fields": fields,
        "footer": {"text": f"TicketAlert • {_get_timestamp()}"},
    }

    if booking_url:
        embed["url"] = booking_url

    return embed


def _get_timestamp() -> str:
    """Get current timestamp string."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def send(config: dict, booking_info: dict) -> bool:
    """
    Send a Discord webhook notification.

    Args:
        config: Dict with key: webhook_url
        booking_info: Dict with booking details

    Returns:
        True if message sent successfully
    """
    webhook_url = config.get("webhook_url", "")

    if not webhook_url:
        logger.warning("[Discord] Missing webhook_url — skipping")
        return False

    embed = _format_embed(booking_info)
    booking_url = booking_info.get("booking_url", "")

    payload = {
        "content": "🎟️ **Ticket bookings are OPEN!** Book now before seats fill up!",
        "embeds": [embed],
    }

    # Add a button-like link
    if booking_url:
        payload["content"] += f"\n🔗 **Book here:** {booking_url}"

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)

        # Discord returns 204 on success
        if resp.status_code in (200, 204):
            logger.info("[Discord] ✅ Alert sent via webhook")
            return True
        else:
            logger.error(f"[Discord] Webhook failed: HTTP {resp.status_code} - {resp.text}")
            return False

    except requests.exceptions.RequestException as e:
        logger.error(f"[Discord] Failed to send alert: {e}")
        return False

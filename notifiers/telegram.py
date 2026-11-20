"""
Telegram Notifier
Sends booking alerts via a Telegram Bot.
"""

import requests
import logging

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


def _format_message(booking_info: dict) -> str:
    """Format booking info into a Telegram-friendly message."""
    platform = booking_info.get("platform", "Unknown")
    movie = booking_info.get("movie", "Unknown")
    theater = booking_info.get("theater", "Unknown")
    showtimes = booking_info.get("showtimes", [])
    booking_url = booking_info.get("booking_url", "")
    dates = booking_info.get("dates", [])

    msg = f"🎬 *BOOKING ALERT!*\n\n"
    msg += f"🎥 *Movie:* {movie}\n"
    msg += f"🏢 *Theater:* {theater}\n"
    msg += f"📱 *Platform:* {platform}\n"

    if dates:
        msg += f"📅 *Dates:* {', '.join(dates)}\n"

    if showtimes:
        msg += f"\n🕐 *Showtimes:*\n"
        for st in showtimes[:10]:  # Limit to 10 showtimes
            msg += f"  • {st}\n"
        if len(showtimes) > 10:
            msg += f"  _...and {len(showtimes) - 10} more_\n"

    if booking_url:
        msg += f"\n🔗 [Book Now!]({booking_url})"

    msg += f"\n\n⏰ _Detected at {_get_timestamp()}_"
    return msg


def _get_timestamp() -> str:
    """Get current timestamp string."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def send(config: dict, booking_info: dict) -> bool:
    """
    Send a Telegram notification.

    Args:
        config: Dict with keys: bot_token, chat_id
        booking_info: Dict with booking details

    Returns:
        True if message sent successfully
    """
    bot_token = config.get("bot_token", "")
    chat_id = config.get("chat_id", "")

    if not bot_token or not chat_id:
        logger.warning("[Telegram] Missing bot_token or chat_id — skipping")
        return False

    message = _format_message(booking_info)

    try:
        url = f"{TELEGRAM_API}/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,
        }

        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()

        result = resp.json()
        if result.get("ok"):
            res_data = result.get("result", {})
            bot_user = res_data.get("from", {}).get("username", "bot")
            chat_info = res_data.get("chat", {})
            chat_target = chat_info.get("username") or chat_info.get("first_name") or str(chat_id)
            msg_id = res_data.get("message_id", "")
            logger.info(f"[Telegram] ✅ Alert sent successfully from @{bot_user} to {chat_target} (ID: {chat_id}, Msg #{msg_id})")
            return True
        else:
            logger.error(f"[Telegram] API error: {result.get('description', 'Unknown error')}")
            return False

    except requests.exceptions.RequestException as e:
        logger.error(f"[Telegram] Failed to send alert: {e}")
        return False

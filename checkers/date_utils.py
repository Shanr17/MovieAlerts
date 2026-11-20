"""
Date Parsing Utilities for Target Booking Dates
"""

from datetime import datetime, date


def parse_target_date(date_str: str) -> date | None:
    """
    Parse a target date string into a date object.
    Supports YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY, DD/MM, DD-MM, etc.
    """
    if not date_str or not str(date_str).strip():
        return None

    clean = str(date_str).strip()
    current_year = datetime.now().year

    formats = [
        "%Y-%m-%d",       # 2026-11-23
        "%d/%m/%Y",       # 23/11/2026
        "%d-%m-%Y",       # 23-11-2026
        "%Y/%m/%d",       # 2026/11/23
        "%d %b %Y",       # 23 Nov 2026
        "%d %B %Y",       # 23 November 2026
    ]

    for fmt in formats:
        try:
            return datetime.strptime(clean, fmt).date()
        except ValueError:
            continue

    no_year_formats = [
        "%d/%m",          # 23/11
        "%d-%m",          # 23-11
        "%d %b",          # 23 Nov
        "%d %B",          # 23 November
    ]

    for fmt in no_year_formats:
        try:
            parsed = datetime.strptime(clean, fmt).date()
            return parsed.replace(year=current_year)
        except ValueError:
            continue

    return None

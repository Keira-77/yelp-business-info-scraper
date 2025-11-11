thonfrom datetime import datetime, timezone

def current_timestamp() -> str:
    """
    Returns the current UTC timestamp as a human-readable string.
    Format: YYYY-MM-DD HH:MM:SS
    """
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%d %H:%M:%S")
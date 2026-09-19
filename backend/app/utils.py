from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC now — stored consistently across all tables."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

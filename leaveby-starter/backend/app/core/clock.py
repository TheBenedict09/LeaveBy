from datetime import UTC, datetime


def now() -> datetime:
    """Single place to get 'now', so tests can patch it."""
    return datetime.now(UTC)

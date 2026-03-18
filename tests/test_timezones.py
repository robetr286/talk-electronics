from datetime import datetime, timedelta

from talk_electronic.routes import processing


def test_sanitize_entry_adds_timezone_aware_createdAt():
    payload = {}
    cleaned = processing._sanitize_entry(payload)
    created = cleaned.get("meta", {}).get("createdAt")
    assert isinstance(created, str)
    # Should be ISO parseable and timezone-aware (UTC offset 0)
    dt = datetime.fromisoformat(created)
    assert dt.tzinfo is not None
    assert dt.utcoffset() == timedelta(0)

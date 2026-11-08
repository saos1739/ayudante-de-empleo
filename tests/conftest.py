import pytest

from radar import db


@pytest.fixture
def base(tmp_path, monkeypatch):
    """Base SQLite temporal: ningún test toca tu base real."""
    monkeypatch.setenv("RADAR_DB", str(tmp_path / "radar.db"))
    db.init_db()
    return tmp_path / "radar.db"

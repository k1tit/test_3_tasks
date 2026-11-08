from datetime import date

import pytest

from etl.config import load_settings, resolve_as_of, resolve_window


def test_blank_env_means_full_reload():
    assert resolve_window(None, None, "  ", "") == (None, None)


def test_env_window_is_inclusive_pair():
    assert resolve_window(None, None, "2026-01-01", "2026-01-31") == (
        date(2026, 1, 1),
        date(2026, 1, 31),
    )


def test_cli_window_replaces_env(monkeypatch):
    monkeypatch.setenv("ETL_START_DATE", "2026-01-01")
    monkeypatch.setenv("ETL_END_DATE", "2026-01-31")
    settings = load_settings(["--start-date", "2026-02-01", "--end-date", "2026-02-02"])
    assert settings.start_date == date(2026, 2, 1)
    assert settings.end_date == date(2026, 2, 2)
    assert settings.full_reload is False


def test_half_specified_window_is_rejected():
    with pytest.raises(ValueError):
        resolve_window("2026-02-01", None, None, None)
    with pytest.raises(ValueError):
        resolve_window(None, None, "2026-02-01", " ")


def test_inverted_window_is_rejected():
    with pytest.raises(ValueError):
        resolve_window("2026-02-02", "2026-02-01", None, None)


def test_as_of_defaults_to_snapshot_and_cli_overrides(monkeypatch):
    monkeypatch.delenv("AS_OF_DATE", raising=False)
    assert resolve_as_of(None) == date(2026, 10, 26)
    assert resolve_as_of("  ") == date(2026, 10, 26)
    settings = load_settings(["--as-of", "2026-09-01"])
    assert settings.as_of == date(2026, 9, 1)


def test_invalid_date_is_rejected():
    with pytest.raises(ValueError):
        resolve_window("2026-13-01", "2026-13-02", None, None)

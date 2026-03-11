from datetime import date, timedelta

from app.services.scheduler import compute_trigger_date, is_within_window, opens_tonight


def test_compute_trigger_date():
    target = date(2026, 6, 13)
    assert compute_trigger_date(target) == target - timedelta(days=91)


def test_is_within_window_true():
    target = date.today() + timedelta(days=30)
    assert is_within_window(target) is True


def test_is_within_window_false_at_90():
    """delta == 90 means window opens tonight, NOT within window yet."""
    target = date.today() + timedelta(days=90)
    assert is_within_window(target) is False


def test_is_within_window_false_past():
    target = date.today() - timedelta(days=1)
    assert is_within_window(target) is False


def test_is_within_window_false_too_far():
    target = date.today() + timedelta(days=100)
    assert is_within_window(target) is False


def test_opens_tonight_true():
    target = date.today() + timedelta(days=90)
    assert opens_tonight(target) is True


def test_opens_tonight_false():
    target = date.today() + timedelta(days=89)
    assert opens_tonight(target) is False

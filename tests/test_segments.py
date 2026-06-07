"""Тесты сегментации пользователей и расчёта мест (segments.py)."""
from __future__ import annotations

import pytest

import config
import db
import segments


# ==================== segment_of ====================

def test_segment_awaiting_payment():
    assert segments.segment_of(db.STATUS_AWAITING_PAYMENT) == segments.SEG_NOT_PAID


def test_segment_rejected():
    assert segments.segment_of(db.STATUS_REJECTED) == segments.SEG_NOT_PAID


def test_segment_door():
    assert segments.segment_of(db.STATUS_DOOR) == segments.SEG_DOOR


def test_segment_confirmed_online():
    assert segments.segment_of(db.STATUS_CONFIRMED_ONLINE) == segments.SEG_PAID


def test_segment_new_returns_none():
    assert segments.segment_of(db.STATUS_NEW) is None


def test_segment_awaiting_confirmation_returns_none():
    assert segments.segment_of(db.STATUS_AWAITING_CONFIRMATION) is None


def test_segment_unknown_returns_none():
    assert segments.segment_of("nonexistent_status") is None


# ==================== seats_left / is_sold_out ====================

async def test_seats_left_full_capacity(fresh_db):
    left = await segments.seats_left()
    assert left == config.EVENT_CAPACITY


async def test_seats_left_after_bookings(fresh_db):
    await db.ensure_user(600, "u600")
    await db.set_order(600, 5, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)
    left = await segments.seats_left()
    assert left == config.EVENT_CAPACITY - 5


async def test_is_sold_out_false_by_default(fresh_db):
    assert await segments.is_sold_out() is False


async def test_is_sold_out_true_at_capacity(fresh_db, monkeypatch):
    monkeypatch.setattr(config, "EVENT_CAPACITY", 2)
    await db.ensure_user(601, "u601")
    await db.set_order(601, 2, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)
    assert await segments.is_sold_out() is True


async def test_is_sold_out_false_one_seat_left(fresh_db, monkeypatch):
    monkeypatch.setattr(config, "EVENT_CAPACITY", 5)
    await db.ensure_user(602, "u602")
    await db.set_order(602, 4, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)
    assert await segments.is_sold_out() is False


# ==================== scarcity_line ====================

async def test_scarcity_line_none_when_plenty(fresh_db, monkeypatch):
    monkeypatch.setattr(config, "EVENT_CAPACITY", 60)
    monkeypatch.setattr(config, "SEATS_REVEAL_THRESHOLD", 15)
    result = await segments.scarcity_line()
    assert result is None


async def test_scarcity_line_shows_at_threshold(fresh_db, monkeypatch):
    monkeypatch.setattr(config, "EVENT_CAPACITY", 20)
    monkeypatch.setattr(config, "SEATS_REVEAL_THRESHOLD", 15)
    # Занимаем 10 мест → осталось 10 ≤ 15
    await db.ensure_user(610, "u610")
    await db.set_order(610, 10, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)
    result = await segments.scarcity_line()
    assert result is not None
    assert "10" in result


async def test_scarcity_line_none_when_sold_out(fresh_db, monkeypatch):
    monkeypatch.setattr(config, "EVENT_CAPACITY", 3)
    monkeypatch.setattr(config, "SEATS_REVEAL_THRESHOLD", 15)
    await db.ensure_user(611, "u611")
    await db.set_order(611, 3, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)
    # left == 0 → не показываем
    result = await segments.scarcity_line()
    assert result is None


# ==================== user_ids_for_segment ====================

async def test_user_ids_for_segment_not_paid(fresh_db):
    await db.ensure_user(620, "u620")
    await db.set_order(620, 1, "vnd", "x", db.STATUS_AWAITING_PAYMENT)
    await db.ensure_user(621, "u621")
    await db.set_order(621, 1, "vnd", "x", db.STATUS_REJECTED)

    ids = await segments.user_ids_for_segment(segments.SEG_NOT_PAID)
    assert set(ids) == {620, 621}


async def test_user_ids_for_segment_door(fresh_db):
    await db.ensure_user(630, "u630")
    await db.set_order(630, 2, "door", "x", db.STATUS_DOOR)

    ids = await segments.user_ids_for_segment(segments.SEG_DOOR)
    assert 630 in ids


async def test_user_ids_for_segment_paid(fresh_db):
    await db.ensure_user(640, "u640")
    await db.set_order(640, 1, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)

    ids = await segments.user_ids_for_segment(segments.SEG_PAID)
    assert 640 in ids


async def test_user_ids_for_segment_empty(fresh_db):
    ids = await segments.user_ids_for_segment(segments.SEG_PAID)
    assert ids == []

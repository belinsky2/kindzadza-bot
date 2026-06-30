"""Тесты конфигурации и вспомогательных функций (config.py)."""
from __future__ import annotations

import os
import pytest

import config


# ==================== format_amount ====================

def test_format_amount_vnd_single():
    result = config.format_amount("vnd", 1)
    assert result == "500 000 ₫"


def test_format_amount_vnd_multiple():
    result = config.format_amount("vnd", 3)
    assert result == "1 500 000 ₫"


def test_format_amount_door_single():
    result = config.format_amount("door", 1)
    assert result == "500 000 ₫"


def test_format_amount_door_multiple():
    result = config.format_amount("door", 2)
    assert result == "1 000 000 ₫"


def test_format_amount_uses_spaces_not_commas():
    """Тысячи разделяются пробелом (российский формат), не запятой."""
    result = config.format_amount("vnd", 1)
    assert "," not in result
    assert " " in result


def test_format_amount_all_methods_non_empty():
    for method in config.PAYMENT_METHODS:
        result = config.format_amount(method, 1)
        assert result
        assert len(result) > 0


# ==================== validate ====================

def test_validate_empty_bot_token(monkeypatch):
    monkeypatch.setattr(config, "BOT_TOKEN", "")
    issues = config.validate()
    assert any("BOT_TOKEN" in i for i in issues)


def test_validate_missing_admin_group(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_GROUP_ID", 0)
    issues = config.validate()
    assert any("ADMIN_GROUP_ID" in i for i in issues)


def test_validate_missing_spreadsheet_id(monkeypatch):
    monkeypatch.setattr(config, "SPREADSHEET_ID", "")
    issues = config.validate()
    assert any("SPREADSHEET_ID" in i for i in issues)


def test_validate_missing_organizer_username(monkeypatch):
    monkeypatch.setattr(config, "ORGANIZER_USERNAME", "")
    issues = config.validate()
    assert any("ORGANIZER_USERNAME" in i for i in issues)


def test_validate_missing_bot_username(monkeypatch):
    monkeypatch.setattr(config, "BOT_USERNAME", "")
    issues = config.validate()
    assert any("BOT_USERNAME" in i for i in issues)


def test_validate_all_set_returns_empty(monkeypatch):
    monkeypatch.setattr(config, "BOT_TOKEN", "123:ABC")
    monkeypatch.setattr(config, "ADMIN_GROUP_ID", -100123456)
    monkeypatch.setattr(config, "SPREADSHEET_ID", "sheet_id")
    monkeypatch.setattr(config, "ORGANIZER_USERNAME", "org_user")
    monkeypatch.setattr(config, "BOT_USERNAME", "my_bot")
    issues = config.validate()
    assert issues == []


# ==================== PAYMENT_METHODS структура ====================

def test_payment_methods_have_required_keys():
    required = {"label", "unit", "cur", "online"}
    for key, method in config.PAYMENT_METHODS.items():
        assert required.issubset(set(method.keys())), f"Метод {key} неполный"


def test_online_methods_are_vnd():
    assert set(config.ONLINE_METHODS) == {"vnd"}


def test_door_is_not_online():
    assert not config.PAYMENT_METHODS["door"]["online"]


def test_online_methods_are_online():
    for m in config.ONLINE_METHODS:
        assert config.PAYMENT_METHODS[m]["online"]

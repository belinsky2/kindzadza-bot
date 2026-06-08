"""Тесты всех операций с базой данных (db.py)."""
from __future__ import annotations

import pytest

import db


# ==================== ensure_user ====================

async def test_ensure_user_creates_new(fresh_db):
    await db.ensure_user(1, "alice")
    reg = await db.get_registration(1)
    assert reg is not None
    assert reg["user_id"] == 1
    assert reg["username"] == "alice"
    assert reg["status"] == "new"


async def test_ensure_user_without_username(fresh_db):
    await db.ensure_user(2, None)
    reg = await db.get_registration(2)
    assert reg is not None
    assert reg["username"] is None


async def test_ensure_user_updates_username(fresh_db):
    await db.ensure_user(3, "old_nick")
    await db.ensure_user(3, "new_nick")
    reg = await db.get_registration(3)
    assert reg["username"] == "new_nick"


async def test_ensure_user_preserves_status(fresh_db):
    await db.ensure_user(4, "user4")
    await db.update_status(4, db.STATUS_CONFIRMED_ONLINE)
    # повторный ensure_user не должен сбрасывать статус
    await db.ensure_user(4, "user4_new_nick")
    reg = await db.get_registration(4)
    assert reg["status"] == db.STATUS_CONFIRMED_ONLINE


# ==================== delete_registration ====================

async def test_delete_registration_removes_record(fresh_db):
    await db.ensure_user(5, "user5")
    await db.set_order(5, 2, "vnd", "400 000 ₫", db.STATUS_CONFIRMED_ONLINE)
    await db.delete_registration(5)
    assert await db.get_registration(5) is None


async def test_delete_registration_missing_is_noop(fresh_db):
    # удаление несуществующей записи не должно падать
    await db.delete_registration(999)
    assert await db.get_registration(999) is None


async def test_ensure_user_multiple(fresh_db):
    for uid in range(10, 15):
        await db.ensure_user(uid, f"user{uid}")
    ids = await db.list_all_user_ids()
    assert set(ids) == {10, 11, 12, 13, 14}


# ==================== get_registration ====================

async def test_get_registration_nonexistent(fresh_db):
    result = await db.get_registration(9999)
    assert result is None


async def test_get_registration_returns_dict(fresh_db):
    await db.ensure_user(20, "bob")
    reg = await db.get_registration(20)
    assert isinstance(reg, dict)


async def test_get_registration_all_keys(fresh_db):
    await db.ensure_user(21, "charlie")
    reg = await db.get_registration(21)
    expected_keys = {
        "user_id", "username", "name", "qty", "payment_method",
        "amount", "status", "raffle_numbers", "ticket_code",
        "checked_in_at", "arrived_count", "created_at", "updated_at",
    }
    assert expected_keys.issubset(set(reg.keys()))


# ==================== set_name ====================

async def test_set_name_stores_correctly(fresh_db):
    await db.ensure_user(30, "dave")
    await db.set_name(30, "David Smith")
    reg = await db.get_registration(30)
    assert reg["name"] == "David Smith"


async def test_set_name_updates_timestamp(fresh_db):
    import time
    await db.ensure_user(31, "eve")
    t_before = int(time.time())
    await db.set_name(31, "Eve")
    reg = await db.get_registration(31)
    assert reg["updated_at"] >= t_before


# ==================== set_order ====================

async def test_set_order_stores_all_fields(fresh_db):
    await db.ensure_user(40, "frank")
    await db.set_order(40, 3, "vnd", "600 000 ₫", db.STATUS_AWAITING_PAYMENT)
    reg = await db.get_registration(40)
    assert reg["qty"] == 3
    assert reg["payment_method"] == "vnd"
    assert reg["amount"] == "600 000 ₫"
    assert reg["status"] == db.STATUS_AWAITING_PAYMENT


async def test_set_order_door(fresh_db):
    await db.ensure_user(41, "grace")
    await db.set_order(41, 1, "door", "300 000 ₫", db.STATUS_DOOR)
    reg = await db.get_registration(41)
    assert reg["payment_method"] == "door"
    assert reg["status"] == db.STATUS_DOOR


# ==================== update_status ====================

async def test_update_status_all_values(fresh_db):
    await db.ensure_user(50, "hank")
    for status in [
        db.STATUS_NEW,
        db.STATUS_AWAITING_PAYMENT,
        db.STATUS_AWAITING_CONFIRMATION,
        db.STATUS_CONFIRMED_ONLINE,
        db.STATUS_DOOR,
        db.STATUS_REJECTED,
    ]:
        await db.update_status(50, status)
        reg = await db.get_registration(50)
        assert reg["status"] == status


# ==================== set_raffle_numbers ====================

async def test_set_raffle_numbers_stores_list(fresh_db):
    await db.ensure_user(60, "ivy")
    await db.set_raffle_numbers(60, [1, 2, 3])
    reg = await db.get_registration(60)
    assert reg["raffle_numbers"] == "1,2,3"


async def test_set_raffle_numbers_single(fresh_db):
    await db.ensure_user(61, "jack")
    await db.set_raffle_numbers(61, [7])
    reg = await db.get_registration(61)
    assert reg["raffle_numbers"] == "7"


# ==================== ticket_code ====================

async def test_set_and_get_ticket_code(fresh_db):
    await db.ensure_user(70, "kate")
    await db.set_ticket_code(70, "abc123XY")
    reg = await db.get_registration(70)
    assert reg["ticket_code"] == "abc123XY"


async def test_get_by_ticket_code_found(fresh_db):
    await db.ensure_user(71, "leo")
    await db.set_ticket_code(71, "FINDME01")
    result = await db.get_by_ticket_code("FINDME01")
    assert result is not None
    assert result["user_id"] == 71


async def test_get_by_ticket_code_not_found(fresh_db):
    result = await db.get_by_ticket_code("DOESNOTEXIST")
    assert result is None


async def test_get_by_ticket_code_unique(fresh_db):
    await db.ensure_user(72, "mia")
    await db.ensure_user(73, "noah")
    await db.set_ticket_code(72, "CODE_72")
    await db.set_ticket_code(73, "CODE_73")
    r72 = await db.get_by_ticket_code("CODE_72")
    r73 = await db.get_by_ticket_code("CODE_73")
    assert r72["user_id"] == 72
    assert r73["user_id"] == 73


# ==================== check_in ====================

async def test_check_in_sets_fields(fresh_db):
    import time
    await db.ensure_user(80, "olivia")
    t_before = int(time.time())
    await db.check_in(80, 2)
    reg = await db.get_registration(80)
    assert reg["checked_in_at"] >= t_before
    assert reg["arrived_count"] == 2


async def test_checkin_totals_empty(fresh_db):
    orders, guests = await db.checkin_totals()
    assert orders == 0
    assert guests == 0


async def test_checkin_totals_multiple(fresh_db):
    await db.ensure_user(81, "peter")
    await db.ensure_user(82, "quinn")
    await db.check_in(81, 3)
    await db.check_in(82, 2)
    orders, guests = await db.checkin_totals()
    assert orders == 2
    assert guests == 5


async def test_checkin_totals_only_checked_in(fresh_db):
    await db.ensure_user(83, "rose")
    await db.ensure_user(84, "sam")
    await db.check_in(83, 1)
    # user 84 не отмечен — не должен попасть в счёт
    orders, guests = await db.checkin_totals()
    assert orders == 1
    assert guests == 1


# ==================== assign_raffle_numbers ====================

async def test_assign_raffle_starts_at_one(fresh_db):
    numbers = await db.assign_raffle_numbers(1)
    assert numbers == [1]


async def test_assign_raffle_sequential(fresh_db):
    first = await db.assign_raffle_numbers(2)
    second = await db.assign_raffle_numbers(3)
    assert first == [1, 2]
    assert second == [3, 4, 5]


async def test_assign_raffle_no_duplicates(fresh_db):
    all_numbers = []
    for _ in range(5):
        nums = await db.assign_raffle_numbers(2)
        all_numbers.extend(nums)
    assert len(all_numbers) == len(set(all_numbers))


async def test_assign_raffle_counter_persistent(fresh_db):
    await db.assign_raffle_numbers(10)
    nums = await db.assign_raffle_numbers(1)
    assert nums == [11]


# ==================== seats_taken ====================

async def test_seats_taken_empty(fresh_db):
    count = await db.seats_taken()
    assert count == 0


async def test_seats_taken_counts_only_seat_statuses(fresh_db):
    # Создаём пользователей с разными статусами
    await db.ensure_user(90, "t90")
    await db.set_order(90, 2, "vnd", "400 000 ₫", db.STATUS_CONFIRMED_ONLINE)  # занимает место

    await db.ensure_user(91, "t91")
    await db.set_order(91, 1, "rub", "650 ₽", db.STATUS_AWAITING_CONFIRMATION)  # занимает место

    await db.ensure_user(92, "t92")
    await db.set_order(92, 3, "door", "900 000 ₫", db.STATUS_DOOR)  # не занимает

    await db.ensure_user(93, "t93")
    # status=new — не занимает

    taken = await db.seats_taken()
    assert taken == 3  # только 2 + 1


async def test_seats_taken_all_seat_statuses(fresh_db):
    for uid, status in [(200, db.STATUS_CONFIRMED_ONLINE), (201, db.STATUS_AWAITING_CONFIRMATION)]:
        await db.ensure_user(uid, f"user{uid}")
        await db.set_order(uid, 1, "vnd", "200 000 ₫", status)
    taken = await db.seats_taken()
    assert taken == 2


async def test_seats_taken_ignored_statuses(fresh_db):
    for uid, status in [
        (210, db.STATUS_NEW),
        (211, db.STATUS_AWAITING_PAYMENT),
        (212, db.STATUS_DOOR),
        (213, db.STATUS_REJECTED),
    ]:
        await db.ensure_user(uid, f"u{uid}")
        await db.set_order(uid, 5, "door", "x", status)
    taken = await db.seats_taken()
    assert taken == 0


# ==================== list_user_ids ====================

async def test_list_all_user_ids_empty(fresh_db):
    ids = await db.list_all_user_ids()
    assert ids == []


async def test_list_all_user_ids_populated(fresh_db):
    for uid in [300, 301, 302]:
        await db.ensure_user(uid, f"u{uid}")
    ids = await db.list_all_user_ids()
    assert set(ids) == {300, 301, 302}


async def test_list_user_ids_by_statuses_empty(fresh_db):
    result = await db.list_user_ids_by_statuses((db.STATUS_CONFIRMED_ONLINE,))
    assert result == []


async def test_list_user_ids_by_statuses_filters(fresh_db):
    await db.ensure_user(310, "u310")
    await db.set_order(310, 1, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)
    await db.ensure_user(311, "u311")
    await db.set_order(311, 1, "door", "x", db.STATUS_DOOR)
    await db.ensure_user(312, "u312")

    confirmed = await db.list_user_ids_by_statuses((db.STATUS_CONFIRMED_ONLINE,))
    assert confirmed == [310]

    door = await db.list_user_ids_by_statuses((db.STATUS_DOOR,))
    assert door == [311]

    both = await db.list_user_ids_by_statuses((db.STATUS_CONFIRMED_ONLINE, db.STATUS_DOOR))
    assert set(both) == {310, 311}


# ==================== breakdown_by_method ====================

async def test_breakdown_by_method_empty(fresh_db):
    result = await db.breakdown_by_method(db.STATUS_CONFIRMED_ONLINE)
    assert result == []


async def test_breakdown_by_method_groups_correctly(fresh_db):
    for uid, method, qty in [(400, "vnd", 2), (401, "vnd", 3), (402, "rub", 1)]:
        await db.ensure_user(uid, f"u{uid}")
        await db.set_order(uid, qty, method, "x", db.STATUS_CONFIRMED_ONLINE)

    result = await db.breakdown_by_method(db.STATUS_CONFIRMED_ONLINE)
    result_dict = {method: qty for method, qty in result}
    assert result_dict["vnd"] == 5
    assert result_dict["rub"] == 1


# ==================== count_by_status ====================

async def test_count_by_status_empty(fresh_db):
    result = await db.count_by_status()
    assert isinstance(result, dict)


async def test_count_by_status_counts_correctly(fresh_db):
    await db.ensure_user(500, "u500")
    await db.set_order(500, 2, "vnd", "x", db.STATUS_CONFIRMED_ONLINE)
    await db.ensure_user(501, "u501")
    await db.set_order(501, 3, "rub", "x", db.STATUS_CONFIRMED_ONLINE)
    await db.ensure_user(502, "u502")
    await db.set_order(502, 1, "door", "x", db.STATUS_DOOR)

    result = await db.count_by_status()
    assert result[db.STATUS_CONFIRMED_ONLINE]["count"] == 2
    assert result[db.STATUS_CONFIRMED_ONLINE]["qty"] == 5
    assert result[db.STATUS_DOOR]["count"] == 1
    assert result[db.STATUS_DOOR]["qty"] == 1


# ==================== broadcasts_log ====================

async def test_is_broadcast_sent_false_initially(fresh_db):
    result = await db.is_broadcast_sent("test_key")
    assert result is False


async def test_mark_and_check_broadcast_sent(fresh_db):
    await db.mark_broadcast_sent("reminder_eve")
    result = await db.is_broadcast_sent("reminder_eve")
    assert result is True


async def test_mark_broadcast_sent_idempotent(fresh_db):
    await db.mark_broadcast_sent("my_key")
    await db.mark_broadcast_sent("my_key")  # второй раз не должен упасть
    result = await db.is_broadcast_sent("my_key")
    assert result is True


async def test_broadcast_keys_independent(fresh_db):
    await db.mark_broadcast_sent("key_A")
    assert await db.is_broadcast_sent("key_A") is True
    assert await db.is_broadcast_sent("key_B") is False


# ==================== posts ====================

async def test_add_post_returns_id(fresh_db):
    post_id = await db.add_post(None, "Привет, мир!")
    assert isinstance(post_id, int)
    assert post_id >= 1


async def test_get_next_post_returns_oldest(fresh_db):
    id1 = await db.add_post(None, "Первый пост")
    await db.add_post(None, "Второй пост")
    post = await db.get_next_post()
    assert post["id"] == id1
    assert post["caption"] == "Первый пост"
    assert post["published"] == 0


async def test_get_next_post_returns_none_when_empty(fresh_db):
    post = await db.get_next_post()
    assert post is None


async def test_mark_post_published(fresh_db):
    post_id = await db.add_post(None, "Текст")
    await db.mark_post_published(post_id)
    post = await db.get_next_post()
    assert post is None


async def test_get_next_post_skips_published(fresh_db):
    id1 = await db.add_post(None, "Пост 1")
    id2 = await db.add_post(None, "Пост 2")
    await db.mark_post_published(id1)
    post = await db.get_next_post()
    assert post["id"] == id2


async def test_count_unpublished_posts(fresh_db):
    assert await db.count_unpublished_posts() == 0
    await db.add_post(None, "P1")
    await db.add_post(None, "P2")
    await db.add_post(None, "P3")
    assert await db.count_unpublished_posts() == 3
    post_id = await db.add_post(None, "P4")
    await db.mark_post_published(post_id)
    assert await db.count_unpublished_posts() == 3


async def test_add_post_with_photo(fresh_db):
    post_id = await db.add_post("file_id_123", "Подпись к фото")
    post = await db.get_next_post()
    assert post["file_path"] == "file_id_123"
    assert post["caption"] == "Подпись к фото"


# ==================== migration ====================

async def test_migration_idempotent(fresh_db):
    """_migrate() можно вызвать несколько раз без ошибок."""
    await db._migrate()
    await db._migrate()
    reg = await db.get_registration(1)
    assert reg is None  # просто не упало

"""SQLite-хранилище (источник истины бота). Async через aiosqlite."""
from __future__ import annotations

import time
from typing import Optional

import aiosqlite

import config

_db: Optional[aiosqlite.Connection] = None

# Статусы регистрации
STATUS_NEW = "new"                      # нажал /start, но не начал форму
STATUS_AWAITING_PAYMENT = "awaiting_payment"        # выбрал онлайн-способ, скрин не прислал
STATUS_AWAITING_CONFIRMATION = "awaiting_confirmation"  # прислал скрин, место в брони
STATUS_CONFIRMED_ONLINE = "confirmed_online"        # орг подтвердил онлайн-оплату
STATUS_DOOR = "door"                    # выбрал оплату на месте
STATUS_REJECTED = "rejected"            # орг отклонил скрин

# Статусы, занимающие место (бронь + подтверждённые)
SEAT_STATUSES = (STATUS_CONFIRMED_ONLINE, STATUS_AWAITING_CONFIRMATION)


def _now() -> int:
    return int(time.time())


async def init_db() -> None:
    global _db
    _db = await aiosqlite.connect(config.DB_PATH)
    _db.row_factory = aiosqlite.Row
    await _db.executescript(
        """
        CREATE TABLE IF NOT EXISTS registrations (
            user_id        INTEGER PRIMARY KEY,
            username       TEXT,
            name           TEXT,
            qty            INTEGER DEFAULT 1,
            payment_method TEXT,
            amount         TEXT,
            status         TEXT DEFAULT 'new',
            raffle_numbers TEXT,
            ticket_code    TEXT,
            checked_in_at  INTEGER,
            arrived_count  INTEGER,
            created_at     INTEGER,
            updated_at     INTEGER
        );

        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS broadcasts_log (
            key     TEXT PRIMARY KEY,
            sent_at INTEGER
        );

        CREATE TABLE IF NOT EXISTS posts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path  TEXT,
            caption    TEXT,
            published  INTEGER DEFAULT 0,
            created_at INTEGER
        );
        """
    )
    await _db.execute(
        "INSERT OR IGNORE INTO meta(key, value) VALUES('raffle_counter', '0')"
    )
    await _migrate()
    await _db.commit()


async def _migrate() -> None:
    """Добавляет недостающие колонки в существующую БД (idempotent)."""
    cur = await _db.execute("PRAGMA table_info(registrations)")
    cols = {r["name"] for r in await cur.fetchall()}
    for col, ddl in (
        ("ticket_code", "ticket_code TEXT"),
        ("checked_in_at", "checked_in_at INTEGER"),
        ("arrived_count", "arrived_count INTEGER"),
        ("food_order", "food_order TEXT"),
    ):
        if col not in cols:
            await _db.execute(f"ALTER TABLE registrations ADD COLUMN {ddl}")


async def close_db() -> None:
    if _db is not None:
        await _db.close()


# ---------- Регистрации ----------

async def ensure_user(user_id: int, username: Optional[str]) -> None:
    """Создаёт строку при первом /start, обновляет ник."""
    now = _now()
    await _db.execute(
        """
        INSERT INTO registrations(user_id, username, status, created_at, updated_at)
        VALUES(?, ?, 'new', ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, updated_at=excluded.updated_at
        """,
        (user_id, username, now, now),
    )
    await _db.commit()


async def get_registration(user_id: int) -> Optional[dict]:
    cur = await _db.execute("SELECT * FROM registrations WHERE user_id=?", (user_id,))
    row = await cur.fetchone()
    return dict(row) if row else None


async def delete_registration(user_id: int) -> None:
    """Полностью удаляет запись пользователя — /start начнётся с приветствия."""
    await _db.execute("DELETE FROM registrations WHERE user_id=?", (user_id,))
    await _db.commit()


async def set_name(user_id: int, name: str) -> None:
    await _db.execute(
        "UPDATE registrations SET name=?, updated_at=? WHERE user_id=?",
        (name, _now(), user_id),
    )
    await _db.commit()


async def set_order(user_id: int, qty: int, method: str, amount: str, status: str) -> None:
    await _db.execute(
        """
        UPDATE registrations
        SET qty=?, payment_method=?, amount=?, status=?, updated_at=?
        WHERE user_id=?
        """,
        (qty, method, amount, status, _now(), user_id),
    )
    await _db.commit()


async def update_status(user_id: int, status: str) -> None:
    await _db.execute(
        "UPDATE registrations SET status=?, updated_at=? WHERE user_id=?",
        (status, _now(), user_id),
    )
    await _db.commit()


async def set_raffle_numbers(user_id: int, numbers: list[int]) -> None:
    await _db.execute(
        "UPDATE registrations SET raffle_numbers=?, updated_at=? WHERE user_id=?",
        (",".join(str(n) for n in numbers), _now(), user_id),
    )
    await _db.commit()


# ---------- Билеты / check-in ----------

async def set_ticket_code(user_id: int, code: str) -> None:
    await _db.execute(
        "UPDATE registrations SET ticket_code=?, updated_at=? WHERE user_id=?",
        (code, _now(), user_id),
    )
    await _db.commit()


async def get_by_ticket_code(code: str) -> Optional[dict]:
    cur = await _db.execute("SELECT * FROM registrations WHERE ticket_code=?", (code,))
    row = await cur.fetchone()
    return dict(row) if row else None


async def check_in(user_id: int, arrived: int) -> None:
    await _db.execute(
        "UPDATE registrations SET checked_in_at=?, arrived_count=?, updated_at=? WHERE user_id=?",
        (_now(), arrived, _now(), user_id),
    )
    await _db.commit()


async def checkin_totals() -> tuple[int, int]:
    """(заказов отмечено, гостей пришло)."""
    cur = await _db.execute(
        "SELECT COUNT(*) AS orders, COALESCE(SUM(arrived_count),0) AS guests "
        "FROM registrations WHERE checked_in_at IS NOT NULL"
    )
    row = await cur.fetchone()
    return int(row["orders"]), int(row["guests"])


# ---------- Номера розыгрыша ----------

async def assign_raffle_numbers(qty: int) -> list[int]:
    """Атомарно резервирует qty следующих номеров розыгрыша."""
    cur = await _db.execute("SELECT value FROM meta WHERE key='raffle_counter'")
    row = await cur.fetchone()
    current = int(row["value"]) if row else 0
    numbers = list(range(current + 1, current + 1 + qty))
    await _db.execute(
        "UPDATE meta SET value=? WHERE key='raffle_counter'", (str(current + qty),)
    )
    await _db.commit()
    return numbers


# ---------- Места ----------

async def seats_taken() -> int:
    placeholders = ",".join("?" for _ in SEAT_STATUSES)
    cur = await _db.execute(
        f"SELECT COALESCE(SUM(qty), 0) AS s FROM registrations WHERE status IN ({placeholders})",
        SEAT_STATUSES,
    )
    row = await cur.fetchone()
    return int(row["s"])


# ---------- Выборки / статистика ----------

async def list_all_user_ids() -> list[int]:
    cur = await _db.execute("SELECT user_id FROM registrations")
    return [r["user_id"] for r in await cur.fetchall()]


async def list_user_ids_by_statuses(statuses: tuple[str, ...]) -> list[int]:
    placeholders = ",".join("?" for _ in statuses)
    cur = await _db.execute(
        f"SELECT user_id FROM registrations WHERE status IN ({placeholders})", statuses
    )
    return [r["user_id"] for r in await cur.fetchall()]


async def breakdown_by_method(status: str) -> list[tuple[str, int]]:
    """[(method, sum_qty), ...] для заданного статуса — для оценки выручки."""
    cur = await _db.execute(
        "SELECT payment_method, COALESCE(SUM(qty),0) AS q FROM registrations "
        "WHERE status=? GROUP BY payment_method",
        (status,),
    )
    return [(r["payment_method"], r["q"]) for r in await cur.fetchall()]


async def count_by_status() -> dict[str, int]:
    cur = await _db.execute(
        "SELECT status, COUNT(*) AS c, COALESCE(SUM(qty),0) AS q FROM registrations GROUP BY status"
    )
    out = {}
    for r in await cur.fetchall():
        out[r["status"]] = {"count": r["c"], "qty": r["q"]}
    return out


# ---------- Рассылки (флаги) ----------

async def is_broadcast_sent(key: str) -> bool:
    cur = await _db.execute("SELECT 1 FROM broadcasts_log WHERE key=?", (key,))
    return await cur.fetchone() is not None


async def mark_broadcast_sent(key: str) -> None:
    await _db.execute(
        "INSERT OR IGNORE INTO broadcasts_log(key, sent_at) VALUES(?, ?)", (key, _now())
    )
    await _db.commit()


# ---------- Посты ----------

async def add_post(file_path: Optional[str], caption: str) -> int:
    cur = await _db.execute(
        "INSERT INTO posts(file_path, caption, published, created_at) VALUES(?, ?, 0, ?)",
        (file_path, caption, _now()),
    )
    await _db.commit()
    return cur.lastrowid


async def get_next_post() -> Optional[dict]:
    cur = await _db.execute(
        "SELECT * FROM posts WHERE published=0 ORDER BY id LIMIT 1"
    )
    row = await cur.fetchone()
    return dict(row) if row else None


async def mark_post_published(post_id: int) -> None:
    await _db.execute("UPDATE posts SET published=1 WHERE id=?", (post_id,))
    await _db.commit()


async def count_unpublished_posts() -> int:
    cur = await _db.execute("SELECT COUNT(*) AS c FROM posts WHERE published=0")
    row = await cur.fetchone()
    return int(row["c"])


async def get_all_registrations(include_new: bool = False) -> list[dict]:
    """Записи, отсортированные по дате создания.

    include_new=False — без «просто зашёл» (для /guests).
    include_new=True — вообще все (для Google Таблицы).
    """
    if include_new:
        cur = await _db.execute("SELECT * FROM registrations ORDER BY created_at")
    else:
        cur = await _db.execute(
            "SELECT * FROM registrations WHERE status != ? ORDER BY created_at",
            (STATUS_NEW,),
        )
    return [dict(r) for r in await cur.fetchall()]

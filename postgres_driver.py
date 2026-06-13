"""Слой доступа к PostgreSQL.

Здесь сосредоточена вся «механика» работы с БД:
- подключение по параметрам из окружения;
- низкоуровневое выполнение SQL (execute / fetchone / fetchall);
- создание отдельной базы данных (CREATE DATABASE);
- создание схемы таблиц (DDL) для приложения бронирования.

Бизнес-логика и конкретные CRUD-запросы живут в backend.py — этот модуль
ничего не знает о правилах бронирования.
"""

import psycopg2
from psycopg2 import sql


# ---------------------------------------------------------------------------
# DDL: определения таблиц приложения.
#
# Имена таблиц намеренно отличаются от общеупотребимых (customers /
# restaurant_tables / bookings), чтобы не конфликтовать с возможными чужими
# таблицами `users` / `tables` в той же базе.
# ---------------------------------------------------------------------------

DDL_CUSTOMERS = """
CREATE TABLE IF NOT EXISTS customers (
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL,
    email      TEXT NOT NULL,
    phone      TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
"""

DDL_TABLES = """
CREATE TABLE IF NOT EXISTS restaurant_tables (
    id        SERIAL PRIMARY KEY,
    number    INTEGER NOT NULL UNIQUE,
    capacity  INTEGER NOT NULL DEFAULT 2 CHECK (capacity > 0),
    location  TEXT NOT NULL DEFAULT 'в центре',
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);
"""

DDL_BOOKINGS = """
CREATE TABLE IF NOT EXISTS bookings (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    table_id   INTEGER NOT NULL REFERENCES restaurant_tables(id) ON DELETE RESTRICT,
    starts_at  TIMESTAMP NOT NULL,
    ends_at    TIMESTAMP NOT NULL,
    comment    TEXT,
    status     TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT booking_time_valid CHECK (ends_at > starts_at)
);
"""

# Индекс ускоряет проверку доступности столика на интервал.
DDL_BOOKINGS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_bookings_table_time
    ON bookings (table_id, starts_at, ends_at);
"""


class PostgresDriver:
    """Тонкая обёртка над psycopg2-соединением с удобными хелперами."""

    def __init__(self, host, port, dbname, user, password):
        self.conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
        )

    # -- управление соединением ---------------------------------------------

    def close(self):
        if self.conn and not self.conn.closed:
            self.conn.close()

    # -- низкоуровневое выполнение SQL ---------------------------------------

    def execute(self, query, params=None):
        """Выполнить запрос без возврата строк (INSERT/UPDATE/DELETE/DDL).

        Если запрос содержит RETURNING, вернётся первое значение первой строки.
        Транзакция фиксируется автоматически.
        """
        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute(query, params)
                if cur.description is not None:
                    row = cur.fetchone()
                    return row[0] if row else None
                return None

    def fetchone(self, query, params=None):
        """Выполнить SELECT и вернуть одну строку (кортеж) или None."""
        with self.conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()

    def fetchall(self, query, params=None):
        """Выполнить SELECT и вернуть список строк (кортежей)."""
        with self.conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()

    # -- схема ---------------------------------------------------------------

    def create_tables(self):
        """Создать все таблицы приложения, если их ещё нет."""
        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute(DDL_CUSTOMERS)
                cur.execute(DDL_TABLES)
                cur.execute(DDL_BOOKINGS)
                cur.execute(DDL_BOOKINGS_INDEX)


# ---------------------------------------------------------------------------
# Вспомогательные функции уровня сервера (не требуют целевой базы).
# ---------------------------------------------------------------------------

def test_connection(host, port, dbname, user, password) -> None:
    """Проверить, что подключение к указанной базе возможно.

    Бросает исключение psycopg2, если подключиться нельзя.
    """
    conn = psycopg2.connect(
        host=host, port=port, dbname=dbname, user=user, password=password
    )
    conn.close()


def database_exists(host, port, user, password, dbname) -> bool:
    """Проверить, существует ли база данных с таким именем."""
    conn = psycopg2.connect(
        host=host, port=port, dbname="postgres", user=user, password=password
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (dbname,))
            return cur.fetchone() is not None
    finally:
        conn.close()


def create_database(host, port, user, password, dbname) -> None:
    """Создать новую базу данных.

    Подключается к служебной базе `postgres` (она есть всегда) и выполняет
    CREATE DATABASE. Имя базы подставляется безопасно через psycopg2.sql.
    CREATE DATABASE нельзя выполнять внутри транзакции, поэтому включаем
    autocommit.
    """
    conn = psycopg2.connect(
        host=host, port=port, dbname="postgres", user=user, password=password
    )
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname))
            )
    finally:
        conn.close()

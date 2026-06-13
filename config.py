"""Конфигурация подключения к БД и консольный мастер первичной настройки.

При первом запуске (когда .env отсутствует или подключение не работает)
мастер в терминале спрашивает параметры подключения, при необходимости
создаёт базу данных и сохраняет всё в .env.
"""

import os

from dotenv import load_dotenv

import postgres_driver as pg

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

DEFAULT_HOST = "localhost"
DEFAULT_PORT = "5432"
DEFAULT_USER = "postgres"


def load_config():
    """Загрузить параметры подключения из .env.

    Возвращает словарь с ключами host, port, dbname, user, password
    либо None, если .env отсутствует или не содержит нужных полей.
    """
    if not os.path.exists(ENV_PATH):
        return None
    load_dotenv(ENV_PATH, override=True)
    cfg = {
        "host": os.getenv("DB_HOST"),
        "port": os.getenv("DB_PORT"),
        "dbname": os.getenv("DB_NAME"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
    }
    if not cfg["dbname"] or not cfg["user"]:
        return None
    return cfg


def save_config(cfg) -> None:
    """Сохранить параметры подключения в .env."""
    lines = [
        f"DB_HOST={cfg['host']}",
        f"DB_PORT={cfg['port']}",
        f"DB_NAME={cfg['dbname']}",
        f"DB_USER={cfg['user']}",
        f"DB_PASSWORD={cfg['password']}",
        "",
    ]
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _prompt(text, default=None):
    """Запросить ввод с необязательным значением по умолчанию."""
    suffix = f" [{default}]" if default else ""
    value = input(f"{text}{suffix}: ").strip()
    return value or (default or "")


def _yes(answer: str) -> bool:
    return answer.lower().startswith(("д", "y"))


def run_setup_wizard():
    """Консольный мастер настройки подключения.

    Возвращает рабочий словарь конфигурации (и сохраняет его в .env).

    По умолчанию спрашивает только имя базы и пароль — хост, порт и
    пользователь берутся стандартные (localhost:5432, postgres). Расширенные
    параметры запрашиваются только если обычное подключение не удалось
    (нестандартная установка PostgreSQL).
    """
    print("\n=== Настройка подключения к PostgreSQL ===")
    print("Файл .env не найден — зададим пару вопросов.")
    print("Обычно нужно знать только пароль пользователя postgres,")
    print("который вы задали при установке PostgreSQL.\n")

    # Значения по умолчанию для стандартной установки.
    host = DEFAULT_HOST
    port = DEFAULT_PORT
    user = DEFAULT_USER
    advanced = False  # включается, если стандартное подключение не сработало

    while True:
        print("Что сделать?")
        print("  1 — создать новую базу данных")
        print("  2 — подключиться к существующей базе")
        choice = _prompt("Ваш выбор (1/2)", "1")

        dbname = _prompt("Имя базы данных", "booking_db")
        password = _prompt("Пароль пользователя postgres", "")

        if advanced:
            # Нестандартная установка: уточняем хост, порт и пользователя.
            print("\nДополнительные параметры (Enter — оставить значение по умолчанию):")
            host = _prompt("Хост", DEFAULT_HOST)
            port = _prompt("Порт", DEFAULT_PORT)
            user = _prompt("Пользователь PostgreSQL", DEFAULT_USER)

        cfg = {
            "host": host,
            "port": port,
            "dbname": dbname,
            "user": user,
            "password": password,
        }

        try:
            if choice == "1":
                if pg.database_exists(host, port, user, password, dbname):
                    print(f"\nБаза «{dbname}» уже существует — просто подключусь к ней.")
                else:
                    pg.create_database(host, port, user, password, dbname)
                    print(f"\nБаза «{dbname}» создана.")
            # Проверяем, что к целевой базе можно подключиться.
            pg.test_connection(host, port, dbname, user, password)
        except Exception as exc:  # noqa: BLE001 — показываем причину пользователю
            print(f"\n[Ошибка] Не удалось подключиться: {exc}\n")
            print("Возможные причины: не запущен сервер PostgreSQL, неверный")
            print("пароль, либо нестандартный порт/пользователь.")
            if not advanced and _yes(_prompt(
                "Указать хост, порт и пользователя вручную? (д/н)", "д")):
                advanced = True
                continue
            if not _yes(_prompt("Попробовать снова? (д/н)", "д")):
                raise SystemExit("Настройка прервана пользователем.")
            continue

        save_config(cfg)
        print(f"Параметры сохранены в {ENV_PATH}\n")
        return cfg


def ensure_config():
    """Гарантировать рабочую конфигурацию подключения.

    Если .env есть и подключение проходит — возвращает конфиг.
    Иначе запускает мастер настройки.
    """
    cfg = load_config()
    if cfg:
        try:
            pg.test_connection(**cfg)
            return cfg
        except Exception as exc:  # noqa: BLE001
            print(f"[Предупреждение] Сохранённое подключение не работает: {exc}")
            print("Запускаю мастер настройки заново.\n")
    return run_setup_wizard()

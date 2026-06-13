"""Бизнес-логика и CRUD-операции системы бронирования.

Слой между интерфейсом (app.py) и доступом к БД (postgres_driver.py).
Здесь живут:
- CRUD для пользователей, столиков и броней;
- проверка доступности столика (check_table_availability);
- запрет пересекающихся броней и валидация интервалов;
- запрет удаления пользователя/стола, у которого есть брони.
"""

from datetime import datetime
from typing import List, Optional

from models import Booking, Table, User


class ValidationError(Exception):
    """Ошибка бизнес-валидации — её текст можно показать пользователю."""


class Backend:
    def __init__(self, driver):
        self.db = driver

    # =======================================================================
    # ПОЛЬЗОВАТЕЛИ (клиенты)
    # =======================================================================

    def create_user(self, name: str, email: str, phone: Optional[str] = None) -> int:
        name = (name or "").strip()
        email = (email or "").strip()
        phone = (phone or "").strip() or None
        if not name:
            raise ValidationError("Имя клиента не может быть пустым.")
        if not email or "@" not in email:
            raise ValidationError("Укажите корректный email (должен содержать «@»).")
        return self.db.execute(
            "INSERT INTO customers (name, email, phone) VALUES (%s, %s, %s) "
            "RETURNING id;",
            (name, email, phone),
        )

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        row = self.db.fetchone(
            "SELECT id, name, email, phone, created_at FROM customers "
            "WHERE id = %s;",
            (user_id,),
        )
        return User.from_row(row)

    def get_all_users(self) -> List[User]:
        rows = self.db.fetchall(
            "SELECT id, name, email, phone, created_at FROM customers "
            "ORDER BY id;"
        )
        return [User.from_row(r) for r in rows]

    def update_user(self, user_id: int, name: str, email: str,
                    phone: Optional[str] = None) -> None:
        name = (name or "").strip()
        email = (email or "").strip()
        phone = (phone or "").strip() or None
        if not name:
            raise ValidationError("Имя клиента не может быть пустым.")
        if not email or "@" not in email:
            raise ValidationError("Укажите корректный email (должен содержать «@»).")
        self.db.execute(
            "UPDATE customers SET name = %s, email = %s, phone = %s WHERE id = %s;",
            (name, email, phone, user_id),
        )

    def delete_user(self, user_id: int) -> None:
        count = self.db.fetchone(
            "SELECT COUNT(*) FROM bookings WHERE user_id = %s;", (user_id,)
        )[0]
        if count > 0:
            raise ValidationError(
                f"Нельзя удалить клиента: у него есть брони ({count} шт.). "
                "Сначала удалите его брони."
            )
        self.db.execute("DELETE FROM customers WHERE id = %s;", (user_id,))

    # =======================================================================
    # СТОЛИКИ
    # =======================================================================

    def create_table(self, number: int, capacity: int = 2,
                     location: str = "в центре", is_active: bool = True) -> int:
        if number is None or int(number) <= 0:
            raise ValidationError("Номер стола должен быть положительным числом.")
        if int(capacity) <= 0:
            raise ValidationError("Вместимость стола должна быть больше нуля.")
        exists = self.db.fetchone(
            "SELECT 1 FROM restaurant_tables WHERE number = %s;", (number,)
        )
        if exists:
            raise ValidationError(f"Стол с номером {number} уже существует.")
        return self.db.execute(
            "INSERT INTO restaurant_tables (number, capacity, location, is_active) "
            "VALUES (%s, %s, %s, %s) RETURNING id;",
            (int(number), int(capacity), location, bool(is_active)),
        )

    def get_table_by_id(self, table_id: int) -> Optional[Table]:
        row = self.db.fetchone(
            "SELECT id, number, capacity, location, is_active "
            "FROM restaurant_tables WHERE id = %s;",
            (table_id,),
        )
        return Table.from_row(row)

    def get_all_tables(self) -> List[Table]:
        rows = self.db.fetchall(
            "SELECT id, number, capacity, location, is_active "
            "FROM restaurant_tables ORDER BY number;"
        )
        return [Table.from_row(r) for r in rows]

    def count_tables(self) -> int:
        return self.db.fetchone("SELECT COUNT(*) FROM restaurant_tables;")[0]

    def update_table(self, table_id: int, number: int, capacity: int,
                     location: str, is_active: bool) -> None:
        if number is None or int(number) <= 0:
            raise ValidationError("Номер стола должен быть положительным числом.")
        if int(capacity) <= 0:
            raise ValidationError("Вместимость стола должна быть больше нуля.")
        clash = self.db.fetchone(
            "SELECT 1 FROM restaurant_tables WHERE number = %s AND id <> %s;",
            (number, table_id),
        )
        if clash:
            raise ValidationError(f"Стол с номером {number} уже существует.")
        self.db.execute(
            "UPDATE restaurant_tables SET number = %s, capacity = %s, "
            "location = %s, is_active = %s WHERE id = %s;",
            (int(number), int(capacity), location, bool(is_active), table_id),
        )

    def delete_table(self, table_id: int) -> None:
        count = self.db.fetchone(
            "SELECT COUNT(*) FROM bookings WHERE table_id = %s;", (table_id,)
        )[0]
        if count > 0:
            raise ValidationError(
                f"Нельзя удалить стол: на него есть брони ({count} шт.). "
                "Сначала удалите эти брони."
            )
        self.db.execute("DELETE FROM restaurant_tables WHERE id = %s;", (table_id,))

    def set_table_count(self, target_count: int) -> None:
        """Привести количество столов к target_count.

        Используется на странице настроек и при первом запуске.
        Недостающие столы создаются с номерами по порядку; лишние удаляются
        (но только если на них нет броней — иначе бросается ошибка).
        """
        if target_count < 0:
            raise ValidationError("Количество столов не может быть отрицательным.")
        tables = self.get_all_tables()
        current = len(tables)
        if target_count > current:
            existing_numbers = {t.number for t in tables}
            next_number = 1
            for _ in range(target_count - current):
                while next_number in existing_numbers:
                    next_number += 1
                self.create_table(number=next_number)
                existing_numbers.add(next_number)
        elif target_count < current:
            # Удаляем столы с самыми большими номерами.
            for table in sorted(tables, key=lambda t: t.number, reverse=True)[
                : current - target_count
            ]:
                self.delete_table(table.id)

    # =======================================================================
    # ПРОВЕРКА ДОСТУПНОСТИ И ПЕРЕСЕЧЕНИЙ
    # =======================================================================

    def check_table_availability(
        self,
        table_id: int,
        starts_at: datetime,
        ends_at: datetime,
        exclude_booking_id: Optional[int] = None,
    ) -> bool:
        """Свободен ли столик на интервал [starts_at, ends_at)?

        Возвращает True, если пересекающихся активных броней нет.

        Логика пересечения интервалов (строгие неравенства):
        две брони пересекаются, если  new_start < existing_end
        И  new_end > existing_start.
        Благодаря строгим знакам соседние брони впритык (одна заканчивается
        ровно когда начинается другая) пересечением НЕ считаются.

        exclude_booking_id позволяет при обновлении не сравнивать бронь саму
        с собой.
        """
        if ends_at <= starts_at:
            raise ValidationError("Время окончания должно быть позже времени начала.")

        query = (
            "SELECT COUNT(*) FROM bookings "
            "WHERE table_id = %s "
            "  AND status = 'active' "
            "  AND starts_at < %s "  # existing_start < new_end
            "  AND ends_at > %s"     # existing_end   > new_start
        )
        params = [table_id, ends_at, starts_at]
        if exclude_booking_id is not None:
            query += " AND id <> %s"
            params.append(exclude_booking_id)

        overlapping = self.db.fetchone(query, tuple(params))[0]
        return overlapping == 0

    def get_conflicting_bookings(
        self,
        table_id: int,
        starts_at: datetime,
        ends_at: datetime,
        exclude_booking_id: Optional[int] = None,
    ) -> List[Booking]:
        """Вернуть список активных броней, мешающих заданному интервалу."""
        query = (
            "SELECT id, user_id, table_id, starts_at, ends_at, comment, "
            "status, created_at FROM bookings "
            "WHERE table_id = %s AND status = 'active' "
            "  AND starts_at < %s AND ends_at > %s"
        )
        params = [table_id, ends_at, starts_at]
        if exclude_booking_id is not None:
            query += " AND id <> %s"
            params.append(exclude_booking_id)
        rows = self.db.fetchall(query, tuple(params))
        return [Booking.from_row(r) for r in rows]

    def get_busy_until(self, table_id: int, at: datetime) -> Optional[datetime]:
        """До какого времени стол занят в момент `at`?

        Если в момент `at` стол свободен — возвращает None.
        Если занят — возвращает время окончания текущей (покрывающей `at`)
        брони. Используется для подсказки «занято до 19:15».
        """
        row = self.db.fetchone(
            "SELECT ends_at FROM bookings "
            "WHERE table_id = %s AND status = 'active' "
            "  AND starts_at <= %s AND ends_at > %s "
            "ORDER BY ends_at DESC LIMIT 1;",
            (table_id, at, at),
        )
        return row[0] if row else None

    # =======================================================================
    # БРОНИРОВАНИЯ
    # =======================================================================

    def _validate_booking_input(self, user_id, table_id, starts_at, ends_at):
        if not user_id:
            raise ValidationError("Не выбран клиент.")
        if not table_id:
            raise ValidationError("Не выбран стол.")
        if not isinstance(starts_at, datetime) or not isinstance(ends_at, datetime):
            raise ValidationError("Некорректные дата и время брони.")
        if ends_at <= starts_at:
            raise ValidationError("Время окончания должно быть позже времени начала.")

    def create_booking(
        self,
        user_id: int,
        table_id: int,
        starts_at: datetime,
        ends_at: datetime,
        comment: Optional[str] = None,
    ) -> int:
        self._validate_booking_input(user_id, table_id, starts_at, ends_at)
        if not self.check_table_availability(table_id, starts_at, ends_at):
            conflicts = self.get_conflicting_bookings(table_id, starts_at, ends_at)
            raise ValidationError(self._conflict_message(conflicts))
        comment = (comment or "").strip() or None
        return self.db.execute(
            "INSERT INTO bookings (user_id, table_id, starts_at, ends_at, comment) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id;",
            (user_id, table_id, starts_at, ends_at, comment),
        )

    def get_booking_by_id(self, booking_id: int) -> Optional[Booking]:
        row = self.db.fetchone(
            "SELECT id, user_id, table_id, starts_at, ends_at, comment, "
            "status, created_at FROM bookings WHERE id = %s;",
            (booking_id,),
        )
        return Booking.from_row(row)

    def get_all_bookings(self) -> List[dict]:
        """Все брони в читаемом виде (с именем клиента и номером стола).

        Возвращает список словарей — удобно для отображения в таблице.
        """
        rows = self.db.fetchall(
            "SELECT b.id, c.name, t.number, b.starts_at, b.ends_at, "
            "       b.comment, b.status, b.user_id, b.table_id "
            "FROM bookings b "
            "JOIN customers c ON c.id = b.user_id "
            "JOIN restaurant_tables t ON t.id = b.table_id "
            "ORDER BY b.starts_at DESC, b.id DESC;"
        )
        result = []
        for r in rows:
            result.append(
                {
                    "id": r[0],
                    "user_name": r[1],
                    "table_number": r[2],
                    "starts_at": r[3],
                    "ends_at": r[4],
                    "comment": r[5],
                    "status": r[6],
                    "user_id": r[7],
                    "table_id": r[8],
                }
            )
        return result

    def update_booking(
        self,
        booking_id: int,
        user_id: int,
        table_id: int,
        starts_at: datetime,
        ends_at: datetime,
        comment: Optional[str] = None,
    ) -> None:
        self._validate_booking_input(user_id, table_id, starts_at, ends_at)
        # При обновлении исключаем саму бронь из проверки пересечений.
        if not self.check_table_availability(
            table_id, starts_at, ends_at, exclude_booking_id=booking_id
        ):
            conflicts = self.get_conflicting_bookings(
                table_id, starts_at, ends_at, exclude_booking_id=booking_id
            )
            raise ValidationError(self._conflict_message(conflicts))
        comment = (comment or "").strip() or None
        self.db.execute(
            "UPDATE bookings SET user_id = %s, table_id = %s, starts_at = %s, "
            "ends_at = %s, comment = %s WHERE id = %s;",
            (user_id, table_id, starts_at, ends_at, comment, booking_id),
        )

    def delete_booking(self, booking_id: int) -> None:
        self.db.execute("DELETE FROM bookings WHERE id = %s;", (booking_id,))

    def _conflict_message(self, conflicts: List[Booking]) -> str:
        if not conflicts:
            return "Столик занят на выбранный интервал."
        parts = []
        for b in conflicts:
            parts.append(
                f"{b.starts_at.strftime('%d.%m %H:%M')}–"
                f"{b.ends_at.strftime('%H:%M')}"
            )
        return "Столик уже занят на это время: " + "; ".join(parts) + "."

    # =======================================================================
    # ТЕСТОВЫЕ ДАННЫЕ
    # =======================================================================

    def create_sample_data(self) -> str:
        """Создать демонстрационные данные: 3 клиента и 2 брони.

        Предполагается, что столы уже созданы (при первом запуске).
        Возвращает текстовое описание результата для показа пользователю.
        """
        tables = self.get_all_tables()
        if not tables:
            raise ValidationError(
                "Нет ни одного стола — сначала создайте столы в настройках."
            )

        u1 = self.create_user("Иван Петров", "ivan@example.com", "+7 900 111-22-33")
        u2 = self.create_user("Мария Сидорова", "maria@example.com", "+7 900 222-33-44")
        u3 = self.create_user("Алексей Кузнецов", "alex@example.com", None)

        # Две непересекающиеся брони на сегодня.
        today = datetime.now().replace(minute=0, second=0, microsecond=0)
        t1 = tables[0].id
        t2 = tables[1].id if len(tables) > 1 else tables[0].id

        b1_start = today.replace(hour=18)
        b1_end = today.replace(hour=20)
        b2_start = today.replace(hour=19)
        b2_end = today.replace(hour=21)

        self.create_booking(u1, t1, b1_start, b1_end, "Ужин на двоих")
        self.create_booking(u2, t2, b2_start, b2_end, "День рождения")

        _ = u3  # третий клиент остаётся без брони — для демонстрации справочника
        return (
            "Созданы тестовые данные: 3 клиента и 2 брони.\n"
            f"• Стол {tables[0].number}: 18:00–20:00 (Иван Петров)\n"
            f"• Стол {(tables[1].number if len(tables) > 1 else tables[0].number)}: "
            "19:00–21:00 (Мария Сидорова)"
        )

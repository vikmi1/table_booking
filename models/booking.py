"""Модель бронирования.

Время хранится двумя полными метками времени (starts_at / ends_at) — так проще
и надёжнее проверять пересечения интервалов.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


# Возможные статусы брони.
STATUS_ACTIVE = "active"
STATUS_CANCELLED = "cancelled"
STATUSES = [STATUS_ACTIVE, STATUS_CANCELLED]


@dataclass
class Booking:
    id: Optional[int] = None
    user_id: int = 0
    table_id: int = 0
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    comment: Optional[str] = None
    status: str = STATUS_ACTIVE
    created_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row) -> Optional["Booking"]:
        """Создать объект из строки результата SQL-запроса.

        Ожидается порядок колонок:
        id, user_id, table_id, starts_at, ends_at, comment, status, created_at.
        """
        if row is None:
            return None
        return cls(
            id=row[0],
            user_id=row[1],
            table_id=row[2],
            starts_at=row[3],
            ends_at=row[4],
            comment=row[5],
            status=row[6],
            created_at=row[7],
        )

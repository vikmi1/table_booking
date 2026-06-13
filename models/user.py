"""Модель пользователя (клиента ресторана).

В этой системе User — это справочник гостей, на которых оформляются брони.
Никакой авторизации/паролей нет: при бронировании клиент выбирается из списка
или заводится новый.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class User:
    id: Optional[int] = None
    name: str = ""
    email: str = ""
    phone: Optional[str] = None
    created_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row) -> Optional["User"]:
        """Создать объект из строки результата SQL-запроса.

        Ожидается порядок колонок: id, name, email, phone, created_at.
        """
        if row is None:
            return None
        return cls(
            id=row[0],
            name=row[1],
            email=row[2],
            phone=row[3],
            created_at=row[4],
        )

    def label(self) -> str:
        """Короткая подпись для выпадающих списков в интерфейсе."""
        return f"#{self.id} — {self.name}"

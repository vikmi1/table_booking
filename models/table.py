"""Модель столика."""

from dataclasses import dataclass
from typing import Optional


# Допустимые варианты расположения столика (используются в выпадающих списках).
LOCATIONS = ["у окна", "в центре", "у стены", "на террасе", "в углу"]


@dataclass
class Table:
    id: Optional[int] = None
    number: int = 0
    capacity: int = 2
    location: str = "в центре"
    is_active: bool = True

    @classmethod
    def from_row(cls, row) -> Optional["Table"]:
        """Создать объект из строки результата SQL-запроса.

        Ожидается порядок колонок: id, number, capacity, location, is_active.
        """
        if row is None:
            return None
        return cls(
            id=row[0],
            number=row[1],
            capacity=row[2],
            location=row[3],
            is_active=row[4],
        )

    def caption(self) -> str:
        """Подпись под столом на карте зала: «Стол 3 · 4 места · у окна»."""
        return f"Стол {self.number} · {self.capacity} мест · {self.location}"

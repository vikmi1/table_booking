"""Точка входа и графический интерфейс системы бронирования (Tkinter).

Запуск:
    python app.py
или двойным кликом по start.cmd (Windows) / start.command (macOS).

При первом запуске в терминале появится мастер настройки подключения к БД,
затем вопрос о количестве столов. После этого откроется окно приложения.
"""

import sys
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import messagebox, ttk

from backend import Backend, ValidationError
from config import ensure_config
from models.table import LOCATIONS
from postgres_driver import PostgresDriver

DATE_FMT = "%Y-%m-%d"
TIME_FMT = "%H:%M"

# Цвета карты зала.
COLOR_FREE = "#2e9e5b"      # свободен — зелёный
COLOR_BUSY = "#d64545"      # занят — красный
COLOR_INACTIVE = "#9aa0a6"  # неактивный стол — серый
COLOR_TEXT = "#ffffff"

# Шрифт интерфейса подбираем под платформу: на Windows есть Segoe UI,
# на macOS — Helvetica, на остальных системах — общий запасной вариант.
if sys.platform.startswith("win"):
    UI_FONT = "Segoe UI"
elif sys.platform == "darwin":
    UI_FONT = "Helvetica"
else:
    UI_FONT = "DejaVu Sans"


# ---------------------------------------------------------------------------
# Помощники для дат/времени.
# ---------------------------------------------------------------------------

def parse_datetime(date_str: str, time_str: str) -> datetime:
    """Собрать datetime из строк даты (ГГГГ-ММ-ДД) и времени (ЧЧ:ММ)."""
    date_str = (date_str or "").strip()
    time_str = (time_str or "").strip()
    try:
        d = datetime.strptime(date_str, DATE_FMT).date()
    except ValueError:
        raise ValidationError(f"Некорректная дата: «{date_str}». Формат: ГГГГ-ММ-ДД.")
    try:
        t = datetime.strptime(time_str, TIME_FMT).time()
    except ValueError:
        raise ValidationError(f"Некорректное время: «{time_str}». Формат: ЧЧ:ММ.")
    return datetime.combine(d, t)


def fmt_dt(dt: datetime) -> str:
    return dt.strftime("%d.%m.%Y %H:%M") if dt else ""


# ---------------------------------------------------------------------------
# Первичный консольный опрос количества столов.
# ---------------------------------------------------------------------------

def prompt_initial_tables(backend: Backend) -> None:
    print("\n=== Первичная настройка зала ===")
    print("В базе пока нет ни одного стола.")
    while True:
        raw = input("Сколько столов создать? (1–10): ").strip()
        try:
            n = int(raw)
        except ValueError:
            print("Введите число от 1 до 10.")
            continue
        if 1 <= n <= 10:
            backend.set_table_count(n)
            print(f"Создано столов: {n}.\n")
            return
        print("Число должно быть от 1 до 10.")


# ---------------------------------------------------------------------------
# Главное окно.
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self, backend: Backend):
        super().__init__()
        self.backend = backend
        self.title("Система бронирования столиков")
        self.geometry("960x640")
        self.minsize(820, 560)

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)

        self.map_tab = FloorMapTab(notebook, self)
        self.bookings_tab = BookingsTab(notebook, self)
        self.customers_tab = CustomersTab(notebook, self)
        self.tables_tab = TablesTab(notebook, self)

        notebook.add(self.map_tab, text="Карта зала")
        notebook.add(self.bookings_tab, text="Бронирования")
        notebook.add(self.customers_tab, text="Клиенты")
        notebook.add(self.tables_tab, text="Столы и настройки")

        notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _on_tab_changed(self, event):
        # Обновляем данные при переключении вкладок.
        self.map_tab.redraw()
        self.bookings_tab.refresh()
        self.customers_tab.refresh()
        self.tables_tab.refresh()

    def refresh_all(self):
        self.map_tab.redraw()
        self.bookings_tab.refresh()
        self.customers_tab.refresh()
        self.tables_tab.refresh()


# ---------------------------------------------------------------------------
# Вкладка «Карта зала».
# ---------------------------------------------------------------------------

class FloorMapTab(ttk.Frame):
    CELL_W = 150
    CELL_H = 100
    GAP = 18
    PAD = 18

    def __init__(self, parent, app: App):
        super().__init__(parent)
        self.app = app
        self.backend = app.backend

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=6, pady=8)

        now = datetime.now().replace(second=0, microsecond=0)
        ttk.Label(bar, text="Дата:").pack(side="left")
        self.date_var = tk.StringVar(value=now.strftime(DATE_FMT))
        ttk.Entry(bar, textvariable=self.date_var, width=12).pack(side="left", padx=(4, 12))

        ttk.Label(bar, text="Время:").pack(side="left")
        self.time_var = tk.StringVar(value=now.strftime(TIME_FMT))
        ttk.Entry(bar, textvariable=self.time_var, width=7).pack(side="left", padx=(4, 12))

        ttk.Button(bar, text="Показать занятость", command=self.redraw).pack(side="left")
        ttk.Label(
            bar,
            text="Зелёный — свободен, красный — занят. Клик по столу — забронировать.",
            foreground="#666",
        ).pack(side="left", padx=12)

        self.canvas = tk.Canvas(self, background="#f4f5f7", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=6, pady=6)
        self.canvas.bind("<Configure>", lambda e: self.redraw())

        self._rects = {}  # canvas rect id -> table

    def _current_moment(self):
        return parse_datetime(self.date_var.get(), self.time_var.get())

    def redraw(self):
        self.canvas.delete("all")
        self._rects.clear()
        try:
            moment = self._current_moment()
        except ValidationError:
            self.canvas.create_text(
                20, 20, anchor="nw", fill="#d64545",
                text="Проверьте формат даты (ГГГГ-ММ-ДД) и времени (ЧЧ:ММ).",
            )
            return

        tables = self.backend.get_all_tables()
        if not tables:
            self.canvas.create_text(
                20, 20, anchor="nw", fill="#666",
                text="Столов пока нет. Создайте их на вкладке «Столы и настройки».",
            )
            return

        width = max(self.canvas.winfo_width(), 1)
        per_row = max(1, (width - self.PAD) // (self.CELL_W + self.GAP))

        for idx, table in enumerate(tables):
            row, col = divmod(idx, per_row)
            x = self.PAD + col * (self.CELL_W + self.GAP)
            y = self.PAD + row * (self.CELL_H + self.GAP)
            self._draw_table(table, x, y, moment)

    def _draw_table(self, table, x, y, moment):
        busy_until = None
        if table.is_active:
            busy_until = self.backend.get_busy_until(table.id, moment)
            color = COLOR_BUSY if busy_until else COLOR_FREE
        else:
            color = COLOR_INACTIVE

        rect = self.canvas.create_rectangle(
            x, y, x + self.CELL_W, y + self.CELL_H,
            fill=color, outline="#33373b", width=2,
        )
        # Номер стола по центру.
        self.canvas.create_text(
            x + self.CELL_W / 2, y + 30,
            text=str(table.number), fill=COLOR_TEXT,
            font=(UI_FONT, 20, "bold"),
        )
        # Подпись.
        caption = f"{table.capacity} мест · {table.location}"
        if not table.is_active:
            caption = "неактивен · " + caption
        elif busy_until:
            caption += f"\nзанято до {busy_until.strftime(TIME_FMT)}"
        self.canvas.create_text(
            x + self.CELL_W / 2, y + 66,
            text=caption, fill=COLOR_TEXT,
            font=(UI_FONT, 9), justify="center", width=self.CELL_W - 12,
        )
        self._rects[rect] = table
        for item in (rect,):
            self.canvas.tag_bind(item, "<Button-1>",
                                 lambda e, t=table: self._on_table_click(t))

    def _on_table_click(self, table):
        if not table.is_active:
            messagebox.showinfo("Стол неактивен",
                                f"Стол {table.number} помечен как неактивный.")
            return
        date = self.date_var.get()
        BookingForm(self.app, prefill_table_id=table.id, prefill_date=date)


# ---------------------------------------------------------------------------
# Вкладка «Бронирования».
# ---------------------------------------------------------------------------

class BookingsTab(ttk.Frame):
    def __init__(self, parent, app: App):
        super().__init__(parent)
        self.app = app
        self.backend = app.backend

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=6, pady=8)
        ttk.Button(bar, text="Добавить", command=self.add).pack(side="left")
        ttk.Button(bar, text="Изменить", command=self.edit).pack(side="left", padx=4)
        ttk.Button(bar, text="Удалить", command=self.delete).pack(side="left")
        ttk.Button(bar, text="Проверить доступность",
                   command=self.check_availability).pack(side="left", padx=12)
        ttk.Button(bar, text="Обновить", command=self.refresh).pack(side="right")

        cols = ("id", "user", "table", "start", "end", "comment", "status")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=16)
        headers = {
            "id": ("ID", 50), "user": ("Клиент", 160), "table": ("Стол", 60),
            "start": ("Начало", 130), "end": ("Конец", 130),
            "comment": ("Комментарий", 180), "status": ("Статус", 80),
        }
        for c, (text, w) in headers.items():
            self.tree.heading(c, text=text)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=6, pady=6)
        self.tree.bind("<Double-1>", lambda e: self.edit())

        self._row_data = {}

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        self._row_data.clear()
        for b in self.backend.get_all_bookings():
            iid = self.tree.insert(
                "", "end",
                values=(
                    b["id"], b["user_name"], b["table_number"],
                    fmt_dt(b["starts_at"]), fmt_dt(b["ends_at"]),
                    b["comment"] or "", b["status"],
                ),
            )
            self._row_data[iid] = b

    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Нет выбора", "Сначала выберите бронь в списке.")
            return None
        return self._row_data[sel[0]]

    def add(self):
        BookingForm(self.app)

    def edit(self):
        data = self._selected()
        if data:
            BookingForm(self.app, booking_id=data["id"])

    def delete(self):
        data = self._selected()
        if not data:
            return
        if messagebox.askyesno("Удаление",
                               f"Удалить бронь #{data['id']}?"):
            self.backend.delete_booking(data["id"])
            self.app.refresh_all()

    def check_availability(self):
        AvailabilityDialog(self.app)


# ---------------------------------------------------------------------------
# Вкладка «Клиенты».
# ---------------------------------------------------------------------------

class CustomersTab(ttk.Frame):
    def __init__(self, parent, app: App):
        super().__init__(parent)
        self.app = app
        self.backend = app.backend

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=6, pady=8)
        ttk.Button(bar, text="Добавить", command=self.add).pack(side="left")
        ttk.Button(bar, text="Изменить", command=self.edit).pack(side="left", padx=4)
        ttk.Button(bar, text="Удалить", command=self.delete).pack(side="left")
        ttk.Button(bar, text="Обновить", command=self.refresh).pack(side="right")

        cols = ("id", "name", "email", "phone", "created")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=16)
        headers = {
            "id": ("ID", 50), "name": ("Имя", 200), "email": ("Email", 200),
            "phone": ("Телефон", 150), "created": ("Создан", 140),
        }
        for c, (text, w) in headers.items():
            self.tree.heading(c, text=text)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=6, pady=6)
        self.tree.bind("<Double-1>", lambda e: self.edit())

        self._row_data = {}

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        self._row_data.clear()
        for u in self.backend.get_all_users():
            iid = self.tree.insert(
                "", "end",
                values=(u.id, u.name, u.email, u.phone or "",
                        fmt_dt(u.created_at)),
            )
            self._row_data[iid] = u

    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Нет выбора", "Сначала выберите клиента в списке.")
            return None
        return self._row_data[sel[0]]

    def add(self):
        CustomerForm(self.app)

    def edit(self):
        u = self._selected()
        if u:
            CustomerForm(self.app, user=u)

    def delete(self):
        u = self._selected()
        if not u:
            return
        if not messagebox.askyesno("Удаление", f"Удалить клиента «{u.name}»?"):
            return
        try:
            self.backend.delete_user(u.id)
            self.app.refresh_all()
        except ValidationError as exc:
            messagebox.showwarning("Нельзя удалить", str(exc))


# ---------------------------------------------------------------------------
# Вкладка «Столы и настройки».
# ---------------------------------------------------------------------------

class TablesTab(ttk.Frame):
    def __init__(self, parent, app: App):
        super().__init__(parent)
        self.app = app
        self.backend = app.backend

        # Блок настроек количества столов и тестовых данных.
        settings = ttk.LabelFrame(self, text="Настройки зала")
        settings.pack(fill="x", padx=6, pady=8)

        ttk.Label(settings, text="Количество столов (1–10):").pack(
            side="left", padx=(8, 4), pady=8)
        self.count_var = tk.IntVar(value=self.backend.count_tables())
        self.count_spin = ttk.Spinbox(settings, from_=0, to=10, width=5,
                                      textvariable=self.count_var)
        self.count_spin.pack(side="left", pady=8)
        ttk.Button(settings, text="Применить",
                   command=self.apply_count).pack(side="left", padx=8)
        ttk.Button(settings, text="Создать тестовые данные",
                   command=self.create_sample).pack(side="left", padx=8)

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=6, pady=(4, 0))
        ttk.Button(bar, text="Добавить стол", command=self.add).pack(side="left")
        ttk.Button(bar, text="Изменить", command=self.edit).pack(side="left", padx=4)
        ttk.Button(bar, text="Удалить", command=self.delete).pack(side="left")
        ttk.Button(bar, text="Обновить", command=self.refresh).pack(side="right")

        cols = ("id", "number", "capacity", "location", "active")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=12)
        headers = {
            "id": ("ID", 50), "number": ("Номер", 80),
            "capacity": ("Мест", 80), "location": ("Расположение", 180),
            "active": ("Активен", 80),
        }
        for c, (text, w) in headers.items():
            self.tree.heading(c, text=text)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=6, pady=6)
        self.tree.bind("<Double-1>", lambda e: self.edit())

        self._row_data = {}

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        self._row_data.clear()
        for t in self.backend.get_all_tables():
            iid = self.tree.insert(
                "", "end",
                values=(t.id, t.number, t.capacity, t.location,
                        "да" if t.is_active else "нет"),
            )
            self._row_data[iid] = t
        # Синхронизируем спинбокс с реальным количеством.
        self.count_var.set(self.backend.count_tables())

    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Нет выбора", "Сначала выберите стол в списке.")
            return None
        return self._row_data[sel[0]]

    def apply_count(self):
        target = self.count_var.get()
        if target > 10:
            messagebox.showwarning("Слишком много",
                                   "Максимум 10 столов.")
            return
        try:
            self.backend.set_table_count(target)
            self.app.refresh_all()
        except ValidationError as exc:
            messagebox.showwarning("Не получилось", str(exc))

    def create_sample(self):
        if not messagebox.askyesno(
            "Тестовые данные",
            "Создать 3 клиентов и 2 брони для демонстрации?"
        ):
            return
        try:
            msg = self.backend.create_sample_data()
            self.app.refresh_all()
            messagebox.showinfo("Готово", msg)
        except ValidationError as exc:
            messagebox.showwarning("Не получилось", str(exc))

    def add(self):
        TableForm(self.app)

    def edit(self):
        t = self._selected()
        if t:
            TableForm(self.app, table=t)

    def delete(self):
        t = self._selected()
        if not t:
            return
        if not messagebox.askyesno("Удаление", f"Удалить стол {t.number}?"):
            return
        try:
            self.backend.delete_table(t.id)
            self.app.refresh_all()
        except ValidationError as exc:
            messagebox.showwarning("Нельзя удалить", str(exc))


# ---------------------------------------------------------------------------
# Диалоговые формы.
# ---------------------------------------------------------------------------

class CustomerForm(tk.Toplevel):
    def __init__(self, app: App, user=None):
        super().__init__(app)
        self.app = app
        self.backend = app.backend
        self.user = user
        self.title("Изменить клиента" if user else "Новый клиент")
        self.resizable(False, False)
        self.transient(app)
        self.grab_set()

        frm = ttk.Frame(self, padding=16)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Имя:").grid(row=0, column=0, sticky="w", pady=4)
        self.name_var = tk.StringVar(value=user.name if user else "")
        ttk.Entry(frm, textvariable=self.name_var, width=32).grid(row=0, column=1, pady=4)

        ttk.Label(frm, text="Email:").grid(row=1, column=0, sticky="w", pady=4)
        self.email_var = tk.StringVar(value=user.email if user else "")
        ttk.Entry(frm, textvariable=self.email_var, width=32).grid(row=1, column=1, pady=4)

        ttk.Label(frm, text="Телефон:").grid(row=2, column=0, sticky="w", pady=4)
        self.phone_var = tk.StringVar(value=(user.phone or "") if user else "")
        ttk.Entry(frm, textvariable=self.phone_var, width=32).grid(row=2, column=1, pady=4)

        btns = ttk.Frame(frm)
        btns.grid(row=3, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(btns, text="Сохранить", command=self.save).pack(side="left", padx=4)
        ttk.Button(btns, text="Отмена", command=self.destroy).pack(side="left", padx=4)

    def save(self):
        try:
            if self.user:
                self.backend.update_user(
                    self.user.id, self.name_var.get(),
                    self.email_var.get(), self.phone_var.get())
            else:
                self.backend.create_user(
                    self.name_var.get(), self.email_var.get(),
                    self.phone_var.get())
        except ValidationError as exc:
            messagebox.showwarning("Проверьте данные", str(exc), parent=self)
            return
        self.app.refresh_all()
        self.destroy()


class TableForm(tk.Toplevel):
    def __init__(self, app: App, table=None):
        super().__init__(app)
        self.app = app
        self.backend = app.backend
        self.table = table
        self.title("Изменить стол" if table else "Новый стол")
        self.resizable(False, False)
        self.transient(app)
        self.grab_set()

        frm = ttk.Frame(self, padding=16)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Номер:").grid(row=0, column=0, sticky="w", pady=4)
        self.number_var = tk.StringVar(value=str(table.number) if table else "")
        ttk.Entry(frm, textvariable=self.number_var, width=20).grid(row=0, column=1, pady=4)

        ttk.Label(frm, text="Мест:").grid(row=1, column=0, sticky="w", pady=4)
        self.cap_var = tk.StringVar(value=str(table.capacity) if table else "2")
        ttk.Spinbox(frm, from_=1, to=50, textvariable=self.cap_var, width=18).grid(
            row=1, column=1, pady=4)

        ttk.Label(frm, text="Расположение:").grid(row=2, column=0, sticky="w", pady=4)
        self.loc_var = tk.StringVar(value=table.location if table else LOCATIONS[0])
        ttk.Combobox(frm, textvariable=self.loc_var, values=LOCATIONS,
                     width=18, state="readonly").grid(row=2, column=1, pady=4)

        self.active_var = tk.BooleanVar(value=table.is_active if table else True)
        ttk.Checkbutton(frm, text="Активен", variable=self.active_var).grid(
            row=3, column=1, sticky="w", pady=4)

        btns = ttk.Frame(frm)
        btns.grid(row=4, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(btns, text="Сохранить", command=self.save).pack(side="left", padx=4)
        ttk.Button(btns, text="Отмена", command=self.destroy).pack(side="left", padx=4)

    def save(self):
        try:
            number = int(self.number_var.get())
            capacity = int(self.cap_var.get())
        except ValueError:
            messagebox.showwarning("Проверьте данные",
                                   "Номер и количество мест должны быть числами.",
                                   parent=self)
            return
        try:
            if self.table:
                self.backend.update_table(
                    self.table.id, number, capacity,
                    self.loc_var.get(), self.active_var.get())
            else:
                self.backend.create_table(
                    number, capacity, self.loc_var.get(),
                    self.active_var.get())
        except ValidationError as exc:
            messagebox.showwarning("Проверьте данные", str(exc), parent=self)
            return
        self.app.refresh_all()
        self.destroy()


class BookingForm(tk.Toplevel):
    def __init__(self, app: App, booking_id=None, prefill_table_id=None,
                 prefill_date=None):
        super().__init__(app)
        self.app = app
        self.backend = app.backend
        self.booking_id = booking_id
        self.title("Изменить бронь" if booking_id else "Новая бронь")
        self.resizable(False, False)
        self.transient(app)
        self.grab_set()

        existing = self.backend.get_booking_by_id(booking_id) if booking_id else None

        frm = ttk.Frame(self, padding=16)
        frm.pack(fill="both", expand=True)

        # Клиент.
        ttk.Label(frm, text="Клиент:").grid(row=0, column=0, sticky="w", pady=4)
        self.users = self.backend.get_all_users()
        self.user_map = {u.label(): u.id for u in self.users}
        self.user_var = tk.StringVar()
        self.user_cb = ttk.Combobox(frm, textvariable=self.user_var,
                                    values=list(self.user_map.keys()),
                                    width=30, state="readonly")
        self.user_cb.grid(row=0, column=1, pady=4)

        # Стол.
        ttk.Label(frm, text="Стол:").grid(row=1, column=0, sticky="w", pady=4)
        self.tables = self.backend.get_all_tables()
        self.table_map = {
            f"Стол {t.number} ({t.capacity} мест, {t.location})": t.id
            for t in self.tables
        }
        self.table_var = tk.StringVar()
        self.table_cb = ttk.Combobox(frm, textvariable=self.table_var,
                                     values=list(self.table_map.keys()),
                                     width=30, state="readonly")
        self.table_cb.grid(row=1, column=1, pady=4)

        # Дата и время.
        now = datetime.now().replace(second=0, microsecond=0)
        start_default = (now + timedelta(hours=1)).replace(minute=0)
        end_default = start_default + timedelta(hours=2)

        ttk.Label(frm, text="Дата (ГГГГ-ММ-ДД):").grid(row=2, column=0, sticky="w", pady=4)
        self.date_var = tk.StringVar(value=start_default.strftime(DATE_FMT))
        ttk.Entry(frm, textvariable=self.date_var, width=30).grid(row=2, column=1, pady=4)

        ttk.Label(frm, text="Начало (ЧЧ:ММ):").grid(row=3, column=0, sticky="w", pady=4)
        self.start_var = tk.StringVar(value=start_default.strftime(TIME_FMT))
        ttk.Entry(frm, textvariable=self.start_var, width=30).grid(row=3, column=1, pady=4)

        ttk.Label(frm, text="Конец (ЧЧ:ММ):").grid(row=4, column=0, sticky="w", pady=4)
        self.end_var = tk.StringVar(value=end_default.strftime(TIME_FMT))
        ttk.Entry(frm, textvariable=self.end_var, width=30).grid(row=4, column=1, pady=4)

        ttk.Label(frm, text="Комментарий:").grid(row=5, column=0, sticky="w", pady=4)
        self.comment_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.comment_var, width=30).grid(row=5, column=1, pady=4)

        btns = ttk.Frame(frm)
        btns.grid(row=6, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(btns, text="Сохранить", command=self.save).pack(side="left", padx=4)
        ttk.Button(btns, text="Отмена", command=self.destroy).pack(side="left", padx=4)

        # Предзаполнение.
        if existing:
            for label, uid in self.user_map.items():
                if uid == existing.user_id:
                    self.user_var.set(label)
            for label, tid in self.table_map.items():
                if tid == existing.table_id:
                    self.table_var.set(label)
            self.date_var.set(existing.starts_at.strftime(DATE_FMT))
            self.start_var.set(existing.starts_at.strftime(TIME_FMT))
            self.end_var.set(existing.ends_at.strftime(TIME_FMT))
            self.comment_var.set(existing.comment or "")
        else:
            if prefill_table_id is not None:
                for label, tid in self.table_map.items():
                    if tid == prefill_table_id:
                        self.table_var.set(label)
            if prefill_date:
                self.date_var.set(prefill_date)

    def _collect(self):
        user_id = self.user_map.get(self.user_var.get())
        table_id = self.table_map.get(self.table_var.get())
        starts_at = parse_datetime(self.date_var.get(), self.start_var.get())
        ends_at = parse_datetime(self.date_var.get(), self.end_var.get())
        return user_id, table_id, starts_at, ends_at, self.comment_var.get()

    def save(self):
        try:
            user_id, table_id, starts_at, ends_at, comment = self._collect()
            if self.booking_id:
                self.backend.update_booking(
                    self.booking_id, user_id, table_id, starts_at, ends_at, comment)
            else:
                self.backend.create_booking(
                    user_id, table_id, starts_at, ends_at, comment)
        except ValidationError as exc:
            messagebox.showwarning("Проверьте данные", str(exc), parent=self)
            return
        self.app.refresh_all()
        self.destroy()


class AvailabilityDialog(tk.Toplevel):
    """Отдельное окно «Проверить доступность» столика на интервал."""

    def __init__(self, app: App):
        super().__init__(app)
        self.app = app
        self.backend = app.backend
        self.title("Проверить доступность")
        self.resizable(False, False)
        self.transient(app)
        self.grab_set()

        frm = ttk.Frame(self, padding=16)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Стол:").grid(row=0, column=0, sticky="w", pady=4)
        self.tables = self.backend.get_all_tables()
        self.table_map = {
            f"Стол {t.number} ({t.capacity} мест, {t.location})": t.id
            for t in self.tables
        }
        self.table_var = tk.StringVar()
        ttk.Combobox(frm, textvariable=self.table_var,
                     values=list(self.table_map.keys()),
                     width=30, state="readonly").grid(row=0, column=1, pady=4)

        now = datetime.now().replace(second=0, microsecond=0)
        start_default = (now + timedelta(hours=1)).replace(minute=0)
        end_default = start_default + timedelta(hours=2)

        ttk.Label(frm, text="Дата (ГГГГ-ММ-ДД):").grid(row=1, column=0, sticky="w", pady=4)
        self.date_var = tk.StringVar(value=start_default.strftime(DATE_FMT))
        ttk.Entry(frm, textvariable=self.date_var, width=30).grid(row=1, column=1, pady=4)

        ttk.Label(frm, text="Начало (ЧЧ:ММ):").grid(row=2, column=0, sticky="w", pady=4)
        self.start_var = tk.StringVar(value=start_default.strftime(TIME_FMT))
        ttk.Entry(frm, textvariable=self.start_var, width=30).grid(row=2, column=1, pady=4)

        ttk.Label(frm, text="Конец (ЧЧ:ММ):").grid(row=3, column=0, sticky="w", pady=4)
        self.end_var = tk.StringVar(value=end_default.strftime(TIME_FMT))
        ttk.Entry(frm, textvariable=self.end_var, width=30).grid(row=3, column=1, pady=4)

        ttk.Button(frm, text="Проверить", command=self.check).grid(
            row=4, column=0, columnspan=2, pady=(12, 6))

        self.result = ttk.Label(frm, text="", font=(UI_FONT, 10, "bold"))
        self.result.grid(row=5, column=0, columnspan=2)

    def check(self):
        try:
            table_id = self.table_map.get(self.table_var.get())
            if not table_id:
                raise ValidationError("Выберите стол.")
            starts_at = parse_datetime(self.date_var.get(), self.start_var.get())
            ends_at = parse_datetime(self.date_var.get(), self.end_var.get())
            free = self.backend.check_table_availability(table_id, starts_at, ends_at)
        except ValidationError as exc:
            self.result.config(text=str(exc), foreground="#d64545")
            return
        if free:
            self.result.config(text="✓ Свободен — можно бронировать.",
                               foreground="#2e9e5b")
        else:
            conflicts = self.backend.get_conflicting_bookings(
                table_id, starts_at, ends_at)
            msg = self.backend._conflict_message(conflicts)
            self.result.config(text="✗ " + msg, foreground="#d64545")


# ---------------------------------------------------------------------------
# Запуск.
# ---------------------------------------------------------------------------

def main():
    # На некоторых консолях Windows кодовая страница не печатает кириллицу —
    # переключаем потоки на UTF-8, чтобы мастер настройки не падал.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass

    cfg = ensure_config()
    driver = PostgresDriver(**cfg)
    try:
        driver.create_tables()
        backend = Backend(driver)
        if backend.count_tables() == 0:
            prompt_initial_tables(backend)
        app = App(backend)
        app.mainloop()
    finally:
        driver.close()


if __name__ == "__main__":
    main()

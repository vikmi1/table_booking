**English** · [Deutsch](README.de.md) · [Русский](README.ru.md)

# Restaurant Table Booking System

A desktop application (Python + PostgreSQL) for managing table reservations
in a restaurant. The interface is built with Tkinter: a floor map with color-coded
tables, lists of customers, tables and reservations, availability checks and
overlap control.

The interface of the app is in Russian; UI labels below are given in Russian with an English translation.

## Screenshots

**Floor map** — tables that are occupied at the selected time are red and show when the reservation ends:

![Floor map](screenshots/booking_map.png)

**List of reservations:**

![List of reservations](screenshots/booking_bookings.png)

## 🚀 Quick start

**Prerequisites:** Python 3.9+ installed and a running PostgreSQL
server (you do not need to open pgAdmin).

### Windows

1. Download/unpack the project and open its folder.
2. Double-click **`start.cmd`** (or run it in a terminal):
   ```
   start.cmd
   ```

### macOS

1. Download/unpack the project and open its folder in Terminal.
2. Make the file executable once and run it:
   ```
   chmod +x start.command
   ./start.command
   ```

The script installs the dependencies and starts the app. **On the first run**
a short wizard appears in the terminal: choose "create a new database", enter a
database name (e.g. `booking_db`) and the password of the `postgres` user — and
the app window opens. Details are in the [Running](#running) and
[First run: database setup](#first-run-database-setup) sections below.

> You can also start it manually: `pip install -r requirements.txt`, then
> `python app.py`.

---

## Features

- **Floor map** — tables are drawn as rectangles with a number and a caption
  (seats, location). Green means free, red means occupied. For an occupied table
  you can see until when. Clicking a table opens the reservation form.
- **Customers** — a guest directory (name, email, phone). Full CRUD.
- **Tables** — number, capacity, location, active flag. Full CRUD,
  quick setting of the number of tables (1–10).
- **Reservations** — full CRUD and a readable list of all reservations.
- **Availability check** for a table over a selected time interval.
- **Overlap control** — you cannot create a reservation that overlaps an
  existing one for the same table. Back-to-back reservations (one ends exactly
  when the next one starts) are allowed.
- **Sample data** — a button creates 3 customers and 2 reservations for a demo.

## Project structure

```
postgres_driver.py   — database connection, SQL execution, creating the database and tables
backend.py           — business logic and CRUD, availability/overlap checks
config.py            — reading .env and the console first-run setup wizard
models/
  user.py            — User model (customer)
  table.py           — Table model
  booking.py         — Booking model (reservation)
app.py               — Tkinter interface and entry point
requirements.txt
.env.example
start.cmd            — start on Windows
start.command        — start on macOS
```

Database tables: `customers`, `restaurant_tables`, `bookings`.

## Requirements

- Python 3.9+ (Tkinter ships with the standard Python distribution).
- An installed and **running PostgreSQL server**.

> **Do I need pgAdmin?** No. pgAdmin is just a graphical client for browsing
> the database. The app connects to the PostgreSQL server directly.
> It is enough that the server service (`postgresql-x64-…`) is running — usually
> it starts automatically with the system. You do not need to open pgAdmin.

## Running

### Windows
Double-click **`start.cmd`** (or run it in a terminal):

```
start.cmd
```

### macOS
Make the file executable once, then start it with a double-click:

```
chmod +x start.command
./start.command
```

The script installs the dependencies from `requirements.txt` and starts `app.py`.
You can also run it directly:

```
pip install -r requirements.txt
python app.py
```

## First run: database setup

On the first run (if there is no `.env` file yet) a wizard appears in the **terminal**.
To keep things simple for non-technical users, it asks only for the essentials:

1. Choose: **create a new database** or **connect to an existing one**.
2. **Database name** (e.g. `booking_db`).
3. **Password of the postgres user** — the one set when installing
   PostgreSQL.

Host (`localhost`), port (`5432`) and user (`postgres`) use the standard
values — you do not need to enter them. If the connection fails (for example,
PostgreSQL runs on a non-standard port), the wizard offers to enter these
parameters manually.

Then:

4. If "create" was chosen, the app connects to the system database `postgres`
   and runs `CREATE DATABASE`.
5. The parameters are saved to `.env`.
6. You are asked **how many tables to create (1–10)**.
7. The app window opens.

> **About the port.** The standard PostgreSQL port is `5432`; it is the same on
> all computers with a regular installation. A different port is rare: it happens
> when several PostgreSQL versions are installed or the port was changed manually.

On subsequent runs `.env` already exists — the wizard does not appear and the
window opens right away.

> To run the setup again (for example, to create a separate database), delete
> the `.env` file and start the app again.

## The .env file

```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=booking_db
DB_USER=postgres
DB_PASSWORD=your_password
```

A template is in `.env.example`. The `.env` file is not committed to the repository.

## How to use

1. On the **"Столы и настройки" (Tables & settings)** tab set the number of tables
   and, if you like, edit each table (seats, location). You can click
   **"Создать тестовые данные" (Create sample data)**.
2. On the **"Клиенты" (Customers)** tab add guests.
3. On the **"Бронирования" (Reservations)** tab or directly on the **floor map**
   (click a table) create a reservation: choose a customer, a table, a date and a time.
4. The **"Проверить доступность" (Check availability)** button shows whether a table is free for an interval.
5. On the floor map choose a date and a time and click **"Показать занятость" (Show occupancy)** —
   the tables turn green/red.

## Overlap logic

Reservation A `[a_start, a_end)` and reservation B `[b_start, b_end)` for the same
table overlap if `a_start < b_end` **and** `a_end > b_start`. The inequalities are
strict, so back-to-back reservations (e.g. 18:00–20:00 and 20:00–22:00) are
allowed. The app also checks that the end time is later than the start time.

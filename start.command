#!/bin/bash
# Запуск системы бронирования на macOS.
# Сделайте файл исполняемым (один раз):  chmod +x start.command
# затем запускайте двойным кликом.

cd "$(dirname "$0")"

# Выбираем доступную команду Python.
if command -v python3 >/dev/null 2>&1; then
    PY=python3
else
    PY=python
fi

echo "Проверяю зависимости..."
$PY -m pip install -r requirements.txt

echo "Запуск приложения..."
$PY app.py

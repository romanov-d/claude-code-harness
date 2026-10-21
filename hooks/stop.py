#!/usr/bin/env python3
"""Хук Stop: не даёт закончить сессию, в которой работали, но ничего не записали.

Логика простая и намеренно грубая:
  1. Смотрим стенограмму сессии. Если агент правил файлы (Write/Edit) или много
     раз лез в Bash — значит работа была.
  2. Смотрим базу: появилась ли за эту сессию хоть одна запись в журнале или
     новая задача.
  3. Работа была, записи нет — возвращаем код 2. Claude Code показывает текст
     из stderr модели и не даёт остановиться, пока она не запишет.

Защита от петли: если Claude Code уже перезапустил нас после блокировки
(stop_hook_active), пропускаем — иначе сессия зациклится.
"""
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta

HUB = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
DB = os.path.join(HUB, "hub.db")

# Одна правка файла — уже работа.
EDIT_TOOLS = ('"name":"Edit"', '"name": "Edit"', '"name":"Write"', '"name": "Write"',
              '"name":"NotebookEdit"', '"name": "NotebookEdit"', '"name":"MultiEdit"',
              '"name": "MultiEdit"')
BASH_TOOLS = ('"name":"Bash"', '"name": "Bash"')
BASH_THRESHOLD = 10          # столько команд без единой правки — тоже работа
MAX_READ = 12 * 1024 * 1024  # стенограмма может быть огромной, хвоста хватает


def worked(transcript_path):
    """Была ли в сессии настоящая работа, а не разговор."""
    if not transcript_path or not os.path.exists(transcript_path):
        return False
    try:
        size = os.path.getsize(transcript_path)
        with open(transcript_path, "r", encoding="utf-8", errors="ignore") as f:
            if size > MAX_READ:
                f.seek(size - MAX_READ)
            raw = f.read()
    except Exception:
        return False
    if any(t in raw for t in EDIT_TOOLS):
        return True
    return sum(raw.count(t) for t in BASH_TOOLS) >= BASH_THRESHOLD


def recorded_since(started_at):
    """Появилась ли за сессию запись в журнале или новая задача."""
    try:
        conn = sqlite3.connect(DB)
        n = conn.execute("SELECT COUNT(*) FROM entries WHERE ts >= ?", (started_at,)).fetchone()[0]
        n += conn.execute("SELECT COUNT(*) FROM tasks WHERE created_at >= ?",
                          (started_at,)).fetchone()[0]
        return n > 0
    except Exception:
        return True   # база недоступна — не мешаем работать


def session_start(session_id):
    """Начало сессии по таблице sessions; нет записи — берём последний час."""
    fallback = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
    if not session_id:
        return fallback
    try:
        conn = sqlite3.connect(DB)
        row = conn.execute("SELECT started_at FROM sessions WHERE session_id = ?"
                           " ORDER BY id DESC LIMIT 1", (session_id,)).fetchone()
        return row[0] if row and row[0] else fallback
    except Exception:
        return fallback


def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if d.get("stop_hook_active"):
        sys.exit(0)
    if not worked(d.get("transcript_path")):
        sys.exit(0)
    started = session_start(d.get("session_id"))
    if recorded_since(started):
        sys.exit(0)

    sys.stderr.write(
        "[hub] В этой сессии велась работа, но в журнале не появилось ни одной записи.\n"
        "Запиши сделанное одной командой и только потом заканчивай:\n"
        '  hub log "что сделано, где проверить, какие грабли, на чём остановились"'
        " -k result --actor claude\n"
        "Если работа была по конкретной задаче — добавь -t <id> и закрой её через"
        " hub t done <id>.\n"
    )
    sys.exit(2)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Хуки SessionStart и SessionEnd.

SessionStart отдаёт агенту состояние проекта: на чём остановились, открытые
задачи, блокеры, последние записи. Агент получает готовую сводку и не
разбирает кодовую базу заново — это экономит и время, и контекстное окно.

SessionEnd закрывает запись о сессии. По этим записям потом считается,
сколько работали и по каким проектам.

Вызов:
    session.py start
    session.py end
"""
import json
import os
import sqlite3
import sys
from datetime import datetime

HUB = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
DB = os.path.join(HUB, "hub.db")
NOW = lambda: datetime.now().strftime("%Y-%m-%d %H:%M")


def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def project_for(c, cwd):
    """Самый глубокий проект, чей путь является началом текущей папки."""
    best = None
    for r in c.execute("SELECT * FROM projects WHERE path IS NOT NULL"):
        if r["path"] and cwd.startswith(r["path"]):
            if best is None or len(r["path"]) > len(best["path"]):
                best = r
    return best


def start(d):
    cwd = d.get("cwd") or os.getcwd()
    sid = d.get("session_id") or ""
    c = conn()
    p = project_for(c, cwd)
    pid = p["id"] if p else None
    c.execute("INSERT INTO sessions (project_id, cwd, session_id, started_at)"
              " VALUES (?,?,?,?)", (pid, cwd, sid, NOW()))
    c.commit()
    if not p:
        return

    out = [f"[hub] Проект: {p['name']} ({p['slug']})"]
    if p["note"]:
        out.append(f"На чём остановились: {p['note']}")

    tasks = c.execute(
        "SELECT id, title, status, due FROM tasks"
        " WHERE project_id = ? AND status IN ('todo','doing','blocked')"
        " ORDER BY CASE status WHEN 'doing' THEN 0 WHEN 'blocked' THEN 1 ELSE 2 END,"
        " priority, id LIMIT 15", (pid,)).fetchall()
    if tasks:
        out.append("\nОткрытые задачи:")
        for t in tasks:
            mark = {"doing": "→", "blocked": "✗"}.get(t["status"], "·")
            due = f" (до {t['due']})" if t["due"] else ""
            out.append(f"  {mark} #{t['id']} {t['title']}{due}")

    log = c.execute(
        "SELECT ts, kind, actor, text FROM entries WHERE project_id = ?"
        " ORDER BY id DESC LIMIT 3", (pid,)).fetchall()
    if log:
        out.append("\nПоследние записи:")
        for e in log:
            head = e["text"].split("\n")[0][:220]
            out.append(f"  [{e['ts']}] [{e['kind']}/{e['actor']}] {head}")

    out.append("\nПеред работой прочитай это вместо разбора кодовой базы. "
               "По итогам работы обязательна запись: hub log \"...\" -k result --actor claude")
    print("\n".join(out))


def end(d):
    sid = d.get("session_id") or ""
    if not sid:
        return
    c = conn()
    c.execute("UPDATE sessions SET ended_at = ? WHERE session_id = ? AND ended_at IS NULL",
              (NOW(), sid))
    c.commit()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "start"
    try:
        d = json.load(sys.stdin)
    except Exception:
        d = {}
    try:
        (start if mode == "start" else end)(d)
    except Exception:
        pass          # хук никогда не должен ломать сессию
    sys.exit(0)


if __name__ == "__main__":
    main()

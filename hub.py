#!/usr/bin/env python3
"""hub — минимальная CLI для обвязки Claude Code.

Проекты, задачи, журнал. Только стандартная библиотека и SQLite.

    hub.py init
    hub.py p add <slug> <name> [--path PATH]
    hub.py p show [slug]
    hub.py p list
    hub.py p note <slug> "на чём остановились"
    hub.py t add "заголовок" [-p slug] [-d ГГГГ-ММ-ДД] [--parent ID]
    hub.py t list [-p slug]
    hub.py t start <id>
    hub.py t done <id>
    hub.py t block <id> "чего ждём"
    hub.py t body <id> "контекст" [-a]
    hub.py log "текст" [-k kind] [-p slug] [-t id] [--actor me|claude]
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime

HUB = os.path.dirname(os.path.realpath(__file__))
DB = os.path.join(HUB, "hub.db")
NOW = lambda: datetime.now().strftime("%Y-%m-%d %H:%M")


def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def cmd_init(a):
    with open(os.path.join(HUB, "schema.sql"), encoding="utf-8") as f:
        conn().executescript(f.read())
    print(f"база готова: {DB}")


def resolve_project(c, slug=None):
    """Проект по слагу, а без слага — по текущей папке."""
    if slug:
        return c.execute("SELECT * FROM projects WHERE slug = ?", (slug,)).fetchone()
    cwd = os.getcwd()
    best = None
    for r in c.execute("SELECT * FROM projects WHERE path IS NOT NULL"):
        if r["path"] and cwd.startswith(r["path"]):
            if best is None or len(r["path"]) > len(best["path"]):
                best = r
    return best


# ---------- проекты ----------

def cmd_p_add(a):
    c = conn()
    path = os.path.abspath(os.path.expanduser(a.path)) if a.path else None
    c.execute("INSERT INTO projects (slug, name, path, updated_at) VALUES (?,?,?,?)",
              (a.slug, a.name, path, NOW()))
    c.commit()
    print(f"проект {a.slug} добавлен")


def cmd_p_note(a):
    c = conn()
    c.execute("UPDATE projects SET note = ?, updated_at = ? WHERE slug = ?",
              (a.text, NOW(), a.slug))
    c.commit()
    print("записано")


def cmd_p_list(a):
    for r in conn().execute("SELECT slug, name, status FROM projects ORDER BY priority, slug"):
        print(f"{r['slug']:<22} {r['status']:<8} {r['name']}")


def cmd_p_show(a):
    c = conn()
    p = resolve_project(c, a.slug)
    if not p:
        print("проект не найден: укажи слаг или запусти из папки проекта")
        return
    print(f"{p['name']} ({p['slug']})  [{p['status']}]")
    if p["path"]:
        print(f"путь: {p['path']}")
    if p["note"]:
        print(f"\nна чём остановились:\n{p['note']}")

    rows = c.execute(
        "SELECT id, title, status, due FROM tasks WHERE project_id = ?"
        " AND status IN ('todo','doing','blocked')"
        " ORDER BY CASE status WHEN 'doing' THEN 0 WHEN 'blocked' THEN 1 ELSE 2 END,"
        " priority, id", (p["id"],)).fetchall()
    if rows:
        print("\nоткрытые задачи:")
        for t in rows:
            mark = {"doing": "→", "blocked": "✗"}.get(t["status"], "·")
            due = f"  до {t['due']}" if t["due"] else ""
            print(f"  {mark} #{t['id']:<5} {t['title']}{due}")

    rows = c.execute("SELECT ts, kind, actor, text FROM entries WHERE project_id = ?"
                     " ORDER BY id DESC LIMIT 5", (p["id"],)).fetchall()
    if rows:
        print("\nпоследние записи:")
        for e in rows:
            print(f"  [{e['ts']}] [{e['kind']}/{e['actor']}] {e['text'].splitlines()[0][:200]}")


# ---------- задачи ----------

def cmd_t_add(a):
    c = conn()
    p = resolve_project(c, a.project)
    c.execute("INSERT INTO tasks (project_id, title, due, parent_id, created_at)"
              " VALUES (?,?,?,?,?)",
              (p["id"] if p else None, a.title, a.due, a.parent, NOW()))
    c.commit()
    tid = c.execute("SELECT last_insert_rowid() AS i").fetchone()["i"]
    print(f"#{tid} {a.title}" + (f" → {p['slug']}" if p else ""))


def cmd_t_list(a):
    c = conn()
    p = resolve_project(c, a.project)
    q = ("SELECT t.id, t.title, t.status, t.due, p.slug FROM tasks t"
         " LEFT JOIN projects p ON p.id = t.project_id"
         " WHERE t.status IN ('todo','doing','blocked')")
    args = []
    if p:
        q += " AND t.project_id = ?"
        args.append(p["id"])
    q += " ORDER BY t.priority, t.id"
    for t in c.execute(q, args):
        mark = {"doing": "→", "blocked": "✗"}.get(t["status"], "·")
        print(f"{mark} #{t['id']:<5} {t['title']}" + (f"  [{t['slug']}]" if t["slug"] else ""))


def _set_status(tid, status, done=False):
    c = conn()
    c.execute("UPDATE tasks SET status = ?, done_at = ? WHERE id = ?",
              (status, NOW() if done else None, tid))
    c.commit()


def cmd_t_start(a):
    _set_status(a.id, "doing")
    print(f"#{a.id} в работе")


def cmd_t_done(a):
    _set_status(a.id, "done", done=True)
    print(f"#{a.id} закрыта")


def cmd_t_block(a):
    _set_status(a.id, "blocked")
    c = conn()
    row = c.execute("SELECT project_id FROM tasks WHERE id = ?", (a.id,)).fetchone()
    c.execute("INSERT INTO entries (ts, project_id, task_id, kind, text, actor)"
              " VALUES (?,?,?,?,?,?)",
              (NOW(), row["project_id"] if row else None, a.id, "blocker", a.text, "me"))
    c.commit()
    print(f"#{a.id} заблокирована: {a.text}")


def cmd_t_body(a):
    c = conn()
    cur = c.execute("SELECT body FROM tasks WHERE id = ?", (a.id,)).fetchone()
    text = (cur["body"] + "\n" + a.text).strip() if (a.append and cur and cur["body"]) else a.text
    c.execute("UPDATE tasks SET body = ? WHERE id = ?", (text, a.id))
    c.commit()
    print(f"#{a.id}: контекст записан")


# ---------- журнал ----------

def cmd_log(a):
    c = conn()
    p = resolve_project(c, a.project)
    pid = p["id"] if p else None
    c.execute("INSERT INTO entries (ts, project_id, task_id, kind, text, actor)"
              " VALUES (?,?,?,?,?,?)", (NOW(), pid, a.task, a.kind, a.text, a.actor))
    # запись result обновляет «на чём остановились» у проекта
    if pid and a.kind == "result":
        c.execute("UPDATE projects SET note = ?, updated_at = ? WHERE id = ?",
                  (a.text, NOW(), pid))
    c.commit()
    print("записано" + (f" → {p['slug']}" if p else ""))


def main():
    ap = argparse.ArgumentParser(prog="hub", add_help=True)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(fn=cmd_init)

    p = sub.add_parser("p").add_subparsers(dest="sub", required=True)
    x = p.add_parser("add"); x.add_argument("slug"); x.add_argument("name")
    x.add_argument("--path"); x.set_defaults(fn=cmd_p_add)
    x = p.add_parser("show"); x.add_argument("slug", nargs="?"); x.set_defaults(fn=cmd_p_show)
    p.add_parser("list").set_defaults(fn=cmd_p_list)
    x = p.add_parser("note"); x.add_argument("slug"); x.add_argument("text")
    x.set_defaults(fn=cmd_p_note)

    t = sub.add_parser("t").add_subparsers(dest="sub", required=True)
    x = t.add_parser("add"); x.add_argument("title"); x.add_argument("-p", "--project")
    x.add_argument("-d", "--due"); x.add_argument("--parent", type=int)
    x.set_defaults(fn=cmd_t_add)
    x = t.add_parser("list"); x.add_argument("-p", "--project"); x.set_defaults(fn=cmd_t_list)
    for name, fn in (("start", cmd_t_start), ("done", cmd_t_done)):
        x = t.add_parser(name); x.add_argument("id", type=int); x.set_defaults(fn=fn)
    x = t.add_parser("block"); x.add_argument("id", type=int); x.add_argument("text")
    x.set_defaults(fn=cmd_t_block)
    x = t.add_parser("body"); x.add_argument("id", type=int); x.add_argument("text")
    x.add_argument("-a", "--append", action="store_true"); x.set_defaults(fn=cmd_t_body)

    x = sub.add_parser("log"); x.add_argument("text")
    x.add_argument("-k", "--kind", default="note",
                   choices=["note", "result", "decision", "blocker"])
    x.add_argument("-p", "--project"); x.add_argument("-t", "--task", type=int)
    x.add_argument("--actor", default="me", choices=["me", "claude"])
    x.set_defaults(fn=cmd_log)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Хук UserPromptSubmit: ловит момент, когда человек ставит новую задачу.

Зачем: правило в CLAUDE.md агент читает один раз в начале сессии и к середине
разговора о нём забывает — новая задача произносится посреди работы и нигде
не фиксируется. Хук срабатывает на каждой реплике и добавляет короткое
напоминание ровно тогда, когда реплика похожа на постановку задачи.

Цена: ~40 токенов и только на подходящих репликах. На «что это за фильм»
хук молчит.
"""
import json
import os
import re
import sqlite3
import sys

HUB = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
DB = os.path.join(HUB, "hub.db")

# Глаголы и обороты, которыми ставят задачу. Ищем по началу слова, чтобы
# «сделай», «сделать», «сделаем» ловились одним корнем.
TASK_WORDS = r"""
сделай|сделать|сделаем|доделай|переделай|добавь|добавить|напиши|написать|
почини|исправь|поправь|пофикси|реализуй|внедри|настрой|создай|заведи|
разбери|разберись|посмотри|проверь|обнови|перенеси|выкати|задеплой|
нужно|надо|требуется|давай|запили|накидай|собери|подготовь|оформи|
задача|таска|дедлайн|к понедельнику|к вторнику|к среде|к четвергу|
к пятнице|к субботе|к воскресенью|до завтра|до конца недели|срочно
"""
TASK_RE = re.compile("|".join(w.strip() for w in TASK_WORDS.split("|") if w.strip()),
                     re.I | re.X)

# Реплики, которые выглядят как задача, но ею не являются: это про сам журнал
# или про уже идущую работу.
SKIP_RE = re.compile(r"\bhub (t|log|p) |запиши в журнал", re.I)


def project_for(cwd):
    """Слаг проекта по текущей папке — чтобы подсказать готовую команду."""
    try:
        conn = sqlite3.connect(DB)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT slug, path FROM projects WHERE path IS NOT NULL").fetchall()
        best = None
        for r in rows:
            if r["path"] and cwd.startswith(r["path"]):
                if best is None or len(r["path"]) > len(best["path"]):
                    best = r
        return best["slug"] if best else None
    except Exception:
        return None


def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    prompt = (d.get("prompt") or "").strip()
    if len(prompt) < 12 or SKIP_RE.search(prompt):
        sys.exit(0)
    if not TASK_RE.search(prompt):
        sys.exit(0)

    slug = project_for(d.get("cwd") or os.getcwd())
    where = f" -p {slug}" if slug else ""
    print(
        "[hub] Реплика похожа на новую задачу. Прежде чем браться за работу — "
        f'заведи её: hub t add "<суть>"{where} (плюс -d ГГГГ-ММ-ДД, если есть срок). '
        "Разрешения не спрашивай. "
        "Если это не задача, а уточнение по текущей работе — просто продолжай."
    )
    sys.exit(0)


if __name__ == "__main__":
    main()

"""Обслуживание с сервера (без веба):

    python -m hypede_store.admin moderator НИК     сделать модератором
    python -m hypede_store.admin user НИК          снять права модератора
    python -m hypede_store.admin ban НИК           заблокировать
    python -m hypede_store.admin unban НИК
    python -m hypede_store.admin queue             что ждёт проверки
"""

import sys

from .config import Config
from .db import Database


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("moderator", "user", "ban", "unban", "queue"):
        print(__doc__)
        return 2
    db = Database(Config().db_path)
    if argv[0] == "queue":
        for row in db.all("SELECT v.id, v.number, i.kind, i.name, u.handle FROM versions v "
                          "JOIN items i ON i.id = v.item_id JOIN users u ON u.id = i.owner_id "
                          "WHERE v.status = 'pending' ORDER BY v.created_at"):
            print(f"#{row['id']}  {row['kind']:9}  {row['name']} v{row['number']}  by @{row['handle']}")
        return 0
    if len(argv) != 2:
        print(__doc__)
        return 2
    handle = argv[1].lower()
    if db.one("SELECT 1 FROM users WHERE handle = ?", handle) is None:
        print(f"no user @{handle}")
        return 1
    if argv[0] in ("moderator", "user"):
        db.run("UPDATE users SET role = ? WHERE handle = ?", argv[0], handle)
    else:
        db.run("UPDATE users SET banned = ? WHERE handle = ?", 1 if argv[0] == "ban" else 0, handle)
        if argv[0] == "ban":
            db.run("DELETE FROM sessions WHERE user_id = (SELECT id FROM users WHERE handle = ?)", handle)
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

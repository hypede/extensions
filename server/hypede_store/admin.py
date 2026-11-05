"""Обслуживание без веба (данные — там же, где у сервиса: диск или Vercel Blob):

    python -m hypede_store.admin moderator НИК     сделать модератором
    python -m hypede_store.admin user НИК          снять права модератора
    python -m hypede_store.admin ban НИК           заблокировать
    python -m hypede_store.admin unban НИК
    python -m hypede_store.admin queue             что ждёт проверки
"""

import sys

from .config import Config
from .repo import Repo
from .storage import from_env


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("moderator", "user", "ban", "unban", "queue"):
        print(__doc__)
        return 2
    repo = Repo(from_env(Config().data))
    if argv[0] == "queue":
        for pending in repo.queue():
            item = repo.item(pending["item"])
            if item:
                print(f"{item['id']}-{pending['number']}  {item['kind']:9}  {item['name']}")
        return 0
    if len(argv) != 2:
        print(__doc__)
        return 2
    user = repo.user_by_handle(argv[1].lower())
    if user is None:
        print(f"no user @{argv[1]}")
        return 1
    if argv[0] in ("moderator", "user"):
        user["role"] = argv[0]
    else:
        user["banned"] = argv[0] == "ban"
        user["epoch"] = user.get("epoch", 0) + 1
    repo.save_user(user)
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

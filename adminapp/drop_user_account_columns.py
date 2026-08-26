"""一次性移除 users 中由 accts 提供的重複帳號欄位。

執行方式：
    docker compose exec admin-app python drop_user_account_columns.py

腳本只刪除欄位，不刪除任何 User 資料列；重複執行也不會失敗。
"""

import asyncio
import os
import sys

from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.repository.database import engine


ACCOUNT_MIRROR_COLUMNS = (
    "acct_id",
    "email",
    "full_name",
    "acct_full_name_2nd",
    "acct_locale_code",
    "acct_create_ut",
    "acct_update_ut",
    "acct_update_scrt_ut",
    "acct_last_login_ut",
    "acct_last_login_info",
    "admin_role",
    "agent_role",
    "orgs",
    "is_active",
)


async def migrate():
    statements = ", ".join(
        f"DROP COLUMN IF EXISTS {column}" for column in ACCOUNT_MIRROR_COLUMNS
    )

    async with engine.begin() as connection:
        await connection.execute(text(f"ALTER TABLE users {statements}"))

    print("users 重複帳號欄位已移除：")
    for column in ACCOUNT_MIRROR_COLUMNS:
        print(f"  - {column}")


if __name__ == "__main__":
    asyncio.run(migrate())
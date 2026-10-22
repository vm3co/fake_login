"""
add_sendtask_columns.py — 一次性 DDL 遷移腳本

用途：
    為 sendtasks 資料表新增 3 個欄位：
        send_end_ut, sendtask_public, server_url

執行方式（在 Docker 容器內）：
    docker exec -it fake-login-admin-app python add_sendtask_columns.py

或在本地直接執行（需要設定好 .env 環境變數）：
    python add_sendtask_columns.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.repository.database import init_db
from backend.repository.db_controller import db_controller
from sqlalchemy import text

NEW_COLUMNS = [
    ("send_end_ut",     "BIGINT"),
    ("sendtask_public", "BOOLEAN"),
    ("server_url",      "TEXT"),
]

async def migrate():
    print("=" * 60)
    print("  sendtasks 欄位新增腳本啟動")
    print("=" * 60)

    await init_db()

    for col_name, col_type in NEW_COLUMNS:
        stmt = text(
            f"ALTER TABLE sendtasks "
            f"ADD COLUMN IF NOT EXISTS {col_name} {col_type};"
        )
        await db_controller.execute(stmt)
        print(f"  + {col_name} {col_type}  ... OK")

    print("\n全部欄位新增完成。")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(migrate())

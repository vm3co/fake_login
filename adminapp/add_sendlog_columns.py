"""
add_sendlog_columns.py — 一次性 DDL 遷移腳本

用途：
    為 send_log_details 資料表新增 4 個欄位：
        order_no, template_order, template_selection, trigger_man

執行方式（在 Docker 容器內）：
    docker exec -it fake-login-admin-app python add_sendlog_columns.py

或在本地直接執行（需要設定好 .env 環境變數）：
    python add_sendlog_columns.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.repository.database import init_db
from backend.repository.db_controller import db_controller
from sqlalchemy import text

NEW_COLUMNS = [
    ("order_no",           "INTEGER"),
    ("template_order",     "INTEGER"),
    ("template_selection", "INTEGER"),
    ("trigger_man",        "INTEGER"),
]

async def migrate():
    print("=" * 60)
    print("  send_log_details 欄位新增腳本啟動")
    print("=" * 60)

    await init_db()

    for col_name, col_type in NEW_COLUMNS:
        stmt = text(
            f"ALTER TABLE send_log_details "
            f"ADD COLUMN IF NOT EXISTS {col_name} {col_type};"
        )
        await db_controller.execute(stmt)
        print(f"  + {col_name} {col_type}  ... OK")

    print("\n全部欄位新增完成。")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(migrate())

"""
backfill_mtmpl_columns.py — 郵件樣板新欄位回填腳本

用途：
    從 SE2 系統重新抓取資料，全量 upsert mtmpl 表，
    回填以下新增欄位：
    - mtmpl_name, mtmpl_tag, mtmpl_content, mtmpl_mail_attached
    - mtmpl_create_ut, mtmpl_update_ut, mtmpl_owner_gid
    - mail_from, mail_from_address

執行方式（在 Docker 容器內）：
    docker exec -it fake-login-admin-app python backfill_mtmpl_columns.py

注意：
    此腳本使用 upsert（ON CONFLICT DO UPDATE），可安全重複執行。
    現有欄位（mtmpl_title 等）也會一併更新為 SE2 最新值。
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.repository.database import init_db
from backend.services.db_user import DBUser

db_user = DBUser()


async def main():
    print("=" * 60)
    print("  mtmpl 欄位回填腳本啟動")
    print("=" * 60)

    await init_db()

    start = time.time()

    print("\n  正在從 SE2 抓取郵件樣板並回填...")
    result = await db_user.refresh_mtmpl()
    upserted = result.get("upserted", 0)

    if upserted == 0:
        print("  ⚠ 從 SE2 抓取不到郵件樣板資料，請確認 SE2 連線。")
    else:
        print(f"  ✓ 已 upsert {upserted} 筆郵件樣板")

    elapsed = time.time() - start

    print("\n" + "=" * 60)
    print(f"  回填完成！耗時 {elapsed:.1f} 秒")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

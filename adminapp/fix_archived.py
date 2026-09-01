"""
fix_archived.py — 一次性修復腳本

用途：
    修正因舊邏輯（NULL 被當作「已過 14 天」）導致的誤封存任務。
    此腳本會：
    1. 先把所有 is_archived=True 的任務全部 Reset 回 False
    2. 用新的正確邏輯重新評估，將符合條件的任務重新封存

執行方式（在 Docker 容器內）：
    docker exec -it fake-login-admin-app python fix_archived.py

或在本地直接執行（需要設定好 .env 環境變數）：
    python fix_archived.py
"""

import asyncio
import time
import os
import sys

# 確保可以 import 到 backend 相關模組
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.repository.database import init_db
from backend.repository.db_controller import db_controller
from backend.repository.models import SendTask
from sqlalchemy import select, update


THRESHOLD_DAYS = 14


def is_should_archive(test_end_ut, pre_test_end_ut, stop_time_new, threshold_time: int) -> bool:
    """
    正確的封存判斷邏輯：
    - NULL、0、-1 等無效值視為「忽略該欄位」
    - 有效欄位（> 0）必須全部超過 14 天才封存
    - 若全部都是無效值，視為無法判斷，不封存
    """
    time_values = [test_end_ut, pre_test_end_ut, stop_time_new]
    valid_times = [v for v in time_values if v and v > 0]

    if not valid_times:
        return False  # 全部無效值，無法判斷，不封存

    return all(t < threshold_time for t in valid_times)


async def fix():
    print("=" * 60)
    print("  is_archived 修復腳本啟動")
    print("=" * 60)

    # 初始化資料庫連線
    await init_db()

    now = int(time.time())
    threshold_time = now - (THRESHOLD_DAYS * 86400)
    print(f"\n目前時間戳：{now}")
    print(f"14 天門檻：{threshold_time}（早於此時間戳才算超過 14 天）\n")

    # ── Step 1：把所有 is_archived=True 的任務全部 Reset 回 False ──────────
    print("Step 1：將所有 is_archived=True 的任務 Reset 回 False...")

    stmt_reset = (
        update(SendTask)
        .where(SendTask.is_archived == True)
        .values(is_archived=False)
    )
    result_reset = await db_controller.execute(stmt_reset)
    print(f"        已 Reset {result_reset.rowcount} 筆任務。\n")

    # ── Step 2：撈出所有任務，用新邏輯重新評估 ──────────────────────────────
    print("Step 2：重新評估所有任務的封存狀態...")

    stmt_all = select(
        SendTask.sendtask_uuid,
        SendTask.sendtask_id,
        SendTask.test_end_ut,
        SendTask.pre_test_end_ut,
        SendTask.stop_time_new,
    )
    result_all = await db_controller.execute(stmt_all)
    all_tasks = result_all.all()
    print(f"        共 {len(all_tasks)} 筆任務待評估。\n")

    # ── Step 3：分類並重新封存 ───────────────────────────────────────────────
    to_archive = []
    to_keep    = []
    to_skip    = []  # 全為無效值，無法判斷

    for row in all_tasks:
        test_end_ut     = row.test_end_ut
        pre_test_end_ut = row.pre_test_end_ut
        stop_time_new   = row.stop_time_new

        valid_times = [v for v in [test_end_ut, pre_test_end_ut, stop_time_new] if v and v > 0]

        if not valid_times:
            to_skip.append(row.sendtask_uuid)
        elif all(t < threshold_time for t in valid_times):
            to_archive.append(row.sendtask_uuid)
        else:
            to_keep.append(row.sendtask_uuid)

    print(f"  ✅ 應封存（所有有效時間欄位都超過 14 天）： {len(to_archive)} 筆")
    print(f"  🟡 應保留（有有效時間欄位未超過 14 天）：  {len(to_keep)} 筆")
    print(f"  ⚪ 無法判斷（所有時間欄位都是無效值）：     {len(to_skip)} 筆\n")

    # ── Step 4：執行封存 ─────────────────────────────────────────────────────
    if to_archive:
        print(f"Step 3：封存 {len(to_archive)} 筆任務...")
        stmt_archive = (
            update(SendTask)
            .where(SendTask.sendtask_uuid.in_(to_archive))
            .values(is_archived=True)
        )
        result_archive = await db_controller.execute(stmt_archive)
        print(f"        完成，實際更新 {result_archive.rowcount} 筆。\n")
    else:
        print("Step 3：沒有需要封存的任務。\n")

    # ── 摘要輸出 ─────────────────────────────────────────────────────────────
    print("=" * 60)
    print("  修復完成！摘要：")
    print(f"  - 最終封存（is_archived=True）： {len(to_archive)} 筆")
    print(f"  - 最終保留（is_archived=False）： {len(to_keep) + len(to_skip)} 筆")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(fix())

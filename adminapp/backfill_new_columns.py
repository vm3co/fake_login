"""
backfill_new_columns.py — 一次性資料回填腳本

用途：
    從 SE2 系統重新抓取資料，回填以下新增欄位的舊資料：
    - sendtasks 表：send_end_ut, sendtask_public, server_url
    - send_log_details 表：order_no, template_order, template_selection, trigger_man

執行方式（在 Docker 容器內）：
    docker exec -it fake-login-admin-app python backfill_new_columns.py

注意：
    此腳本只會更新值為 NULL 的欄位，不會覆蓋已有的資料。
    可以安全重複執行。
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.repository.database import init_db
from backend.repository.db_controller import db_controller
from backend.repository.models import SendTask, SendLogDetail
from backend.services.getSe2data import get_se2_data
from sqlalchemy import text


# ──────────────────────────────────────────────────────────────────────
# 1. 回填 sendtasks 表（send_end_ut, sendtask_public, server_url）
# ──────────────────────────────────────────────────────────────────────
async def backfill_sendtasks():
    """
    讀取 DB 中所有 sendtask_uuid，
    逐一呼叫 SE2 API get_sendtasks（全量）來比對回填。
    """
    print("\n" + "=" * 60)
    print("  [1/2] 開始回填 sendtasks 新欄位")
    print("=" * 60)

    # 取得 DB 中所有 sendtask
    tasks = await db_controller.get(SendTask)
    if not tasks:
        print("  ⚠ 資料庫中沒有任何 sendtask，跳過。")
        return

    print(f"  資料庫中共有 {len(tasks)} 個 sendtask")

    # 從 SE2 抓取所有 sendtasks（不設時間範圍）
    print("  正在從 SE2 抓取 sendtasks 清單...")
    se2_df = await get_se2_data.get_sendtasks()

    if se2_df is None or se2_df.empty:
        print("  ⚠ 從 SE2 抓取不到 sendtasks 資料，跳過。")
        return

    # 建立 uuid → row 的查找表
    se2_map = {}
    for _, row in se2_df.iterrows():
        se2_map[row["sendtask_uuid"]] = row

    updated = 0
    skipped = 0
    not_found = 0

    for task in tasks:
        uuid = task.sendtask_uuid
        se2_row = se2_map.get(uuid)

        if se2_row is None:
            not_found += 1
            continue

        # 只更新目前為 NULL 的欄位
        update_data = {}
        if task.send_end_ut is None and "send_end_ut" in se2_row.index:
            val = se2_row.get("send_end_ut")
            if val is not None and str(val) != "nan":
                update_data["send_end_ut"] = int(val)

        if task.sendtask_public is None and "sendtask_public" in se2_row.index:
            val = se2_row.get("sendtask_public")
            if val is not None and str(val) != "nan":
                update_data["sendtask_public"] = bool(val)

        if task.server_url is None and "server_url" in se2_row.index:
            val = se2_row.get("server_url")
            if val is not None and str(val) != "nan":
                update_data["server_url"] = str(val)

        if update_data:
            await db_controller.update(SendTask, {"sendtask_uuid": uuid}, update_data)
            updated += 1
            print(f"    ✓ {uuid[:12]}... 更新了 {list(update_data.keys())}")
        else:
            skipped += 1

    print(f"\n  完成！更新: {updated}, 已有資料跳過: {skipped}, SE2 找不到: {not_found}")


# ──────────────────────────────────────────────────────────────────────
# 2. 回填 send_log_details 表（order_no, template_order, template_selection, trigger_man）
# ──────────────────────────────────────────────────────────────────────
BACKFILL_SENDLOG_COLS = ["order_no", "template_order", "template_selection", "trigger_man"]

async def backfill_sendlog_details():
    """
    讀取 DB 中所有 sendtask_uuid，
    逐一呼叫 SE2 get_sendlog API 取得完整 sendlog，
    根據 uuid 比對並回填 4 個新欄位。
    """
    print("\n" + "=" * 60)
    print("  [2/2] 開始回填 send_log_details 新欄位")
    print("=" * 60)

    # 取得所有不重複的 sendtask_uuid
    tasks = await db_controller.get(SendTask)
    if not tasks:
        print("  ⚠ 資料庫中沒有任何 sendtask，跳過。")
        return

    task_uuids = [t.sendtask_uuid for t in tasks]
    print(f"  共有 {len(task_uuids)} 個 sendtask 需要處理")

    total_updated = 0
    total_skipped = 0

    for idx, sendtask_uuid in enumerate(task_uuids, 1):
        print(f"\n  [{idx}/{len(task_uuids)}] 處理 sendtask: {sendtask_uuid[:12]}...")

        # 從 SE2 抓取該任務的 sendlog
        sendlog_df = await get_se2_data.get_sendlog(sendtask_uuid)

        if sendlog_df is None or sendlog_df.empty:
            print(f"    ⚠ SE2 無 sendlog 資料，跳過。")
            continue

        # 建立 uuid → SE2 row 的查找表
        se2_log_map = {}
        for _, row in sendlog_df.iterrows():
            log_uuid = row.get("uuid")
            if log_uuid:
                se2_log_map[log_uuid] = row

        # 讀取 DB 中該 sendtask 的所有 detail
        details = await db_controller.get(SendLogDetail, {"sendtask_uuid": sendtask_uuid})

        task_updated = 0
        task_skipped = 0

        for detail in details:
            se2_row = se2_log_map.get(detail.uuid)
            if se2_row is None:
                continue

            update_data = {}
            for col in BACKFILL_SENDLOG_COLS:
                current_val = getattr(detail, col, None)
                if current_val is None and col in se2_row.index:
                    new_val = se2_row.get(col)
                    if new_val is not None and str(new_val) != "nan":
                        update_data[col] = int(new_val)

            if update_data:
                await db_controller.update(SendLogDetail, {"uuid": detail.uuid}, update_data)
                task_updated += 1
            else:
                task_skipped += 1

        total_updated += task_updated
        total_skipped += task_skipped
        print(f"    完成：更新 {task_updated} 筆, 跳過 {task_skipped} 筆")

        # 每個 sendtask 之間稍微延遲，避免 SE2 API 過載
        await asyncio.sleep(0.2)

    print(f"\n  全部完成！共更新: {total_updated}, 跳過: {total_skipped}")


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────
async def main():
    print("=" * 60)
    print("  資料回填腳本啟動")
    print("=" * 60)

    await init_db()

    start = time.time()

    await backfill_sendtasks()
    await backfill_sendlog_details()

    elapsed = time.time() - start

    print("\n" + "=" * 60)
    print(f"  全部回填作業完成！耗時 {elapsed:.1f} 秒")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

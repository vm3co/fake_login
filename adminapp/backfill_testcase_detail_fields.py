"""
backfill_testcase_detail_fields.py — 一次性資料回填腳本

用途：
    從 SE2 get_testcase API 重新抓取資料，回填 sendtasks 表新增的 testcase 詳細欄位：
    testcase_uuid, testcase_id, testcase_unit, testcase_create_ut, testcase_update_ut,
    pre_test_person_count, test_person_count, mail_server, mail_speed, mail_logic,
    mail_logging, mail_template, mail_delivery, mail_delivery_d, testcase_owner_gid,
    testcase_public, alert_content, redirect_url, clicklink_action,
    adv_mail_delivery, adv_mail_delivery_val

執行方式（在 Docker 容器內）：
    docker exec -it fake-login-admin-app python backfill_testcase_detail_fields.py

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
from backend.repository.models import SendTask
from backend.services.db_user import DBUser, TESTCASE_DETAIL_COLUMNS


async def backfill_testcase_detail_fields():
    print("=" * 60)
    print("  開始回填 sendtasks 表的 testcase 詳細欄位")
    print("=" * 60)

    tasks = await db_controller.get(SendTask)
    if not tasks:
        print("  ⚠ 資料庫中沒有任何 sendtask，跳過。")
        return

    print(f"  資料庫中共有 {len(tasks)} 個 sendtask")

    db_user = DBUser()
    updated = 0
    skipped = 0
    not_found_tasks = []

    for idx, task in enumerate(tasks, 1):
        uuid = task.sendtask_uuid
        print(f"  [{idx}/{len(tasks)}] 處理 sendtask: {uuid[:12]}... ({task.sendtask_id})")

        detail_fields = await db_user._build_testcase_detail_fields(uuid)
        if not detail_fields:
            not_found_tasks.append((uuid, task.sendtask_id))
            print(f"    ⚠ SE2 查無此 testcase 或取得失敗，跳過。")
            await asyncio.sleep(0.1)
            continue

        # 只更新目前為 NULL 的欄位
        update_data = {}
        for col in TESTCASE_DETAIL_COLUMNS:
            if getattr(task, col, None) is None and detail_fields.get(col) is not None:
                update_data[col] = detail_fields[col]

        if update_data:
            await db_controller.update(SendTask, {"sendtask_uuid": uuid}, update_data)
            updated += 1
            print(f"    ✓ 更新了 {list(update_data.keys())}")
        else:
            skipped += 1

        await asyncio.sleep(0.1)

    print(f"\n  完成！更新: {updated}, 已有資料跳過: {skipped}, SE2 查無資料: {len(not_found_tasks)}")

    if not_found_tasks:
        print("\n  SE2 查無資料的任務清單：")
        for uuid, sendtask_id in not_found_tasks:
            print(f"    - {sendtask_id}  ({uuid})")


async def main():
    print("=" * 60)
    print("  資料回填腳本啟動")
    print("=" * 60)

    await init_db()

    start = time.time()
    await backfill_testcase_detail_fields()
    elapsed = time.time() - start

    print("\n" + "=" * 60)
    print(f"  全部回填作業完成！耗時 {elapsed:.1f} 秒")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

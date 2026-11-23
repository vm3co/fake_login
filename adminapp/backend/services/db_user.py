'''
Database operations for user-related data, including sendlog management.
'''

# import re
# import asyncpg
# import aiofiles
import time
import uuid
import json
from typing import List, Dict, Any
from datetime import datetime, timedelta
import pandas as pd
from sqlalchemy import func, select
from zoneinfo import ZoneInfo

from backend.services.log_manager import Logger
from backend.services.getSe2data import get_se2_data
from backend.repository.db_controller import db_controller
from backend.core.security import verify_password, hash_password
from backend.services.notification_manager import send_telegram_notification, escape_markdown_v2
from backend.repository.models import User, Acct, CustomerAcct, SendTask, SendLogDetail, SendLogStats, Mtmpl, LoginLog
from backend.services.redis_client import RedisClient
from backend.services.task_sync_window import automatic_task_sync

logger = Logger().get_logger()

# ==============================================================================
# Utility Functions (獨立出來的工具函式)
# ==============================================================================
def timestamp():
    tz = ZoneInfo("Asia/Taipei")   # 修改時區
    today = datetime.now(tz).date()
    start_ts = int(datetime.combine(today, datetime.min.time(), tz).timestamp())
    end_ts = int(datetime.combine(today, datetime.max.time(), tz).timestamp())
    return start_ts, end_ts

def calc_stats(stats: List[Dict[str, Any]]) -> Dict[str, Any]:
    """ 
    計算統計數據
    :param stats: sendlog 資料列表
    :return: 統計數據字典
    """
    start_ts, end_ts = timestamp()

    # 總寄出數量
    total_send = [t for t in stats if t.get("send_time", 0) != 0]
    # 總成功數量
    total_success = [t for t in stats if str(t.get("send_res", "")).startswith("True")]

    # 今日尚未寄送：寄送時間>=當天開始時間 & 寄送時間<當天結束時間 & 寄送時間為0
    today_unsend = [t for t in stats if start_ts <= t.get("plan_time", 0) < end_ts and t.get("send_time", 0) == 0]
    # 今日寄送：寄送時間>=當天開始時間 & 寄送時間<當天結束時間
    today_sends = [t for t in stats if start_ts <= t.get("send_time", 0) < end_ts]
    # 今日成功：寄送時間>=當天開始時間 & 寄送時間<當天結束時間 & 寄送結果為成功
    today_success = [t for t in today_sends if str(t.get("send_res", "")).startswith("True")]

    today_plan_time = [t["plan_time"] for t in stats if start_ts <= t.get("plan_time", 0) < end_ts]
    # 今日寄送裡，第一封的 plan_time（如果有的話）
    today_earliest_plan_time = min(today_plan_time) if today_plan_time else 0
    # 今日寄送裡，最後一封的 plan_time（如果有的話）
    today_latest_plan_time = max(today_plan_time) if today_plan_time else 0

    # 任務第一封的 plan_time
    all_earliest_plan_time = min((t["plan_time"] for t in stats if t.get("plan_time")), default=0)
    # 任務最後一封的 plan_time
    all_latest_plan_time = max(t["plan_time"] for t in stats) if stats else 0

    # 下一封要寄出（尚未寄出的信中最早的 plan_time，含逾期）
    next_plan_time = min(
        (t["plan_time"] for t in stats
         if t.get("send_time", 0) == 0 and t.get("plan_time")),
        default=0,
    )

    # 統計觸發人數
    trigger_fields = ["access_src", "click_src", "file_src", "second_access_src", "second_input_src", "second_qrcode_src"]
    totalTriggered = [
        t for t in stats 
        if any((t.get(field) and len(t.get(field)) > 0) for field in trigger_fields)
    ]


    return {
        "totalplanned": len(stats),
        "totalsend": len(total_send),
        "totalsuccess": len(total_success),
        "totalfailed": len(total_send) - len(total_success),  # 總失敗數量
        "totaltriggered": len(totalTriggered),
        "todayunsend": len(today_unsend),
        "todaysend": len(today_sends),
        "todaysuccess": len(today_success),
        "todayfailed": len(today_sends) - len(today_success),
        "today_earliest_plan_time": today_earliest_plan_time,
        "today_latest_plan_time": today_latest_plan_time,
        "all_earliest_plan_time": all_earliest_plan_time,
        "all_latest_plan_time": all_latest_plan_time,
        "next_plan_time": next_plan_time,
    }

# ==============================================================================
# Module Constants (模組常數)
# ==============================================================================
ACCTS_COLUMNS = [
    "acct_uuid", "acct_id", "acct_full_name", "acct_full_name_2nd", "acct_email",
    "acct_locale_code", "acct_activate", "acct_create_ut", "acct_update_ut",
    "acct_update_scrt_ut", "acct_last_login_ut", "acct_last_login_info", "admin_role",
    "agent_role", "orgs",
]

SENDTASKS_COLUMNS = ["sendtask_uuid", "sendtask_id", "sendtask_owner_gid", "person_count",
                     "pre_test_end_ut", "pre_test_start_ut", "pre_send_end_ut", "sendtask_create_ut",
                     "test_end_ut", "test_start_ut", "is_pause", "pre_test_enable", "stop_time_new",
                     "send_end_ut", "sendtask_public", "server_url"]



SENDLOG_COLUMNS = ["uuid", "target_email", "person_info", "template_uuid", "plan_time",
                   "send_time", "send_res", "access_time", "access_src", "access_dev",
                   "click_time", "click_src", "click_dev", "file_time", "file_src", "file_dev",
                   "order_no", "template_order", "template_selection", "trigger_man"]

# 來自 SE2 get_testcase 回應、任務啟動當下一次性同步進 sendtasks 的欄位
TESTCASE_DETAIL_COLUMNS = [
    "testcase_uuid", "testcase_id", "testcase_unit", "testcase_create_ut", "testcase_update_ut",
    "pre_test_person_count", "test_person_count", "mail_server", "mail_speed", "mail_logic",
    "mail_logging", "mail_template", "mail_delivery", "mail_delivery_d", "testcase_owner_gid",
    "testcase_public", "alert_content", "redirect_url", "clicklink_action",
    "adv_mail_delivery", "adv_mail_delivery_val",
]


class DBUser:
    def __init__(self, *, task_list_sync=None, task_sync=None):
        """ 
        初始化 DBUser 類別
        """
        self.day = 7  # 預設查詢天數為 7 天
        self.accts_columns = ACCTS_COLUMNS
        self.task_list_sync = task_list_sync
        self.task_sync = task_sync

    def get_task_sync(self):
        if self.task_sync is None:
            from backend.repository.database import async_session
            from backend.services.task_sync_core import TaskSyncService

            self.task_sync = TaskSyncService(async_session, get_se2_data.get_task_reader())
        return self.task_sync

    async def sync_tasks(self, uuids, *, orgs, on_result=None):
        from backend.services.task_sync_entrypoints import sync_task_batch
        from backend.services.task_sync_core import TaskSyncAccessDenied

        if orgs is not None and (
            not isinstance(orgs, (list, tuple)) or not orgs
            or any(not isinstance(group, str) or not group for group in orgs)
        ):
            raise TaskSyncAccessDenied("A trusted organization scope is required")

        core = self.get_task_sync()
        session_factory = getattr(core, "session_factory", None)
        previous = {}
        if session_factory is not None:
            async with session_factory() as session:
                previous = dict((await session.execute(select(
                    SendLogStats.sendtask_uuid, SendLogStats.todaysend,
                ).where(SendLogStats.sendtask_uuid.in_(uuids)))).all())

        async def after_commit(result):
            if on_result is not None:
                await on_result(result)
            if session_factory is not None:
                await self._notify_sync_commit(core, result, previous.get(result.task_uuid, 0))

        return await sync_task_batch(core, uuids, orgs=orgs, on_result=after_commit)

    async def _notify_sync_commit(self, core, result, old_todaysend):
        if result.status not in {"added", "updated", "recreated"}:
            return
        async with core.session_factory() as session:
            row = (await session.execute(select(SendTask.sendtask_id, SendLogStats.todaysend).join(
                SendLogStats, SendLogStats.sendtask_uuid == SendTask.sendtask_uuid,
            ).where(
                SendTask.sendtask_uuid == result.task_uuid,
                SendTask.local_generation_id == result.generation,
                SendTask.sync_revision == result.revision,
            ))).one_or_none()
        if row is not None and (result.status in {"added", "recreated"} or (old_todaysend or 0) == 0) and (row.todaysend or 0) > 0:
            sent = await send_telegram_notification(f"任務開始執行：{escape_markdown_v2(row.sendtask_id)}")
            if sent is False:
                raise RuntimeError("Telegram notification delivery failed")

    async def authorize_sync_candidate(self, task_uuid, *, orgs):
        from backend.services.task_sync_core import _require_scope

        local = await db_controller.get_one(SendTask, {"sendtask_uuid": task_uuid})
        if local is not None:
            _require_scope(local.sendtask_owner_gid, orgs)
            return {"sendtask_uuid": task_uuid, "sendtask_id": local.sendtask_id}
        response = await self.get_task_sync().reader.read_sendtask(task_uuid)
        task = response["data"]
        _require_scope(task.get("sendtask_owner_gid"), orgs)
        return task
        
    @automatic_task_sync
    async def table_initialize(self):
        """
        初始化資料表
        檢查資料表是否為空，如果是空的，則從 SE2 獲取資料並插入到資料表中。
        如果資料表已經有資料，則跳過初始化。
        """
        table_mappings = {
            "accts": {"model": Acct, "fetch_method": self.get_se2_accts, "fetch_args": [ACCTS_COLUMNS]},
            "sendtasks": {"model": SendTask},
            "mtmpl": {"model": Mtmpl, "special_logic": True},
            "sendlog_stats": {"model": SendLogStats, "special_logic": True},
            "send_log_details": {"model": SendLogDetail, "special_logic": True}
        }
        
        for table_name, config in table_mappings.items():
            model = config["model"]
            
            # Check if table is empty
            # Using get(limit=1) as a proxy for count > 0
            existing_data = await db_controller.get(model, limit=1)
            count = len(existing_data)
            
            if count == 0:
                logger.info(f"{table_name} is empty. Initializing with data from SE2...")
                if model is SendTask:
                    result = await self.sync_sendtasks(orgs=None)
                    if result["status"] == "partial":
                        from backend.services.task_sync_entrypoints import TaskSyncIncomplete

                        raise TaskSyncIncomplete(result)
                    continue
                
                if config.get("special_logic"):
                    if table_name == "mtmpl":
                        result = await self.refresh_mtmpl()
                        logger.info(f"Initialized mtmpl: {result}")
                    elif table_name == "sendlog_stats":
                         # Logic handled outside this loop
                         pass
                    elif table_name == "send_log_details":
                         logger.info(f"Skipping direct initialization for {table_name}, it will be populated via logic.")
                         pass
                    continue
                
                # Fetch data
                fetch_method = config["fetch_method"]
                fetch_args = config.get("fetch_args", [])
                se2_list = await fetch_method(*fetch_args)
                
                if not se2_list:
                    logger.warning(f"No data found for {table_name} in SE2.")
                    continue
                
                # Insert data
                # Using batch_create (insert) since table is empty
                try:
                    await db_controller.batch_create(model, se2_list)
                    logger.info(f"Inserted {len(se2_list)} records into {table_name}.")
                except Exception as e:
                    logger.error(f"Failed to initialize {table_name}: {e}")
            else:
                logger.info(f"{table_name} already has data. Skipping initialization.")


        sample_stats = await db_controller.get(SendLogStats, limit=1)
        count_stats = len(sample_stats)
        
        if count_stats == 0:
             tasks = await db_controller.get(SendTask)
             sendtask_uuids = [t.sendtask_uuid for t in tasks]
             
             if sendtask_uuids:
                 # refresh_sendlog_stats manages its own session
                 sendlog_stats_status = await self.refresh_sendlog_stats(sendtask_uuids, orgs=None)
                 if "error" in sendlog_stats_status.values():
                     from backend.services.task_sync_entrypoints import TaskSyncIncomplete

                     raise TaskSyncIncomplete(sendlog_stats_status)
                 logger.info(f"Updated sendlog_stats with status: {sendlog_stats_status}")

    async def get_se2_accts(self, acct_columns=None) -> list[dict]:
        """
        從 SE2 獲取 accts 資料
        :param acct_columns: accts 的欄位名稱
        :return: accts 資料列表
        """

        acct_columns = acct_columns or ACCTS_COLUMNS
        acct_df = await get_se2_data.get_accts()
        if acct_df is not None and not acct_df.empty:
            available_columns = [column for column in acct_columns if column in acct_df.columns]
            if "_orgs_lookup_failed" in acct_df.columns:
                available_columns.append("_orgs_lookup_failed")
            acct_list = acct_df[available_columns].to_dict(orient="records")
            for acct in acct_list:
                for key, value in acct.items():
                    if not isinstance(value, (list, dict)) and pd.isna(value):
                        acct[key] = None

                orgs_lookup_failed = acct.pop("_orgs_lookup_failed", False)
                if orgs_lookup_failed:
                    acct.pop("orgs", None)

                # 將 SE2 的啟用狀態映射至既有資料庫欄位。
                acct["is_active"] = str(acct.get("acct_activate", "")).lower() in {"true", "1"}
                acct.pop("acct_activate", None)

                for timestamp_column in (
                    "acct_create_ut",
                    "acct_update_ut",
                    "acct_update_scrt_ut",
                    "acct_last_login_ut",
                ):
                    if acct.get(timestamp_column) is not None:
                        acct[timestamp_column] = int(acct[timestamp_column])

                if isinstance(acct.get("acct_last_login_info"), (dict, list)):
                    acct["acct_last_login_info"] = json.dumps(acct["acct_last_login_info"])

                for role_column in ("admin_role", "agent_role"):
                    if acct.get(role_column) is not None:
                        acct[role_column] = str(acct[role_column]).lower() in {"true", "1"}
            return acct_list
        return []

    async def _fetch_and_apply_metadata(self, sendtasks_df: pd.DataFrame) -> pd.DataFrame:
        """
        對 list API 的 DataFrame 補齊 metadata 3 欄（is_pause, stop_time_new, person_count）。
        pre_test_enable 不再從 metadata 補（list API 的 data 區塊已有此欄位）。
        """
        logger.info("Fetching metadata for sendtasks...")
        for index, row in sendtasks_df.iterrows():
            uuid = row["sendtask_uuid"]
            resp = await get_se2_data.get_sendtask(uuid)
            metadata = (resp or {}).get("metadata") or {}
            summary = metadata.get("summary") or {}
            if metadata:
                sendtasks_df.at[index, "is_pause"] = metadata.get("pause", False)
                sendtasks_df.at[index, "stop_time_new"] = metadata.get("stop_time_new", -1)
                sendtasks_df.at[index, "person_count"] = summary.get("person_count", 0)
            else:
                sendtasks_df.loc[index, ["is_pause", "stop_time_new", "person_count"]] = [False, -1, 0]
        
        logger.info("Metadata fetched and applied successfully.")
        return sendtasks_df

    async def _build_sendtask_record_from_detail(self, uuid: str) -> dict | None:
        """
        從 SE2 get_sendtask 單筆 API 組出符合 SENDTASKS_COLUMNS 的完整 dict。
        回傳 None 表示 404 或 API 失敗。
        """
        resp = await get_se2_data.get_sendtask(uuid)
        if not resp:
            return None
        if resp.get("error", {}).get("code") == 404:
            return None

        data = resp.get("data") or {}
        metadata = resp.get("metadata") or {}
        summary = metadata.get("summary") or {}

        return {
            # from data
            "sendtask_uuid": data.get("sendtask_uuid", uuid),
            "sendtask_id": data.get("sendtask_id"),
            "sendtask_owner_gid": data.get("sendtask_owner_gid"),
            "sendtask_create_ut": data.get("sendtask_create_ut"),
            "pre_test_enable": data.get("pre_test_enable", False),  # 從 data 取
            "pre_test_start_ut": data.get("pre_test_start_ut"),
            "pre_test_end_ut": data.get("pre_test_end_ut"),
            "pre_send_end_ut": data.get("pre_send_end_ut"),
            "test_start_ut": data.get("test_start_ut"),
            "test_end_ut": data.get("test_end_ut"),
            "send_end_ut": data.get("send_end_ut"),
            "sendtask_public": data.get("sendtask_public"),
            "server_url": data.get("server_url"),
            # from metadata
            "is_pause": metadata.get("pause", False),
            "stop_time_new": metadata.get("stop_time_new", -1),
            "person_count": summary.get("person_count", 0),
        }

    async def _build_testcase_detail_fields(self, uuid: str) -> dict | None:
        """
        從 SE2 get_testcase 取得專案完整資料，僅回傳 TESTCASE_DETAIL_COLUMNS 中定義的欄位。
        供任務啟動當下一次性同步進 sendtasks 用，回傳 None 表示 API 失敗或無資料。
        """
        data = await get_se2_data.get_testcase(uuid)
        if not data:
            return None
        return {col: data.get(col) for col in TESTCASE_DETAIL_COLUMNS}

    async def _sync_sendtask_from_se2(self, uuid: str) -> bool:
        statuses = await self.sync_tasks([uuid], orgs=None)
        return statuses.get(uuid) in {"added", "updated", "recreated"}

    async def get_se2_sendtasks(self, column_names=None, days=7) -> list[dict]:
        """
        從 SE2 獲取 sendtasks 資料
        :param sendtasks_columns: sendtasks 的欄位名稱
        :param days: 查詢的天數(目前預設7天)
        :return: sendtasks 資料列表
        """

        sendtasks_df = await get_se2_data.get_sendtasks()
        if sendtasks_df is not None and not sendtasks_df.empty:
            sendtasks_df = await self._fetch_and_apply_metadata(sendtasks_df)

            # 取得當前時間戳
            now = int(time.time())
            # 計算抓取任務範圍的時間戳
            ago = now - (days * 24 * 60 * 60)  # days轉換為秒
            # 過濾條件(test_end_ut >= days)(結束時間為days天內)
            filtered_df = sendtasks_df.query(
                "((test_end_ut >= @ago) or (stop_time_new >= @ago))"
            )
            logger.info(f"Total sendtasks fetched: {len(filtered_df)}")

            # 如果沒有符合條件的資料，則返回空列表
            if filtered_df.empty:
                return []
            sendtasks_list = filtered_df[column_names].to_dict(orient="records")
            return sendtasks_list
        return []

    async def sync_sendtasks(self, orgs: list[str] | None = None) -> dict:
        if self.task_list_sync is None:
            from backend.services.task_list_sync import TaskListSyncService

            self.task_list_sync = TaskListSyncService(self.get_task_sync())
        from backend.services.task_sync_entrypoints import TaskSyncStatuses, TaskSyncCancelled
        import asyncio

        committed = TaskSyncStatuses()

        async def record(result):
            committed[result.task_uuid] = result.status
            committed.results[result.task_uuid] = result

        try:
            return await self.task_list_sync.sync(orgs=orgs, on_result=record)
        except asyncio.CancelledError as exc:
            if isinstance(getattr(exc, "results", None), TaskSyncStatuses):
                committed.merge(exc.results)
            raise TaskSyncCancelled(committed) from None
    
    # Mtmpl model 允許的欄位名稱（來自 SE2 同步）
    _MTMPL_FIELDS = {
        "mtmpl_uuid", "mtmpl_name", "mtmpl_tag", "mtmpl_title", "mtmpl_content",
        "mtmpl_activate", "mtmpl_mail_attached", "mtmpl_create_ut", "mtmpl_update_ut",
        "mtmpl_owner_gid", "mtmpl_public", "mtmpl_plain", "mtmpl_embedded_img",
        "mtmpl_readonly", "mail_from", "mail_from_address",
    }

    async def get_se2_mtmpl(self) -> list[dict]:
        """
        從 SE2 獲取郵件範本資料
        :return: 符合 Mtmpl model 欄位的 list of dict
        """
        raw_list = await get_se2_data.get_mailtmpls()
        if not raw_list:
            return []

        # 過濾只保留 model 支援的欄位，避免寫入時報錯
        filtered = []
        for item in raw_list:
            record = {k: v for k, v in item.items() if k in self._MTMPL_FIELDS}
            if record.get("mtmpl_uuid"):
                filtered.append(record)
        return filtered

    async def refresh_mtmpl(self) -> dict:
        """
        全量同步郵件範本資料到 DB（upsert by mtmpl_uuid），並回傳新增與刪除摘要。
        """
        mtmpl_list = await self.get_se2_mtmpl()
        if not mtmpl_list:
            logger.warning("No mtmpl data fetched from SE2.")
            return {
                "upserted": 0,
                "synced_count": 0,
                "added_count": 0,
                "added_templates": [],
                "removed_count": 0,
                "removed_templates": [],
            }

        local_rows = await db_controller.get(Mtmpl)
        local_by_uuid = {row.mtmpl_uuid: row for row in local_rows}
        remote_by_uuid = {item["mtmpl_uuid"]: item for item in mtmpl_list}

        def template_summary(template, template_uuid=None):
            if isinstance(template, dict):
                title = template.get("mtmpl_name") or template.get("mtmpl_title")
                uuid_value = template.get("mtmpl_uuid") or template_uuid
            else:
                title = getattr(template, "mtmpl_name", None) or getattr(template, "mtmpl_title", None)
                uuid_value = getattr(template, "mtmpl_uuid", None) or template_uuid
            return {
                "mtmpl_uuid": uuid_value,
                "title": title or "未命名樣板",
            }

        added_uuids = set(remote_by_uuid) - set(local_by_uuid)
        removed_uuids = set(local_by_uuid) - set(remote_by_uuid)
        added_templates = [
            template_summary(remote_by_uuid[template_uuid], template_uuid)
            for template_uuid in sorted(added_uuids)
        ]
        removed_templates = [
            template_summary(local_by_uuid[template_uuid], template_uuid)
            for template_uuid in sorted(removed_uuids)
        ]

        update_cols = [c for c in mtmpl_list[0].keys() if c != "mtmpl_uuid"]
        await db_controller.upsert(
            Mtmpl,
            mtmpl_list,
            index_elements=["mtmpl_uuid"],
            update_columns=update_cols,
        )
        for template_uuid in removed_uuids:
            await db_controller.delete(Mtmpl, {"mtmpl_uuid": template_uuid})

        logger.info(f"Upserted {len(mtmpl_list)} mtmpl records.")
        return {
            "upserted": len(mtmpl_list),
            "synced_count": len(mtmpl_list),
            "added_count": len(added_templates),
            "added_templates": added_templates,
            "removed_count": len(removed_templates),
            "removed_templates": removed_templates,
        }

    
    async def get_se2_sendlog(self, sendtask_uuid: str, sendlog_columns=None) -> list[dict]:
        """
        從 SE2 獲取 sendlog 資料
        :param sendtask_uuid: sendtask 的 UUID
        :param sendlog_columns: sendlog 的欄位名稱
        :return: sendlog 資料列表
        """
        sendlog_df = await get_se2_data.get_sendlog(sendtask_uuid)
        if sendlog_df is not None and not sendlog_df.empty:
            sendlog_list = sendlog_df[sendlog_columns].to_dict(orient="records")
            return sendlog_list
        return []

## sendtask 相關操作
    async def refresh_today_create_task(self):
        start_ts, end_ts = timestamp()
        return await self.get_task_sync().reader.read_sendtasks(start_time=start_ts, end_time=end_ts)

    async def sync_today_created_tasks(self, *, orgs):
        from backend.services.task_sync_entrypoints import summarize_task_sync

        tasks = await self.refresh_today_create_task()
        if orgs is not None:
            tasks = [task for task in tasks if set(task.get("sendtask_owner_gid") or []).intersection(orgs)]
        statuses = await self.sync_tasks([task["sendtask_uuid"] for task in tasks], orgs=orgs)
        return {"today_count": len(tasks), **summarize_task_sync(statuses, tasks)}

    async def search_sendtasks_by_keyword(self, keyword: str) -> list[dict]:
        return await self.get_task_sync().reader.read_sendtasks(keyword=keyword)

    async def upsert_sendtasks_by_uuids(self, uuids: list[str], *, orgs=None) -> dict:
        statuses = await self.sync_tasks(uuids, orgs=orgs)
        return {
            "upserted": [task_uuid for task_uuid, status in statuses.items() if status in {"added", "updated", "recreated"}],
            "not_found": [task_uuid for task_uuid, status in statuses.items() if status in {"backed_up", "unchanged"}],
            "statuses": statuses,
        }

## sendlog and sendlog_stats相關操作
    async def check_sendlog(self, uuids_and_create_time: dict, ignore_archived: bool = False, *, orgs=None):
        return await self.sync_tasks(list(uuids_and_create_time), orgs=orgs)

    async def sendlog_write(self, sendtask_uuid: list, *, orgs=None) -> dict:
        return await self.sync_tasks(sendtask_uuid, orgs=orgs)

    async def refresh_sendlog_stats(self, uuids: list[str] = None, ignore_archived: bool = False, skip_sendtask_sync: bool = False, *, orgs=None, on_result=None) -> dict:
        """Compatibility flags never bypass generation checks; all writes use the core."""
        if uuids is None:
            tasks = await db_controller.get(SendTask)
            uuids = [task.sendtask_uuid for task in tasks if orgs is None or set(task.sendtask_owner_gid or []).intersection(orgs)]
        return await self.sync_tasks(uuids, orgs=orgs, on_result=on_result)

    async def get_sendlog(self, sendtask_uuid: str, need_id=True, use_cache=True):
        from backend.services.task_details_cache import TaskDetailsCache

        factory = getattr(self.task_sync, "session_factory", None) or db_controller.get_session
        return await TaskDetailsCache(factory, RedisClient().get_client).get(
            sendtask_uuid, need_id=need_id, use_cache=use_cache,
        )

## user相關操作
    async def get_registered_account(
        self,
        *,
        acct_uuid: str | None = None,
        acct_id: str | None = None,
    ):
        """以穩定 UUID 或登入帳號取得本機 User 與權威 Acct 資料。"""
        if not acct_uuid and not acct_id:
            raise ValueError("acct_uuid 或 acct_id 至少需要提供一個")

        stmt = select(User, Acct).join(Acct, User.acct_uuid == Acct.acct_uuid)
        if acct_uuid:
            stmt = stmt.where(User.acct_uuid == acct_uuid)
        else:
            stmt = stmt.where(func.lower(Acct.acct_id) == acct_id.lower())

        async with db_controller.get_session() as session:
            result = await session.execute(stmt.limit(1))
            return result.first()

    async def user_exists(self, username: str) -> bool:
        """
        檢查使用者是否存在
        :param username: 使用者名稱
        :return: 如果使用者存在，返回 True，否則返回 False
        """
        return await self.get_registered_account(acct_id=username) is not None

    async def insert_user(self, username: str, password_hash: str):
        """
        插入新使用者
        :param username: 使用者名稱
        :param password_hash: 密碼哈希值
        """
        # 檢查 acct 是否存在
        accounts = await db_controller.execute_scalars(
            select(Acct).where(func.lower(Acct.acct_id) == username.lower()).limit(1)
        )
        acct = accounts[0] if accounts else None

        if not acct:
            logger.error(f"acct_id {username} does not exist in the main system (accts).")
            return {"status": "error", "message": "帳號不存在在主系統"}
        
        try:
            new_user = await db_controller.create(User, {
                "acct_uuid": acct.acct_uuid,
                "username": acct.acct_id,
                "password_hash": password_hash,
            })
            
            return {
                "status": "success", 
                "message": "註冊成功", 
                "acct_uuid": new_user.acct_uuid, 
                "username": new_user.username
            }
        except Exception as e:
             return {"status": "error", "message": str(e)}
    
    async def get_all_users_with_registration_status(self):
        """
        從 'accts' 獲取所有帳戶，並檢查他們在 'users' 中的註冊狀態。
        """
        # Fetch all accounts
        accts = await db_controller.get(Acct, order_by=Acct.acct_full_name)
        
        # Fetch all registered user uuids
        users = await db_controller.get(User)
        registered_uuids = set(user.acct_uuid for user in users)
        
        # Merge and transform
        result = []
        for acct in accts:
            acct_uuid = acct.acct_uuid
            row = {
                "acct_uuid": acct_uuid,
                "acct_id": acct.acct_id,
                "acct_full_name": acct.acct_full_name,
                "acct_email": acct.acct_email,
                "is_active": acct.is_active, 
                "orgs": acct.orgs,
                "is_registered": acct_uuid in registered_uuids
            }
            result.append(row)
            
        return result
    

    async def clear_trigger_data(self, uuid: str, sendtask_uuid: str):
        """
        清除指定受測者(uuid)的所有觸發紀錄 (包含主系統與 Dashboard)
        並清除 Redis 快取
        """
        try:
            await db_controller.update(SendLogDetail, {"uuid": uuid}, {
                "second_access_time": None, "second_access_src": None, "second_access_dev": None,
                "second_input_time": None, "second_input_src": None, "second_input_dev": None, "second_input_info": None,
                "second_qrcode_time": None, "second_qrcode_src": None, "second_qrcode_dev": None
            })
            logger.info(f"Cleared trigger data for uuid: {uuid}")
        except Exception as e:
            logger.error(f"Failed to clear trigger data in DB for {uuid}: {e}")
            raise e

        # 3. 清除 Redis 快取
        if sendtask_uuid:
            try:
                cache_key = f"task:{sendtask_uuid}:details"
                from backend.services.redis_client import RedisClient
                redis_client = RedisClient()
                client = await redis_client.get_client()
                await client.delete(cache_key)
                logger.info(f"Invalidated Redis cache for task {sendtask_uuid} after clearing trigger data")
            except Exception as e:
                logger.warning(f"Failed to invalidate Redis cache for {sendtask_uuid}: {e}")

        return True

## customer 相關操作
    async def customer_exists(self, customer_name: str) -> bool:
        """
        檢查客戶是否存在
        :param customer_name: 客戶名稱
        :return: 如果客戶存在，返回 True，否則返回 False
        """
        customer = await db_controller.get_one(CustomerAcct, {"customer_name": customer_name})
        return customer is not None

    async def insert_customer(self, data: dict):
        """
        插入新客戶
        :param data: 客戶資料
        :return: 
        """
        try:
            new_customer = await db_controller.create(CustomerAcct, {
                "customer_uuid": uuid.uuid4().hex,
                "customer_name": data.get("customer_name"),
                "customer_full_name": data.get("customer_full_name"),
                "password_hash": data.get("password_hash"),
                "acct_uuid": data.get("acct_uuid")
            })
            return {"status": "success", "message": "新增客戶成功", "customer_name": new_customer.customer_name}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def update_customer_sendtasks(self, customer_name: str, sendtask_data: List[Dict[str, Any]]):
        """
        更新客戶的任務列表，將其存為 JSONB 格式。
        :param customer_name: 客戶名稱
        :param sendtask_data: 任務物件的列表 (List of Dictionaries)
        """
        # 檢查是否存在    
        customer = await db_controller.get_one(CustomerAcct, {"customer_name": customer_name})

        if not customer:
            logger.error(f"Customer {customer_name} does not exist.")
            return {"status": "error", "message": "客戶不存在"}
        
        try:
            await db_controller.update(CustomerAcct, {"customer_name": customer_name}, {"sendtasks": sendtask_data})
            return "success"
        except Exception as e:
            logger.error(f"Update customer sendtasks failed: {e}")
            return {"status": "error", "message": str(e)}

    async def update_customer_task_creation(self, customer_name: str, enabled: bool, org_uuid: str = None, allowed_email_domains: list[str] = None, max_task_count: int = None):
        """
        更新客戶的「建立任務功能」開關狀態與指定組織。
        :param customer_name: 客戶名稱
        :param enabled: 是否啟用建立任務功能
        :param org_uuid: 關聯的組織 uuid
        :param allowed_email_domains: 允許的 Email domain 清單
        :param max_task_count: 可建立任務數量上限（None / 0 = 不限制）
        """
        customer = await db_controller.get_one(CustomerAcct, {"customer_name": customer_name})

        if not customer:
            logger.error(f"Customer {customer_name} does not exist.")
            return {"status": "error", "message": "客戶不存在"}

        try:
            update_data = {"task_creation_enabled": enabled}
            if org_uuid is not None:
                update_data["task_creation_org_uuid"] = org_uuid
            if allowed_email_domains is not None:
                update_data["allowed_email_domains"] = allowed_email_domains
            if max_task_count is not None:
                update_data["max_task_count"] = max_task_count
            await db_controller.update(CustomerAcct, {"customer_name": customer_name}, update_data)
            return {"status": "success", "message": f"客戶 {customer_name} 建立任務功能設定已更新"}
        except Exception as e:
            logger.error(f"Update customer task_creation_enabled failed: {e}")
            return {"status": "error", "message": str(e)}

    async def update_password(self, user_type: str, identifier: str, new_password: str, old_password: str = None, acct_uuid: str = None) -> dict:
        """
        統一的密碼更新方法，支援一般用戶和客戶
        :param user_type: 用戶類型 ("user" 或 "customer")
        :param identifier: 用戶識別符（acct_uuid 或 customer_name）
        :param new_password: 新密碼
        :param old_password: 舊密碼（可選，用於驗證）
        :param acct_uuid: 用戶的 UUID（可選，用於權限驗證）
        :return: 更新結果
        """
        
        try:
            target_user = None
            model = None
            filter_key = None
            
            if user_type == "user":
                model = User
                filter_key = "acct_uuid"
            elif user_type == "customer":
                model = CustomerAcct
                filter_key = "customer_name"
            else:
                return {"status": "error", "message": "無效的用戶類型"}
                
            target_user = await db_controller.get_one(model, {filter_key: identifier})
            
            if not target_user:
                return {"status": "error", "message": f"{'用戶' if user_type == 'user' else '客戶'}不存在"}
            
            # 進行驗證舊密碼
            if old_password:
                if not verify_password(old_password, target_user.password_hash):
                    return {"status": "error", "message": "舊密碼不正確"}
                
                if old_password == new_password:
                    return {"status": "error", "message": "新密碼不能與舊密碼相同"}
            
            # 更新密碼
            new_password_hash = hash_password(new_password)
            
            await db_controller.update(model, {filter_key: identifier}, {"password_hash": new_password_hash})
            
            logger.info(f"Password updated successfully for {user_type}: {identifier}")
            return {
                "status": "success", 
                "message": "密碼更新成功", 
                "identifier": identifier,
                "user_type": user_type
            }
                
        except Exception as e:
            logger.error(f"Error updating password for {user_type} {identifier}: {str(e)}")
            return {"status": "error", "message": str(e)}
            return {"status": "error", "message": f"更新密碼時發生錯誤: {str(e)}"}

    async def add_login_log(self, username: str, action: str, status: str, ip_address: str = None, details: str = None):
        """
        登入/登出紀錄
        :param username: 使用者名稱
        :param action: 動作 ('login', 'logout')
        :param status: 狀態 ('success', 'failed')
        :param ip_address: IP 位址
        :param details: 詳細資訊
        """
        try:
            await db_controller.create(LoginLog, {
                "username": username, 
                "action": action, 
                "status": status, 
                "ip_address": ip_address, 
                "details": details
            })
            logger.info(f"Added login log: {username} {action} {status}")
        except Exception as e:
            logger.error(f"Error adding login log: {str(e)}")

    async def get_login_logs(self, limit: int = 100):
        """
        取得登入/登出紀錄
        :param limit: 限制筆數
        :return: 紀錄列表
        """
        try:
            result = await db_controller.get(LoginLog, limit=limit, order_by=LoginLog.create_time.desc())
            
            # Convert to dict list
            logs = []
            for row in result:
                 logs.append({
                     "username": row.username,
                     "action": row.action,
                     "status": row.status,
                     "ip_address": row.ip_address,
                     "details": row.details,
                     "create_time": row.create_time
                 })
            return logs
            
        except Exception as e:
            logger.error(f"Error fetching login logs: {str(e)}")
            return []
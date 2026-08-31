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
    def __init__(self):
        """ 
        初始化 DBUser 類別
        """
        self.day = 7  # 預設查詢天數為 7 天
        self.accts_columns = ACCTS_COLUMNS
        
    async def table_initialize(self):
        """
        初始化資料表
        檢查資料表是否為空，如果是空的，則從 SE2 獲取資料並插入到資料表中。
        如果資料表已經有資料，則跳過初始化。
        """
        table_mappings = {
            "accts": {"model": Acct, "fetch_method": self.get_se2_accts, "fetch_args": [ACCTS_COLUMNS]},
            "sendtasks": {"model": SendTask, "fetch_method": self.get_se2_sendtasks, "fetch_args": [SENDTASKS_COLUMNS, self.day]},
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
                 sendlog_stats_status = await self.refresh_sendlog_stats(sendtask_uuids)
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
        """
        從 SE2 取單筆，更新 SendTask 全欄位。
        回傳 True 成功 / False 表示 404 或 API 失敗。
        不會覆寫 is_archived（不在 SENDTASKS_COLUMNS 中）。
        """
        record = await self._build_sendtask_record_from_detail(uuid)
        if record is None:
            return False
        await db_controller.update(SendTask, {"sendtask_uuid": uuid}, record)
        return True

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
        """
        檢查 7 天內 SendTask 清單，只對「內容有變動」的 row upsert。
        1. 從 SE2 list API 拿 7 天內任務（_fetch_and_apply_metadata 補 metadata 3 欄）
        2. 依 orgs 過濾
        3. 與本地 SendTask 做 dict-level diff：
           - added：SE2 有但本地沒有的 uuid（全新任務）
           - changed：SE2 與本地同 uuid 但欄位值不同
           - removed：本地有但 SE2 7 天窗口內沒有的 uuid
        4. (added + changed) → upsert SendTask
        5. removed → 逐一確認 404/archive
        回傳: {"added": [...], "changed": [...], "archived": N, "deleted": N}
        """
        from backend.api.data_api import has_common_orgs

        remote_tasks = await self.get_se2_sendtasks(SENDTASKS_COLUMNS)
        if orgs is not None:
            remote_tasks = [t for t in remote_tasks
                            if has_common_orgs(t.get("sendtask_owner_gid", []), orgs)]

        # 本地 SendTask（只取 SENDTASKS_COLUMNS 的欄位做比對，並加入 is_archived 給封存邏輯用）
        local_rows = await db_controller.get(SendTask)
        local_map = {}
        for row in local_rows:
            local_map[row.sendtask_uuid] = {
                c: getattr(row, c, None) for c in SENDTASKS_COLUMNS
            }
            local_map[row.sendtask_uuid]["is_archived"] = getattr(row, "is_archived", False)

        remote_map = {t["sendtask_uuid"]: t for t in remote_tasks}

        # 判斷有變動的 row（含全新 + 欄位值改變）
        def normalize(v):
            if isinstance(v, list):
                return tuple(v)
            try:
                if pd.isna(v):  # 處理 NaN 等同 None
                    return None
            except (ValueError, TypeError):
                pass
            return v

        def row_changed(remote: dict, local: dict | None) -> bool:
            if local is None:
                return True  # 新任務
            for col in SENDTASKS_COLUMNS:
                if normalize(remote.get(col)) != normalize(local.get(col)):
                    return True
            return False

        added_list = []
        changed_list = []
        for uuid, remote in remote_map.items():
            local = local_map.get(uuid)
            if local is None:
                added_list.append(remote)
            elif row_changed(remote, local):
                changed_list.append(remote)

        upsert_list = added_list + changed_list
        if upsert_list:
            update_cols = [c for c in SENDTASKS_COLUMNS if c != "sendtask_uuid"]
            await db_controller.upsert(
                SendTask,
                upsert_list,
                index_elements=["sendtask_uuid"],
                update_columns=update_cols,
            )

        # removed：本地有但遠端 7 天窗口內沒有
        missing_uuids = set(local_map.keys()) - set(remote_map.keys())
        del_count = archive_count = 0
        for uuid in missing_uuids:
            data = await get_se2_data.get_sendtask(uuid)
            if data and data.get("error", {}).get("code") == 404:
                await db_controller.delete(SendTask, {"sendtask_uuid": uuid})
                await db_controller.delete(SendLogStats, {"sendtask_uuid": uuid})
                await db_controller.delete(SendLogDetail, {"sendtask_uuid": uuid})
                del_count += 1
            elif data is None:
                logger.warning(f"SE2 returned None for {uuid}, skipping.")
            else:
                # 只 archive 還沒被 archive 的
                local = local_map.get(uuid)
                if not local.get("is_archived"):
                    await db_controller.update(SendTask, {"sendtask_uuid": uuid}, {"is_archived": True})
                    archive_count += 1

        return {
            "added": added_list,
            "changed": changed_list,
            "archived": archive_count,
            "deleted": del_count,
        }
    
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
        全量同步郵件範本資料到 DB（upsert by mtmpl_uuid）
        :return: {"upserted": N}
        """
        mtmpl_list = await self.get_se2_mtmpl()
        if not mtmpl_list:
            logger.warning("No mtmpl data fetched from SE2.")
            return {"upserted": 0}

        update_cols = [c for c in mtmpl_list[0].keys() if c != "mtmpl_uuid"]
        await db_controller.upsert(
            Mtmpl,
            mtmpl_list,
            index_elements=["mtmpl_uuid"],
            update_columns=update_cols,
        )
        logger.info(f"Upserted {len(mtmpl_list)} mtmpl records.")
        return {"upserted": len(mtmpl_list)}

    
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
        """從 SE2 獲取當天建立的 sendtasks"""
        start_ts, end_ts = timestamp()
        logger.info(f"Refreshing tasks created between {start_ts} and {end_ts}")

        today_create_tasks_df = await get_se2_data.get_sendtasks(end_time=end_ts, start_time=start_ts)
        if today_create_tasks_df is None or today_create_tasks_df.empty:
            logger.info("No new tasks created today found on SE2.")
            return []

        today_create_tasks_df = await self._fetch_and_apply_metadata(today_create_tasks_df)
        today_create_tasks_list = today_create_tasks_df[SENDTASKS_COLUMNS].to_dict(orient="records")
        return today_create_tasks_list

    async def search_sendtasks_by_keyword(self, keyword: str) -> list[dict]:
        """依關鍵字向 SE2 查詢任務（不限定日期），用於快速確認任務是否已建立"""
        tasks_df = await get_se2_data.get_sendtasks(keyword=keyword)
        if tasks_df is None or tasks_df.empty:
            return []
        tasks_df = await self._fetch_and_apply_metadata(tasks_df)
        return tasks_df[SENDTASKS_COLUMNS].to_dict(orient="records")

    async def upsert_sendtasks_by_uuids(self, uuids: list[str]) -> dict:
        """依 uuid 清單，逐一向 SE2 取得最新單筆資料後 upsert 進本地 sendtasks 表"""
        records = []
        not_found = []
        for u in uuids:
            record = await self._build_sendtask_record_from_detail(u)
            if record is None:
                not_found.append(u)
            else:
                records.append(record)
        if records:
            await db_controller.upsert(SendTask, records, index_elements=["sendtask_uuid"])
        return {"upserted": [r["sendtask_uuid"] for r in records], "not_found": not_found}

## sendlog and sendlog_stats相關操作
    async def check_sendlog(self, uuids_and_create_time: dict, ignore_archived: bool = False):
        """
        檢查 sendlog table 是否存在於資料庫中
        :param uuids_and_create_time: sendtask 的 UUID，對應建立時間的字典
        """
        logger.info("Checking sendlog tables...")
        
        statuses = {}
        # 0. 先過濾掉已封存的任務 (Safety Check)
        target_uuids = list(uuids_and_create_time.keys())
        if not target_uuids:
             return {}
        
        if not ignore_archived:
            # 查詢所有傳入的 UUID 中，有哪些已經是 is_archived = TRUE
            # Use DBController get with in_ filter (assumes DBController supports list for IN)
            archived_tasks = await db_controller.get(SendTask, {"sendtask_uuid": target_uuids, "is_archived": True})
            archived_uuids = set(t.sendtask_uuid for t in archived_tasks)
            for uuid in archived_uuids:
                statuses[uuid] = "archived"
            
            # 只保留未封存的任務
            active_uuids_and_time = {
                u: t for u, t in uuids_and_create_time.items() 
                if u not in archived_uuids
            }
                
            if len(active_uuids_and_time) < len(uuids_and_create_time):
                logger.info(f"Skipped {len(uuids_and_create_time) - len(active_uuids_and_time)} archived tasks in check_sendlog.")
        else:
            logger.info("ignore_archived is True. Not filtering archived tasks.")
            active_uuids_and_time = uuids_and_create_time

        # 批次檢查所有資料表是否存在
        for uuid, create_ut in active_uuids_and_time.items():
            data = await get_se2_data.get_sendtask(uuid)
            if data and data.get("error", {}).get("code") == 404:
                logger.warning(f"Task {uuid} not found on SE2 (404). Deleting local data.")
                # 該任務在主系統已不存在，刪除本地所有相關資料
                
                # Delete from sendtasks
                await db_controller.delete(SendTask, {"sendtask_uuid": uuid})
                # Delete from sendlog_stats
                await db_controller.delete(SendLogStats, {"sendtask_uuid": uuid})
                # Delete from send_log_details
                await db_controller.delete(SendLogDetail, {"sendtask_uuid": uuid})

                statuses[uuid] = "deleted"
                continue # 繼續處理下一個 uuid
            
            if data is None:
                logger.error(f"Failed to get task info for {uuid} from SE2, likely a token or connection issue. Skipping.")
                statuses[uuid] = "error"
                continue

            remote_create_ut = data.get("data", {}).get("sendtask_create_ut")
            if create_ut != remote_create_ut:
                log_message = f"Task {uuid} has a new create time. Local: {create_ut}, Remote: {remote_create_ut}. Re-syncing task."
                logger.warning(log_message)
                
                telegram_message = f"🔄 *任務已重同步*\n任務 `{escape_markdown_v2(uuid)}` 的建立時間不符，已觸發資料重同步。"
                await send_telegram_notification(telegram_message)
                
                # 獲取新任務資料並更新 sendtasks 表
                task_data_df = pd.DataFrame([data.get("data", {})])
                updated_task_df = await self._fetch_and_apply_metadata(task_data_df)
                if not updated_task_df.empty:
                    task_to_update = updated_task_df[SENDTASKS_COLUMNS].to_dict(orient="records")[0]
                    # Use ORM update
                    await db_controller.update(SendTask, {"sendtask_uuid": uuid}, task_to_update)
                    logger.info(f"Updated sendtasks table for {uuid}.")
            
        # sendlog_write now handles its own session, but we call it here.
        # To avoid nested sessions issues if not handled (db.get_session creates new one),
        # we can pass session or just let it create new one. sendlog_write creates its own.
        logger.info("Upserting sendlog tables...")
        # 只處理未被刪除或未出錯的任務
        sendtask_uuids_to_write = [uuid for uuid in active_uuids_and_time.keys() if statuses.get(uuid) not in ["deleted", "error"]]
    
        # Call sendlog_write (it manages its own transaction)
        write_statuses = await self.sendlog_write(sendtask_uuids_to_write)
        statuses.update(write_statuses)
        logger.info(f"Sendlog tables upserted with statuses: {statuses}")
        return statuses  # 返回狀態

    async def sendlog_write(self, sendtask_uuid: list) -> dict:
        """
        更新 sendlog 資料到資料庫
        :param sendtask_uuid: 任務清單的uuid列表
         """
        sendlog_status = {}
        sendlog_status = {}
        # sendlog_write now uses db_controller
        
        for uuid in sendtask_uuid:
            # 獲取 sendlog 資料 (From SE2 API)
            sendlog = await self.get_se2_sendlog(uuid, sendlog_columns=SENDLOG_COLUMNS)
            
            if sendlog:
                sendlog_status[uuid] = "unchanged"
                
                sendlog_data_list = []
                for log in sendlog:
                    # 準備寫入資料
                    log_data = log.copy()
                    log_data["sendtask_uuid"] = uuid
                    sendlog_data_list.append(log_data)
                
                # 使用 db_controller.upsert
                if sendlog_data_list:
                     await db_controller.upsert(
                        SendLogDetail,
                        sendlog_data_list,
                        index_elements=['uuid'],
                        update_columns=[c for c in sendlog_data_list[0].keys() if c != 'uuid']
                    )

            else:
                logger.warning(f"No valid columns found in sendlog for task {uuid}")

        return sendlog_status

    async def refresh_sendlog_stats(self, uuids: list[str] = None, ignore_archived: bool = False, skip_sendtask_sync: bool = False) -> dict:
        """
        刷新 sendlog_stats 資料
        :param uuid: 如果提供，則僅刷新指定的 sendtask_uuid；如果為 None，則刷新所有 sendtask 的統計資料
        :return: sendlog_stats 的更新狀態
        """
        if uuids is not None and len(uuids) == 0:
            logger.info("Empty UUIDs list provided to refresh_sendlog_stats. Skipping.")
            return {}

        if uuids is None:
            logger.info("Fetching all sendtask uuids for refresh...")
            sendtask_data = await db_controller.get(SendTask)
        else:
            logger.info(f"Refreshing sendlog_stats for specified uuids: {uuids}")
            sendtask_data = await db_controller.get(SendTask, {"sendtask_uuid": uuids})

        # Convert to dict for easier access locally
        uuids_and_create_time = {task.sendtask_uuid: task.sendtask_create_ut for task in sendtask_data}
        # 取得任務名稱，用於通知
        task_names = {task.sendtask_uuid: task.sendtask_id for task in sendtask_data}

        # 確保 sendlog 資料表存在，同時更新資料表 (check_sendlog handles its own session)
        check_statuses = await self.check_sendlog(uuids_and_create_time, ignore_archived=ignore_archived)


        # 開始刷新 sendlog_stats
        for uuid in uuids_and_create_time.keys():
            if check_statuses.get(uuid) in ["deleted", "error", "archived"]:
                continue

            try:
            # logger.info(f"Refreshing sendlog_stats for {uuid}")

            # 同步 SE2 metadata（全欄位更新）
                if not skip_sendtask_sync:
                    await self._sync_sendtask_from_se2(uuid)

            # 1. 獲取舊的統計數據
                old_stats = await db_controller.get_one(SendLogStats, {"sendtask_uuid": uuid})
                old_todaysend = old_stats.todaysend if old_stats else 0

            # 2. 計算新的統計數據
            # get_sendlog implementation is below, it uses session internally or creates one
                data = await self.get_sendlog(sendtask_uuid=uuid, need_id=False, use_cache=False)
                new_stats = calc_stats(data)

            # 3. 比較並觸發通知
                new_todaysend = new_stats.get("todaysend", 0)
                if old_todaysend == 0 and new_todaysend > 0:
                    task_name = task_names.get(uuid, uuid)
                    message = f"🚀 *任務開始執行*\n任務 `{escape_markdown_v2(task_name)}` 今天已開始寄送第一封郵件。"
                    await send_telegram_notification(message)

            # 4. 更新資料庫
                stats_data = {
                    "sendtask_uuid": uuid,
                    **new_stats
                }
            # Upsert SendLogStats
                await db_controller.upsert(
                    SendLogStats,
                    [stats_data],
                    index_elements=['sendtask_uuid']
                )
                check_statuses[uuid] = "updated"
            except Exception as error:
                logger.error(f"Failed to refresh sendlog_stats for {uuid}: {error}")
                check_statuses[uuid] = "error"
            
        logger.info(f"Finished refreshing sendlog_stats.")

        return check_statuses

    async def get_sendlog(self, sendtask_uuid: str, need_id=True, use_cache=True):
        
        # 0. 嘗試從 Redis 讀取快取
        cache_key = f"task:{sendtask_uuid}:details"
        if use_cache:
            try:
                redis_client = RedisClient()
                client = await redis_client.get_client()
                
                cached_data = await client.get(cache_key)
                if cached_data:
                    logger.debug(f"Cache Hit for {sendtask_uuid}")
                    return json.loads(cached_data)
            except Exception as e:
                logger.warning(f"Redis cache miss/error for {sendtask_uuid}: {e}")
        else:
            # 如果不使用快取，還是需要 client 來寫入
            try:
                from backend.services.redis_client import RedisClient
                redis_client = RedisClient()
                client = await redis_client.get_client()
            except Exception as e:
                logger.warning(f"Failed to initialize Redis client: {e}")

        # 1. DB 查詢 send_log_details using ORM
        # Use DBController
        log_records = await db_controller.get(SendLogDetail, {"sendtask_uuid": sendtask_uuid})
        
        # Convert Query Result to list of dicts for compatibility with existing logic
        data = []
        for row in log_records:
            d = {col.name: getattr(row, col.name) for col in row.__table__.columns}
            data.append(d)
        
        # 資料沒變，先把 id 拿掉 (如果不需要的話)
        if not need_id: 
            # 注意：這裡邏輯跟原版稍微不同，原版是在 return 前 pop。
            # 但若要寫入 Cache，通常需不需要 id? Dashboard 通常不需要 id，但需要 uuid
            # 為了保持一致性，先複製一份處理
            data_to_cache = [d.copy() for d in data] if data else []
            for dd in data_to_cache:
                dd.pop("id", None)
            
            # 使用 data_to_cache 做為快取來源
            final_data = data_to_cache
        else:
            final_data = data

        # 2. 寫回 Redis
        try:
            if final_data:
                # 檢查這任務是否已封存，決定 TTL
                task = await db_controller.get_one(SendTask, {"sendtask_uuid": sendtask_uuid})
                is_archived = task.is_archived if task else False
                
                ttl = 3600 if is_archived else 86400  # 1小時 vs 1天 (Active)
                
                # 序列化
                await client.set(cache_key, json.dumps(final_data, default=str), ex=ttl)
                logger.debug(f"Cache Set for {sendtask_uuid} with TTL {ttl}")
        except Exception as e:
             logger.warning(f"Failed to set Redis cache for {sendtask_uuid}: {e}")

        return final_data

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
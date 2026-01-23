'''
Database operations for user-related data, including sendlog management.
'''

# import re
# import asyncpg
# import aiofiles
import time
import json
from typing import List, Dict, Any
from datetime import datetime, timedelta
import pandas as pd
from zoneinfo import ZoneInfo

from backend.services.log_manager import Logger
from backend.services.getSe2data import get_se2_data
from backend.repository.db_controller import ApplianceDB
from backend.core.security import verify_password, hash_password
from backend.services.notification_manager import send_telegram_notification, escape_markdown_v2
from backend.core.security import hash_password


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

    # 統計觸發人數
    trigger_fields = ["access_src", "click_src", "file_src", "second_access_src", "second_input_src"]
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
    }

# ==============================================================================
# Module Constants (模組常數)
# ==============================================================================
ACCTS_COLUMNS = ["acct_uuid", "acct_id", "acct_full_name", "acct_full_name_2nd",
                 "acct_email", "acct_activate", "orgs"]

SENDTASKS_COLUMNS = ["sendtask_uuid", "sendtask_id", "sendtask_owner_gid", "person_count",
                     "pre_test_end_ut", "pre_test_start_ut", "pre_send_end_ut", "sendtask_create_ut", 
                     "test_end_ut", "test_start_ut", "is_pause", "pre_test_enable", "stop_time_new"]



SENDLOG_COLUMNS = ["uuid", "target_email", "person_info", "template_uuid", "plan_time",
                   "send_time", "send_res", "access_time", "access_src", "access_dev",
                   "click_time", "click_src", "click_dev", "file_time", "file_src", "file_dev"]


class DBUser:
    def __init__(self, db: ApplianceDB = ApplianceDB()):
        """ 
        初始化 DBUser 類別
        :param db: ApplianceDB 實例，預設為 ApplianceDB()
        """
        self.db = db
        self.day = 7  # 預設查詢天數為 7 天
        self.accts_columns = ACCTS_COLUMNS
        
    async def table_initialize(self):
        """
        初始化資料表
        檢查資料表是否為空，如果是空的，則從 SE2 獲取資料並插入到資料表中。
        如果資料表已經有資料，則跳過初始化。
        """
        # 檢查資料庫連線
        await self.db.check_db_connection()

        table_names = ["accts", "sendtasks", "mtmpl", "sendlog_stats", "send_log_details"]
        
        # 檢查資料表是否為空，如果是空的，則從 SE2 獲取資料並插入到資料表中。
        for table_name in table_names:
            if await self.db.table_empty(table_name):
                logger.info(f"{table_name} is empty. Initializing with data from SE2...")
                if table_name == "accts":
                    # 從 SE2 獲取 accts 資料
                    se2_list = await self.get_se2_accts(ACCTS_COLUMNS)
                elif table_name == "sendtasks":
                    # 從 SE2 獲取 sendtasks 資料
                    se2_list = await self.get_se2_sendtasks(SENDTASKS_COLUMNS, days=self.day)
                elif table_name == "mtmpl":
                    # 從 SE2 獲取 mtmpl 資料
                    se2_list = await self.get_se2_mtmpl()
                elif table_name == "sendlog_stats":
                    # 取得sendtask_uuids
                    sendtask_data = await self.db.get_db("sendtasks", select_columns=["sendtask_uuid"])
                    sendtask_uuids = [t["sendtask_uuid"] for t in sendtask_data]
                    # 開始更新sendlog_stats table
                    sendlog_stats_status = await self.refresh_sendlog_stats(sendtask_uuids)
                    logger.info(f"Updated sendlog_stats with status: {sendlog_stats_status}")
                    continue
                elif table_name == "send_log_details":
                    # 這個表通常由 refresh_sendlog_stats 或 check_sendlog 填充
                    logger.info(f"Skipping direct initialization for {table_name}, it will be populated via logic.")
                    continue

                if not se2_list:
                    logger.warning(f"No data found for {table_name} in SE2.")
                    continue
                await self.db.insert_db(table_name, se2_list)
                logger.info(f"Inserted {len(se2_list)} records into {table_name}.")
            else:
                logger.info(f"{table_name} already has data. Skipping initialization.")

    async def get_se2_accts(self, acct_columns=None) -> list[dict]:
        """
        從 SE2 獲取 accts 資料
        :param acct_columns: accts 的欄位名稱
        :return: accts 資料列表
        """
        await self.db.check_db_connection()

        acct_df = await get_se2_data.get_accts()
        if acct_df is not None and not acct_df.empty:
            acct_list = acct_df[acct_columns].to_dict(orient="records")
            for acct in acct_list:
                # 將 acct_activate 欄位轉換為 is_active
                acct["is_active"] = acct.get("acct_activate", False)
                acct.pop("acct_activate", None)
            return acct_list
        return []

    async def _fetch_and_apply_metadata(self, sendtasks_df: pd.DataFrame) -> pd.DataFrame:
        """
        輔助函式
        獲取並套用 sendtask 的 metadata(get_sendtasks的api不會有metadata資料)
        :param sendtasks_df: 包含 sendtask 資料的 DataFrame
        :return: 已加上 metadata 的 DataFrame
        """
        logger.info("Fetching metadata for sendtasks...")
        for index, row in sendtasks_df.iterrows():
            uuid = row["sendtask_uuid"]
            data = await get_se2_data.get_sendtask(uuid)
            metadata = data.get("metadata") if data else None
            if metadata:
                sendtasks_df.at[index, "is_pause"] = metadata.get("pause", False)
                sendtasks_df.at[index, "stop_time_new"] = metadata.get("stop_time_new", -1)
                sendtasks_df.at[index, "person_count"] = metadata.get("summary", {}).get("person_count", 0)
                sendtasks_df.at[index, "pre_test_enable"] = metadata.get("summary", {}).get("pre_test_enable", False)
            else: # 預設值
                sendtasks_df.loc[index, ["is_pause", "stop_time_new", "person_count", "pre_test_enable"]] = [False, -1, 0, False]
        
        logger.info("Metadata fetched and applied successfully.")
        return sendtasks_df

    async def get_se2_sendtasks(self, column_names=None, days=7) -> list[dict]:
        """
        從 SE2 獲取 sendtasks 資料
        :param sendtasks_columns: sendtasks 的欄位名稱
        :param days: 查詢的天數(目前預設7天)
        :return: sendtasks 資料列表
        """
        await self.db.check_db_connection()

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
    
    async def get_se2_mtmpl(self) -> list[dict]:
        """
        從 SE2 獲取 mtmpl 資料
        """
        await self.db.check_db_connection()
        mtmpl_df = await get_se2_data.get_mtmpl_subject_list()
        if mtmpl_df is not None and not mtmpl_df.empty:
            mtmpl_list = mtmpl_df.to_dict(orient="records")
            return mtmpl_list
        return []
    
    async def get_se2_sendlog(self, sendtask_uuid: str, sendlog_columns=None) -> list[dict]:
        """
        從 SE2 獲取 sendlog 資料
        :param sendtask_uuid: sendtask 的 UUID
        :param sendlog_columns: sendlog 的欄位名稱
        :return: sendlog 資料列表
        """
        await self.db.check_db_connection()
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

## sendlog and sendlog_stats相關操作
    async def check_sendlog(self, uuids_and_create_time: dict):
        """
        檢查 sendlog table 是否存在於資料庫中，且建立時間正確
        :param uuids_and_create_time: sendtask 的 UUID，對應建立時間的字典
        """
        await self.db.check_db_connection()
        logger.info("Checking sendlog tables...")
        
        statuses = {}
        # 0. 先過濾掉已封存的任務 (Safety Check)
        # 雖然外部通常已過濾，但為了安全起見再次確認
        # 查詢所有傳入的 UUID 中，有哪些已經是 is_archived = TRUE
        target_uuids = list(uuids_and_create_time.keys())
        if not target_uuids:
             return {}
        
        archived_tasks = await self.db.get_db(
            "sendtasks", 
            select_columns=["sendtask_uuid"], 
            where_column="sendtask_uuid", 
            values=target_uuids,
            where_clauses=["is_archived = TRUE"]
        )
        archived_uuids = {t["sendtask_uuid"] for t in archived_tasks}
        
        # 只保留未封存的任務
        active_uuids_and_time = {
            u: t for u, t in uuids_and_create_time.items() 
            if u not in archived_uuids
        }
        
        if len(active_uuids_and_time) < len(uuids_and_create_time):
             logger.info(f"Skipped {len(uuids_and_create_time) - len(active_uuids_and_time)} archived tasks in check_sendlog.")

        # 批次檢查所有資料表是否存在，且建立時間正確
        tables_to_create = []
        for uuid, create_ut in active_uuids_and_time.items():
            if not await self.db.table_exists(uuid):
                tables_to_create.append(uuid)
            else:
                data = await get_se2_data.get_sendtask(uuid)
                if data and data.get("error", {}).get("code") == 404:
                    logger.warning(f"Task {uuid} not found on SE2 (404). Deleting local data.")
                    # 該任務在主系統已不存在，刪除本地所有相關資料
                    await self.db.delete_db("sendtasks", {"sendtask_uuid": uuid})
                    logger.info(f"Deleted task {uuid} from 'sendtasks' table.")
                    await self.db.delete_db("sendlog_stats", {"sendtask_uuid": uuid})
                    logger.info(f"Deleted stats for task {uuid} from 'sendlog_stats' table.")
                    if await self.db.table_exists(uuid):
                        await self.db.drop_table(uuid)
                        logger.info(f"Dropped sendlog table '{uuid}'.")
                    statuses[uuid] = "deleted"
                    message = f"🗑️ *任務已刪除*\n任務 `{escape_markdown_v2(uuid)}` 在遠端系統上找不到，本地資料已同步刪除。"
                    await send_telegram_notification(message)
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
        tables_to_create = []
        for uuid, create_ut in active_uuids_and_time.items():
            if not await self.db.table_exists(uuid):
                tables_to_create.append(uuid)
            else:
                data = await get_se2_data.get_sendtask(uuid)
                remote_create_ut = data.get("data", {}).get("sendtask_create_ut")
                if create_ut != remote_create_ut:
                    # log_message = f"Task {uuid} has a new create time. Local: {create_ut}, Remote: {remote_create_ut}. Re-syncing task."
                    # logger.warning(log_message)
                    
                    # telegram_message = f"🔄 *任務已重同步*\n任務 `{escape_markdown_v2(uuid)}` 的建立時間不符，已觸發資料重同步。"
                    # await send_telegram_notification(telegram_message)
                    
                    # 獲取新任務資料並更新 sendtasks 表
                    task_data_df = pd.DataFrame([data.get("data", {})])
                    updated_task_df = await self._fetch_and_apply_metadata(task_data_df)
                    if not updated_task_df.empty:
                        task_to_update = updated_task_df[SENDTASKS_COLUMNS].to_dict(orient="records")[0]
                        await self.db.update_db("sendtasks", task_to_update, {"sendtask_uuid": uuid})
                        logger.info(f"Updated sendtasks table for {uuid}.")

        logger.info("Upserting sendlog tables...")
        logger.info("Upserting sendlog tables...")
        # 只處理未被刪除或未出錯的任務
        sendtask_uuids_to_write = [uuid for uuid in active_uuids_and_time.keys() if statuses.get(uuid) not in ["deleted", "error"]]
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
        await self.db.check_db_connection()
        for uuid in sendtask_uuid:
            # 獲取 sendlog 資料
            sendlog = await self.get_se2_sendlog(uuid, sendlog_columns=SENDLOG_COLUMNS)
            if sendlog:
                sendlog_status[uuid] = "unchanged"
                for log in sendlog:
                    # 注入 sendtask_uuid
                    log["sendtask_uuid"] = uuid
                    # 寫入 send_log_details 表
                    # 注意：我們使用 log 中的 uuid 作為 conflict key (這是每封信的唯一識別碼)
                    status = await self.db.upsert_db("send_log_details", log, conflict_keys=["uuid"])
                    if status == "changed":
                        sendlog_status[uuid] = "changed"
            else:
                logger.warning(f"No valid columns found in sendlog for task {uuid}")

        return sendlog_status

    async def refresh_sendlog_stats(self, uuids: list[str] = None) -> dict:
        """
        刷新 sendlog_stats 資料
        :param uuid: 如果提供，則僅刷新指定的 sendtask_uuid；如果為 None，則刷新所有 sendtask 的統計資料
        :return: sendlog_stats 的更新狀態
        """
        await self.db.check_db_connection()
        if uuids is not None and len(uuids) == 0:
            logger.info("Empty UUIDs list provided to refresh_sendlog_stats. Skipping.")
            return {}

        if uuids is None:
            logger.info("Fetching all sendtask uuids for refresh...")
            sendtask_data = await self.db.get_db("sendtasks", select_columns=["sendtask_uuid", "sendtask_create_ut", "sendtask_id"])
        else:
            logger.info(f"Refreshing sendlog_stats for specified uuids: {uuids}")
            sendtask_data = await self.db.get_db("sendtasks", select_columns=["sendtask_uuid", "sendtask_create_ut", "sendtask_id"], where_column="sendtask_uuid", values=uuids)
        uuids_and_create_time = {task["sendtask_uuid"]: task["sendtask_create_ut"] for task in sendtask_data}

        # 確保 sendlog 資料表存在，同時更新資料表
        check_statuses = await self.check_sendlog(uuids_and_create_time)

        # 取得任務名稱，用於通知
        task_names = {task["sendtask_uuid"]: task["sendtask_id"] for task in sendtask_data}

        # 開始刷新 sendlog_stats
        for uuid in [u for u in uuids_and_create_time.keys() if check_statuses.get(u) not in ["deleted", "error"]]:
            # logger.info(f"Refreshing sendlog_stats for {uuid}")

            # 1. 獲取舊的統計數據
            old_stats_data = await self.db.get_db("sendlog_stats", where_column="sendtask_uuid", values=uuid)
            old_stats = old_stats_data[0] if old_stats_data else {}

            # 2. 計算新的統計數據
            data = await self.get_sendlog(sendtask_uuid=uuid, need_id=False, use_cache=False)
            new_stats = calc_stats(data)

            # 3. 比較並觸發通知
            old_todaysend = old_stats.get("todaysend", 0)
            new_todaysend = new_stats.get("todaysend", 0)
            if old_todaysend == 0 and new_todaysend > 0:
                task_name = task_names.get(uuid, uuid)
                message = f"🚀 *任務開始執行*\n任務 `{escape_markdown_v2(task_name)}` 今天已開始寄送第一封郵件。"
                await send_telegram_notification(message)

            # 4. 更新資料庫
            check_statuses[uuid] = await self.db.upsert_db("sendlog_stats", {
                "sendtask_uuid": uuid,
                **new_stats
            }, conflict_keys=["sendtask_uuid"])
            # logger.info(f"Updated sendlog_stats for {uuid}. Status: {check_statuses[uuid]}")
        logger.info(f"Finished refreshing sendlog_stats.")

        return check_statuses

    async def get_sendlog(self, sendtask_uuid: str, need_id=True, use_cache=True):
        await self.db.check_db_connection()
        
        # 0. 嘗試從 Redis 讀取快取
        cache_key = f"task:{sendtask_uuid}:details"
        if use_cache:
            try:
                from backend.services.redis_client import RedisClient
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

        # 1. DB 查詢 send_log_details
        data = await self.db.get_db("send_log_details", where_column="sendtask_uuid", values=sendtask_uuid)
        
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
                # 簡單起見，先讀取 sendtasks 狀態。這可能會多一次 DB Query，但為了 TTL 正確值得。
                # 也可以考慮把 is_archived 放入 Cache Key 或另外存
                task_rows = await self.db.get_db("sendtasks", select_columns=["is_archived"], where_column="sendtask_uuid", values=sendtask_uuid)
                is_archived = task_rows[0].get("is_archived", False) if task_rows else False
                
                ttl = 3600 if is_archived else 86400  # 1小時 vs 1天 (Active)
                
                # 序列化含有 datetime/date 的物件需要小心，但這裡 data 來自 asyncpg row (dict)，
                # 且大部分時間是 BIGINT 或 TEXT，應該可以直接 dumps。
                # 若有 datetime 物件需自訂 encoder，但在 table_info 看到都是 BIGINT (timestamp)。
                
                await client.set(cache_key, json.dumps(final_data), ex=ttl)
                logger.debug(f"Cache Set for {sendtask_uuid} with TTL {ttl}")
        except Exception as e:
             logger.warning(f"Failed to set Redis cache for {sendtask_uuid}: {e}")

        return final_data

## user相關操作
    async def user_exists(self, username: str) -> bool:
        """
        檢查使用者是否存在
        :param username: 使用者名稱
        :return: 如果使用者存在，返回 True，否則返回 False
        """
        await self.db.check_db_connection()
        result = await self.db.get_db("users", where_column="username", values=username)
        return len(result) > 0

    async def insert_user(self, username: str, password_hash: str):
        """
        插入新使用者
        :param username: 使用者名稱
        :param password_hash: 密碼哈希值
        """
        await self.db.check_db_connection()
        accts_data = await self.db.get_db("accts", where_column="acct_id", values=username)
        if not accts_data:
            logger.error(f"acct_id {username} does not exist in the main system (accts).")
            return {"status": "error", "message": "帳號不存在在主系統"}
        acct = accts_data[0]
        data = {
            "acct_uuid": acct["acct_uuid"],
            "username": username,
            "password_hash": password_hash,
            "email": acct["acct_email"],
            "full_name": acct["acct_full_name"],
            "orgs": acct["orgs"]
        }
        await self.db.insert_db("users", data)
        return {"status": "success", "message": "註冊成功", "acct_uuid": data["acct_uuid"], "username": data["username"]}
    
    async def get_all_users_with_registration_status(self):
        """
        從 'accts' 獲取所有帳戶，並檢查他們在 'users' 中的註冊狀態。
        """
        await self.db.check_db_connection()
        # Fetch all accounts
        accts = await self.db.get_db(
            table_name="accts", 
            select_columns=["acct_uuid", "acct_id", "acct_full_name", "acct_email", "is_active", "orgs"],
            order_by="acct_full_name"
        )
        
        # Fetch all registered user uuids
        users = await self.db.get_db(
            table_name="users",
            select_columns=["acct_uuid"]
        )
        registered_uuids = {u["acct_uuid"] for u in users if u.get("acct_uuid")}
        
        # Merge and transform
        result = []
        for acct in accts:
            acct_uuid = acct.get("acct_uuid")
            row = {
                "acct_uuid": acct_uuid,
                "acct_id": acct.get("acct_id"),
                "acct_full_name": acct.get("acct_full_name"),
                "acct_email": acct.get("acct_email"),
                "is_active": acct.get("is_active"),
                "orgs": acct.get("orgs"),
                "is_registered": acct_uuid in registered_uuids
            }
            result.append(row)
            

        
        return result
    

    async def clear_trigger_data(self, uuid: str, sendtask_uuid: str):
        """
        清除指定受測者(uuid)的所有觸發紀錄 (包含主系統與 Dashboard)
        並清除 Redis 快取
        """
        await self.db.check_db_connection()
        
        # 1. 定義要清空的欄位
        update_data = {
            "second_access_time": None, "second_access_src": None, "second_access_dev": None,
            "second_input_time": None, "second_input_src": None, "second_input_dev": None, "second_input_info": None
        }
        
        # 2. 更新資料庫
        # 注意: update_db 需要 condition={"uuid": uuid}
        # 為了安全起見，也可以只用 uuid，因為 uuid 應該是唯一的
        try:
            await self.db.update_db("send_log_details", update_data, condition={"uuid": uuid})
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
        await self.db.check_db_connection()
        result = await self.db.get_db("customer_accts", where_column="customer_name", values=customer_name)
        return len(result) > 0

    async def insert_customer(self, data: dict):
        """
        插入新客戶
        :param data: 客戶資料
        :return: 
        """
        await self.db.check_db_connection()
        try:
            data = {
                "customer_name": data.get("customer_name"),
                "customer_full_name": data.get("customer_full_name"),
                "password_hash": data.get("password_hash"),
                "acct_uuid": data.get("acct_uuid")
            }
            await self.db.insert_db("customer_accts", data)
            return {"status": "success", "message": "新增客戶成功", "customer_name": data["customer_name"]}
        except Exception as e:
            return {"status": "error", "message": str(e)}


    async def update_customer_sendtasks(self, customer_name: str, sendtask_data: List[Dict[str, Any]]):
        """
        更新客戶的任務列表，將其存為 JSONB 格式。
        :param customer_name: 客戶名稱
        :param sendtask_data: 任務物件的列表 (List of Dictionaries)
        """
        await self.db.check_db_connection()

        # 檢查客戶是否存在
        if not await self.customer_exists(customer_name):
            logger.error(f"Customer {customer_name} does not exist.")
            return {"status": "error", "message": "客戶不存在"}
        
        sendtasks_json_string = json.dumps(sendtask_data, ensure_ascii=False)

        status = await self.db.update_db(
            table_name="customer_accts",
            data={"sendtasks": sendtasks_json_string},
            condition={"customer_name": customer_name}
        )
        return status

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
        await self.db.check_db_connection()
        
        try:
            if user_type == "user":
                table_name = "users"
                where_column = "acct_uuid"
            elif user_type == "customer":
                table_name = "customer_accts"
                where_column = "customer_name"
            else:
                return {"status": "error", "message": "無效的用戶類型"}
            
            # 檢查用戶是否存在
            user_data = await self.db.get_db(
                table_name, 
                where_column=where_column, 
                values=identifier
            )
            
            if not user_data:
                return {"status": "error", "message": f"{'用戶' if user_type == 'user' else '客戶'}不存在"}
            
            user = user_data[0]
            
            # 進行驗證舊密碼
            if old_password:
                if not verify_password(old_password, user.get("password_hash")):
                    return {"status": "error", "message": "舊密碼不正確"}
                
                if old_password == new_password:
                    return {"status": "error", "message": "新密碼不能與舊密碼相同"}
            
            # 更新密碼
            new_password_hash = hash_password(new_password)
            status = await self.db.update_db(
                table_name=table_name, 
                data={"password_hash": new_password_hash}, 
                condition={where_column: identifier}
            )
            
            if status:
                logger.info(f"Password updated successfully for {user_type}: {identifier}")
                return {
                    "status": "success", 
                    "message": "密碼更新成功", 
                    "identifier": identifier,
                    "user_type": user_type
                }
            else:
                return {"status": "error", "message": "密碼更新失敗"}
                
        except Exception as e:
            logger.error(f"Error updating password for {user_type} {identifier}: {str(e)}")
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
        await self.db.check_db_connection()
        try:
            data = {
                "username": username,
                "action": action,
                "status": status,
                "ip_address": ip_address,
                "details": details
            }
            await self.db.insert_db("login_logs", data)
            logger.info(f"Added login log: {username} {action} {status}")
        except Exception as e:
            logger.error(f"Error adding login log: {str(e)}")

    async def get_login_logs(self, limit: int = 100):
        """
        取得登入/登出紀錄
        :param limit: 限制筆數
        :return: 紀錄列表
        """
        await self.db.check_db_connection()
        try:
            result = await self.db.get_paginated_db(
                table_name="login_logs",
                paginate=True,
                page=1,
                rows_per_page=limit,
                order_by="create_time DESC"
            )
            return result.get("data", [])
        except Exception as e:
            logger.error(f"Error fetching login logs: {str(e)}")
            return []
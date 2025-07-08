'''
Database operations for user-related data, including sendlog management.
'''

import re
import asyncpg
import aiofiles
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.services.log_manager import Logger
from app.services.getSe2data import get_se2_data
from app.core.db_controller import ApplianceDB


logger = Logger().get_logger()

def timestamp():
    tz = ZoneInfo("Asia/Taipei")   # 修改時區
    today = datetime.now(tz).date()
    start_ts = int(datetime.combine(today, datetime.min.time(), tz).timestamp())
    end_ts = int((datetime.combine(today, datetime.min.time(), tz) + timedelta(days=1)).timestamp())
    return start_ts, end_ts

def calc_stats(stats):
    """ 
    計算統計數據
    :param stats: sendlog 資料列表
    :return: 統計數據字典
    """
    start_ts, end_ts = timestamp()

    # 總成功數量
    totalSuccess = [t for t in stats if str(t.get("send_res", "")).startswith("True")]

    # 今日寄送：寄送時間>=當天開始時間 & 寄送時間<當天結束時間 & 寄送時間為0
    todayUnsend = [t for t in stats if start_ts <= t.get("plan_time", 0) < end_ts and t.get("send_time", 0) == 0]
    # 今日寄送：寄送時間>=當天開始時間 & 寄送時間<當天結束時間
    todaySends = [t for t in stats if start_ts <= t.get("send_time", 0) < end_ts]
    todaySuccess = [t for t in todaySends if str(t.get("send_res", "")).startswith("True")]
    totalSends = [t for t in stats if t.get("send_time", 0) != 0]

    today_plan_time = [t["plan_time"] for t in stats if start_ts <= t.get("plan_time", 0) < end_ts]
    # 今日未寄送最早的 plan_time（如果有的話）
    today_earliest_plan_time = min(today_plan_time) if today_plan_time else 0
    # 今日為寄送最後的 plan_time（如果有的話）
    today_latest_plan_time = max(today_plan_time) if today_plan_time else 0

    # 任務第一封的 plan_time
    all_earliest_plan_time = min(t["plan_time"] for t in stats) if stats else 0
    # 任務最後一封的 plan_time
    all_latest_plan_time = max(t["plan_time"] for t in stats) if stats else 0
    # # 任務最後一封的 send_time
    # all_latest_send_time = max(t["send_time"] for t in stats) if stats and len(stats) == len(totalSends) else 0

    return {
        "totalplanned": len(stats),
        "totalSuccess": len(totalSuccess),
        "todayunsend": len(todayUnsend),
        "today_earliest_plan_time": today_earliest_plan_time,
        "today_latest_plan_time": today_latest_plan_time,
        "all_earliest_plan_time": all_earliest_plan_time,
        "all_latest_plan_time": all_latest_plan_time,
        "todaysend": len(todaySends),
        "todaysuccess": len(todaySuccess),
        "totalsend": len(totalSends),
    }


class DBUser:
    def __init__(self, db: ApplianceDB = ApplianceDB()):
        """ 
        初始化 DBUser 類別
        :param db: ApplianceDB 實例，預設為 ApplianceDB()
        """
        self.db = db
        self.day = 15  # 預設查詢天數為 15 天
        # accts 欄位
        self.accts_columns = ["acct_uuid", "acct_id", "acct_full_name", "acct_full_name_2nd",
                              "acct_email", "acct_activate", "orgs"]

        # sendtasks 欄位
        self.sendtasks_columns = ["sendtask_uuid", "sendtask_id", "sendtask_owner_gid", "pre_test_end_ut",
                                  "pre_test_start_ut", "pre_send_end_ut", "sendtask_create_ut", "test_end_ut", 
                                  "test_start_ut", "is_pause", "stop_time_new"]
        # sendlog 資料表結構
        self.sendlog_table_info = {"id": "SERIAL PRIMARY KEY", "uuid": "TEXT UNIQUE", "target_email": "TEXT", 
                                   "template_uuid": "TEXT", "access_active": "TEXT[]", "access_ip": "TEXT[]",
                                   "access_time": "BIGINT[]", "person_info": "TEXT", "plan_time": "BIGINT",
                                   "send_time": "BIGINT", "send_res": "TEXT", "access_time": "BIGINT[]",
                                   "access_src": "TEXT[]", "access_dev": "TEXT[]", "click_time": "BIGINT[]",
                                   "click_src": "TEXT[]", "click_dev": "TEXT[]", "file_time": "BIGINT[]",
                                   "file_src": "TEXT[]", "file_dev": "TEXT[]"}
        # sendlog 欄位
        self.sendlog_columns = ["uuid", "target_email", "person_info", "template_uuid", "plan_time",
                                "send_time", "send_res", "access_time", "access_src", "access_dev",
                                "click_time", "click_src", "click_dev", "file_time", "file_src", "file_dev"]
        
        # coustomer 資料表結構
        self.customer_info = {"id": "SERIAL PRIMARY KEY", "customer_name": "TEXT UNIQUE NOT NULL",
                              "customer_full_name": "TEXT", "password_hash": "TEXT NOT NULL", "sendtasks": "TEXT[]",
                              "create_time": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
                              "is_active": "BOOLEAN DEFAULT TRUE"}
        
    async def table_initialize(self):
        """
        初始化資料表
        檢查資料表是否為空，如果是空的，則從 SE2 獲取資料並插入到資料表中。
        如果資料表已經有資料，則跳過初始化。
        """
        # 檢查資料庫連線
        await self.db.check_db_connection()

        table_names = ["accts", "sendtasks", "sendlog_stats"]
        
        # 檢查資料表是否為空，如果是空的，則從 SE2 獲取資料並插入到資料表中。
        for table_name in table_names:
            if await self.db.table_empty(table_name):
                logger.info(f"{table_name} is empty. Initializing with data from SE2...")
                if table_name == "accts":
                    # 從 SE2 獲取 accts 資料
                    se2_list = await self.get_se2_accts(self.accts_columns)
                elif table_name == "sendtasks":
                    # 從 SE2 獲取 sendtasks 資料
                    se2_list = await self.get_se2_sendtasks(self.sendtasks_columns, days=self.day)
                elif table_name == "sendlog_stats":
                    # 取得sendtask_uuids
                    sendtask_data = await self.db.get_db("sendtasks", select_columns=["sendtask_uuid"])
                    sendtask_uuids = [t["sendtask_uuid"] for t in sendtask_data]
                    # 開始更新sendlog_stats table
                    sendlog_stats_status = await self.refresh_sendlog_stats(sendtask_uuids)
                    logger.info(f"Updated sendlog_stats with status: {sendlog_stats_status}")
                    continue

                if not se2_list:
                    logger.warning(f"No data found for {table_name} in SE2.")
                    continue
                await self.db.insert_db(table_name, se2_list)
                logger.info(f"Inserted {len(se2_list)} records into {table_name}.")
            else:
                logger.info(f"{table_name} already has data. Skipping initialization.")

        # 從 users 資料表去新增 customer 資料表
        if not self.db.table_empty("users"):
            user_data = await self.db.get_db("users", select_columns=["username"])
            self.check_customer(d["username"] for d in user_data)

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

    async def get_se2_sendtasks(self, column_names=None, days=15) -> list[dict]:
        """
        從 SE2 獲取 sendtasks 資料
        :param sendtasks_columns: sendtasks 的欄位名稱
        :param days: 查詢的天數
        :return: sendtasks 資料列表
        """
        await self.db.check_db_connection()

        sendtasks_df = await get_se2_data.get_sendtasks()
        if sendtasks_df is not None and not sendtasks_df.empty:
            # 獲取 metadata 資料
            logger.info("Fetching metadata...")
            for index, row in sendtasks_df.iterrows():
                uuid = row["sendtask_uuid"]
                metadata = await get_se2_data.get_sendtask_metadata(uuid)
                if metadata is not None:
                    sendtasks_df.at[index, "is_pause"] = metadata.get("pause", False)
                    sendtasks_df.at[index, "stop_time_new"] = metadata.get("stop_time_new", -1)
                else:
                    sendtasks_df.at[index, "is_pause"] = False
                    sendtasks_df.at[index, "stop_time_new"] = -1
            logger.info("Metadata fetched successfully.")

            # 取得當前時間戳
            now = int(time.time())
            # 計算抓取任務範圍的時間戳
            ago = now - (days * 24 * 60 * 60)  # days轉換為秒
            # 過濾條件(test_end_ut >= days)(結束時間為15天內)
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
        start_ts, end_ts = timestamp()
        logger.info(f"start_ts: {start_ts}")
        logger.info(f"end_ts: {end_ts}")

        today_create_tasks_df = await get_se2_data.get_sendtasks(end_time=end_ts, start_time=start_ts, filter_time_range=99)
        if today_create_tasks_df is not None and not today_create_tasks_df.empty:
            # 獲取 metadata 資料
            logger.info("Fetching metadata...")
            for index, row in today_create_tasks_df.iterrows():
                uuid = row["sendtask_uuid"]
                metadata = await get_se2_data.get_sendtask_metadata(uuid)
                if metadata is not None:
                    today_create_tasks_df.at[index, "is_pause"] = metadata.get("pause", False)
                    today_create_tasks_df.at[index, "stop_time_new"] = metadata.get("stop_time_new", -1)
                else:
                    today_create_tasks_df.at[index, "is_pause"] = False
                    today_create_tasks_df.at[index, "stop_time_new"] = -1
            logger.info("Metadata fetched successfully.")
            today_create_tasks_list = today_create_tasks_df[self.sendtasks_columns].to_dict(orient="records")
            return today_create_tasks_list
        return []

## sendlog and sendlog_stats相關操作
    async def check_sendlog(self, sendtask_uuids: list):
        """
        檢查 sendlog table 是否存在於資料庫中
        不存在便新建，並存入資料
        存在則更新資料
        :param sendtask_uuid: sendtask 的 UUID
        """
        await self.db.check_db_connection()
        logger.info("Checking sendlog tables...")
        # 批次檢查所有資料表是否存在
        tables_to_create = []
        for uuid in sendtask_uuids:
            if not await self.db.table_exists(uuid):
                tables_to_create.append(uuid)
        # 批次建立資料表
        for uuid in tables_to_create:
            await self.db.create_table(uuid, self.sendlog_table_info)
            logger.info(f"Table {uuid} created.")
        if not tables_to_create:
            logger.info("All sendlog tables already exist.")  

        logger.info("Upserting sendlog tables...")
        sendlog_status = await self.sendlog_write(sendtask_uuids)
        logger.info(f"Sendlog tables upserted with status: {sendlog_status}")
        return sendlog_status  # 返回狀態而不是 None

    async def sendlog_write(self, sendtask_uuid: list, sendlog_type="test") -> dict:
        """ 
        更新 sendlog 資料到資料庫
        :param sendtask_uuid: 任務清單的uuid列表
        :param sendlog_type: sendlog 類型，預設為 "test"
         """
        sendlog_status = {}
        await self.db.check_db_connection()
        for uuid in sendtask_uuid:
            # 獲取 sendlog 資料
            sendlog = await self.get_se2_sendlog(uuid, sendlog_columns=self.sendlog_columns)
            if sendlog:
                sendlog_status[uuid] = "unchanged"
                for log in sendlog:
                    status = await self.db.upsert_db(uuid, log, conflict_keys=["uuid"])
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
        if uuids is None:
            logger.info("Fetching all sendtask uuids for refresh...")
            sendtask_data = await self.db.get_db("sendtasks", select_columns=["sendtask_uuid"])
            uuids = [task["sendtask_uuid"] for task in sendtask_data]
        else:
            logger.info(f"Refreshing sendlog_stats for specified uuids: {uuids}")

        # 確保 sendlog 資料表存在並且為最新狀態
        await self.check_sendlog(uuids)
        # 開始刷新 sendlog_stats
        sendlog_stats_status = {}
        for uuid in uuids:
            logger.info(f"Refreshing sendlog_stats for {uuid}")
            data = await self.db.get_db(uuid)
            for dd in data:
                dd.pop("id", None)
            stats = calc_stats(data)
            sendlog_stats_status[uuid] = await self.db.upsert_db("sendlog_stats", {
                "sendtask_uuid": uuid,
                **stats
            }, conflict_keys=["sendtask_uuid"])
            logger.info(f"Updated sendlog_stats for {uuid}. Status: {sendlog_stats_status[uuid]}")
        logger.info(f"Finished refreshing sendlog_stats.")

        return sendlog_stats_status

## user相關操作
    async def user_exists(self, email: str) -> bool:
        """
        檢查使用者是否存在
        :param email: 使用者名稱
        :return: 如果使用者存在，返回 True，否則返回 False
        """
        await self.db.check_db_connection()
        result = await self.db.get_db("users", where_column="email", values=email)
        return len(result) > 0
    
    async def insert_user(self, email: str, password_hash: str):
        """
        插入新使用者
        :param email: 使用者電子郵件
        :param password_hash: 密碼哈希值
        """
        await self.db.check_db_connection()
        accts_data = await self.db.get_db("accts", where_column="acct_id", values=email)
        if not accts_data:
            logger.error(f"Email {email} does not exist in the main system (accts).")
            return {"status": "error", "msg": "帳號不存在在主系統"}
        acct = accts_data[0]
        data = {
            "acct_uuid": acct["acct_uuid"],
            "username": acct["acct_id"],
            "password_hash": password_hash,
            "email": email,
            "full_name": acct["acct_full_name"],
            "orgs": acct["orgs"]
        }
        await self.db.insert_db("users", data)
        return {"status": "success", "msg": "註冊成功", "email": email, "username": data["username"]}
    
## customer 相關操作
    async def check_customer(self, acct_mails: list):
        tables_to_create = []
        for mail in acct_mails:
            table_name = mail.replace("@", "_") + "_customers"
            if not await self.db.table_exists(table_name):
                tables_to_create.append(table_name)
        # 批次建立資料表
        for table_name in tables_to_create:
            await self.db.create_table(table_name, self.customer_info)
            logger.info(f"Table {table_name} created.")
        if not tables_to_create:
            logger.info("All customer tables already exist.")  

    async def customer_exists(self, username: str, customer_name: str) -> bool:
        """
        檢查客戶是否存在
        :param username: 帳號名稱
        :param name: 客戶名稱
        :return: 如果客戶存在，返回 True，否則返回 False
        """
        await self.db.check_db_connection()
        table_name = username.replace("@", "_") + "_customers"
        result = await self.db.get_db(table_name, where_column="customer_name", values=customer_name)
        return len(result) > 0

    async def insert_customer(self, username: str, customer_name: str, customer_full_name: str, password_hash: str):
        """
        插入新客戶
        :param customer_name: 客戶名稱
        :param customer_full_name: 客戶全名
        :param password_hash: 密碼哈希值
        """
        await self.db.check_db_connection()
        data = {
            "customer_name": customer_name,
            "customer_full_name": customer_full_name,
            "password_hash": password_hash,
            "sendtasks": []
        }
        table_name = username.replace("@", "_") + "_customers"
        await self.db.insert_db(table_name, data)
        return {"status": "success", "msg": "新增客戶成功", "customer_name": customer_name}

    async def add_customer_sendtasks(self, username: str, customer_name: str, sendtasks: list[str]):
        await self.db.check_db_connection()
        table_name = username.replace("@", "_") + "_customers"
        status = await self.db.upsert_db(table_name, {
                    "customer_name": customer_name,
                    "sendtasks": sendtasks
                }, conflict_keys=["customer_name"])
        return status

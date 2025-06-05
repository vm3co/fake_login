import re
import asyncpg
import aiofiles
from datetime import datetime, timedelta

from app.services.log_manager import Logger
from app.services.getSe2data import get_se2_data
from app.core.db_controller import ApplianceDB


logger = Logger().get_logger()

def calc_stats(stats):
    today = datetime.now().date()
    start_ts = int(datetime.combine(today, datetime.min.time()).timestamp())
    end_ts = int((datetime.combine(today, datetime.min.time()) + timedelta(days=1)).timestamp())

    todayPlans = [t for t in stats if t.get("plan_time", 0) >= start_ts and t.get("plan_time", 0) < end_ts]
    todaySends = [t for t in stats if t.get("send_time", 0) >= start_ts and t.get("send_time", 0) < end_ts and t.get("send_time", 0) != 0]
    todaySuccess = [t for t in todaySends if str(t.get("send_res", "")).startswith("True")]
    totalSends = [t for t in stats if t.get("send_time", 0) != 0]

    return {
        "totalplanned": len(stats),
        "todayplanned": len(todayPlans),
        "todaysent": len(todaySends),
        "todaysuccess": len(todaySuccess),
        "totalsent": len(totalSends),
        "stats_date": today
    }


class DBUser:
    def __init__(self, db: ApplianceDB = ApplianceDB()):
        """ 
        初始化 DBUser 類別
        :param db: ApplianceDB 實例，預設為 ApplianceDB()
        """
        self.db = db

    async def sendlog_write(self, all_tasksname_list):
        columns = {"id": "SERIAL PRIMARY KEY", 
                    "uuid": "TEXT",
                    "target_email": "TEXT", 
                    "template_uuid": "TEXT", 
                    "access_active": "TEXT[]",
                    "access_ip": "TEXT[]",
                    "access_time": "BIGINT[]",
                    "person_info": "TEXT",
                    "plan_time": "BIGINT",
                    "send_time": "BIGINT",
                    "send_res": "TEXT",
                    "access_time": "BIGINT[]",
                    "access_src": "TEXT[]",
                    "access_dev": "TEXT[]",
                    "click_time": "BIGINT[]",
                    "click_src": "TEXT[]",
                    "click_dev": "TEXT[]",
                    "file_time": "BIGINT[]",
                    "file_src": "TEXT[]",
                    "file_dev": "TEXT[]",
                    }
        for task in all_tasksname_list:
            table_name = task["sendtask_uuid"]
            if not await self.db.table_exists(table_name):
                logger.info(f"Creating table {task['sendtask_uuid']}...")
                await self.db.create_table(task["sendtask_uuid"], columns)
            elif not await self.db.table_empty(task["sendtask_uuid"]):
                logger.info(f"Table {task['sendtask_uuid']} already exists and is not empty. Skipping creation.")
                continue
            
            df_sendlog = await get_se2_data.get_sendlog(task["sendtask_uuid"])
            if df_sendlog is not None and not df_sendlog.empty:
                sendlog_columns = ["uuid", "target_email", "person_info", "template_uuid", "plan_time", "send_time",
                                    "send_res", "access_time", "access_src", "access_dev", "click_time", "click_src",
                                    "click_dev", "file_time", "file_src", "file_dev"]
                # 只取有在 DataFrame 中的欄位
                valid_columns = [col for col in sendlog_columns if col in df_sendlog.columns]
                if valid_columns:
                    sendlog = df_sendlog[valid_columns].to_dict(orient="records")
                    await self.db.insert_db(task["sendtask_uuid"], sendlog)
                else:
                    logger.warning(f"No valid columns found in sendlog for task {task['sendtask_uuid']}")
            else:
                logger.info(f"No sendlog data for task {task['sendtask_uuid']}")

    async def table_initialize(self):
        """
        初始化資料表
        """
        # 檢查資料庫連線
        await self.db.check_db_connection()
        # 檢查 accts 資料表
        if await self.db.table_empty("accts"):
            logger.info("accts is empty. Initializing with data from SE2...")
            acct_df = await get_se2_data.get_accts()
            if acct_df is not None and not acct_df.empty:
                acct_list = acct_df[["acct_uuid", "acct_id", "acct_full_name", "acct_full_name_2nd",
                                    "acct_email", "acct_activate", "orgs"]].to_dict(orient="records")
                for acct in acct_list:
                    acct["is_active"] = acct["acct_activate"]
                    acct.pop("acct_activate", None)  # 移除 acct_activate 欄位
                await self.db.insert_db("accts", acct_list)
                logger.info(f"Inserted {len(acct_list)} records into accts.")
        else:
            logger.info("accts already has data. Skipping initialization.")
        # 檢查 sendtasks 資料表
        if await self.db.table_empty("sendtasks"):
            logger.info("sendtasks is empty. Initializing with data from SE2...")
            sendtasks_df = await get_se2_data.get_sendtasks()
            if sendtasks_df is not None and not sendtasks_df.empty:
                columns = ["sendtask_uuid", "sendtask_id", "sendtask_owner_gid", "pre_test_end_ut",
                           "pre_test_start_ut", "pre_send_end_ut", "sendtask_create_ut", "test_end_ut", "test_start_ut"]
                sendtasks_list = sendtasks_df[columns].to_dict(orient="records")
                await self.db.insert_db("sendtasks", sendtasks_list)
                logger.info(f"Inserted {len(sendtasks_list)} records into sendtasks.")
            # 檢查 sendlog 資料表
            await self.sendlog_write(sendtasks_list)
        else:
            logger.info("sendtasks already has data. Skipping initialization.")
            # sendtasks_list = await self.db.get_db("sendtasks", column_names=columns)
        # 檢查sendlog_stats 資料表
        # uuids = await self.db.get_db("sendtasks", column_names=["sendtask_uuid"])
        # for uuid in uuids:
        #     uuid = uuid["sendtask_uuid"]
        #     data = await self.db.get_db(uuid, include_inactive=True)
        #     for dd in data:
        #         dd.pop("id", None)
        #     stats = calc_stats(new_data)
        #     await self.db.upsert_db("sendlog_stats", {
        #         "sendtask_uuid": uuid,
        #         **stats
        #     }, conflict_keys=["sendtask_uuid"])


    async def user_exists(self, email: str) -> bool:
        """
        檢查使用者是否存在
        :param email: 使用者名稱
        :return: 如果使用者存在，返回 True，否則返回 False
        """
        await self.db.check_db_connection()
        result = await self.db.get_db("users", column_names=["email"], value=email)
        return len(result) > 0
    
    async def insert_user(self, email: str, password_hash: str):
        """
        插入新使用者
        :param email: 使用者電子郵件
        :param password_hash: 密碼哈希值
        """
        await self.db.check_db_connection()
        accts_data = await self.db.get_db("accts", column_names=["acct_email"], value=email)
        if not accts_data:
            logger.error(f"Email {email} does not exist in the main system (accts).")
            return {"status": "error", "msg": "帳號不存在在主系統"}
        acct = accts_data[0]
        data = {
            "username": acct["acct_id"],
            "password_hash": password_hash,
            "email": email,
            "full_name": acct["acct_full_name"],
            "orgs": acct["orgs"]
        }
        await self.db.insert_db("users", data)
        return {"status": "success", "msg": "註冊成功"}

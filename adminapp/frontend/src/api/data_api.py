# -*- coding: utf-8 -*-
"""
Created on Thu May  8 14:32:44 2025

@author: 2501053

用api到se2系統抓取資料
"""
from fastapi import APIRouter, Request, Body
from pydantic import BaseModel
import os
import csv
import pandas as pd
from dotenv import load_dotenv

from app.services.log_manager import Logger
from app.services.getSe2data import get_se2_data


load_dotenv()
LOG_FILE = os.getenv("LOG_FILE", "/data/visit_log.csv")

def has_common_orgs(a: list, b: list) -> bool:
    return any(item in a for item in b)

def dict_to_hashable(d):
    return tuple(sorted(
        (k, tuple(v) if isinstance(v, list) else v)
        for k, v in d.items()
    ))

def hashable_to_dict(t):
    return {k: list(v) if isinstance(v, tuple) else v for k, v in t}        
            
def normalize(data):
    # 將每一筆 dict 轉成排序後的 tuple，然後整個 list 排序
    return sorted(tuple(sorted(d.items())) for d in data)

def get_router(db, db_user):
    """
    初始化路由
    :param db: 資料庫實例
    :return: APIRouter 實例
    """
    router = APIRouter()
    logger = Logger().get_logger()

    sendlog_columns = ["uuid", "target_email", "person_info", "template_uuid", "plan_time", "send_time",
                    "send_res", "access_time", "access_src", "access_dev", "click_time", "click_src",
                    "click_dev", "file_time", "file_src", "file_dev"]
    
    class OrgsRequest(BaseModel):
        orgs: list[str] = []

    @router.post("/sendtasks/get")
    async def get_sendtasks(request: OrgsRequest):
        try:
            column_names = ["sendtask_id", "sendtask_uuid", "sendtask_owner_gid", "sendtask_create_ut"]
            my_tasksname_list = await db.get_db("sendtasks", column_names=column_names)
            if request.orgs:
                my_tasksname_list = [
                    task for task in my_tasksname_list
                    if has_common_orgs(task.get("sendtask_owner_gid", []), request.orgs)
                ]
            return {"status": "success", "data": my_tasksname_list}
        except Exception as e:
            logger.error(f"Error in get_sendtasks: {str(e)}")
            return {"status": "error", "message": str(e)}

    @router.get("/sendtasks/check")
    async def check_sendtasks():
        """
        檢查sendtask是否有變更
        1. 讀取sendtask清單
        2. 與資料庫sendtask清單做diff
        3. 新增到sendtask資料庫
        4. 刪除sendtask資料庫的is_active=False
        """
        try:
            df = await get_se2_data.get_sendtasks()
            if df is None:
                return {"status": "error", "message": "get_se2_data error"}
            
            column_names = ["sendtask_id", "sendtask_uuid", "sendtask_owner_gid", "sendtask_create_ut"]
            all_tasksname_list = df[column_names].to_dict(orient="records")
            my_tasksname_list = await db.get_db("sendtasks", column_names=column_names)

            all_set = set(dict_to_hashable(d) for d in all_tasksname_list)
            my_set = set(dict_to_hashable(d) for d in my_tasksname_list)
            # 找出差異
            added = all_set - my_set
            removed = my_set - all_set

            # 再轉回 list[dict] 格式
            added_list = [hashable_to_dict(t) for t in added]
            removed_list = [hashable_to_dict(t) for t in removed]

            # 新增
            await db.insert_db("sendtasks", added_list)
            await db_user.sendlog_write(added_list)

            # 刪除(is_active=FALSE)
            for item in removed_list:
                await db.update_db(
                    table_name="sendtasks",
                    data={"is_active": False},
                    condition={"sendtask_uuid": item["sendtask_uuid"]}
                    )

            data = {"added": added_list, "removed": removed_list}
            return {"status": "success", "data": data}
        except Exception as e:
            logger.error(f"Error in check_sendtasks: {str(e)}")
            return {"status": "error", "message": str(e)}

    @router.get("/sendtasks/update")
    async def update_sendtasks():
        pass


    @router.get("/sendlog/get/{uuid}")
    async def create_participant_data(uuid: str): 
        try:
            data = await db.get_db(uuid, include_inactive=True)
            for dd in data:
                dd.pop("id", None)

            return {"status": "success", "data": data}
        except Exception as e:
            logger.error(f"Error in create_participant_data: {str(e)}")
            return {"status": "error", "message": str(e)}

    @router.post("/sendlog/refresh")
    async def refresh_sendlog():
        try:
            # 取得所有 sendtasks
            sendtasks = await db.get_db("sendtasks", column_names=["sendtask_uuid"])
            updated = []
            for task in sendtasks:
                uuid = task["sendtask_uuid"]
                # 1. 取得最新寄送資料
                df_new = await get_se2_data.get_sendlog(uuid)
                if df_new is None:
                    continue
                new_data = df_new[sendlog_columns].to_dict(orient="records")
                # 2. 取得資料庫現有資料
                db_data = await db.get_db(uuid, column_names=sendlog_columns, include_inactive=True)
                # 3. 用 normalize 比對內容
                if normalize(new_data) != normalize(db_data):
                    # 4. 清空舊資料，寫入新資料
                    await db.clear_table(uuid)
                    await db.insert_db(uuid, new_data)
                    updated.append(uuid)
            return {"status": "success", "message": f"{len(updated)} 筆寄送現況"}
        except Exception as e:
            logger.error(f"Error in refresh_sendlog: {str(e)}")
            return {"status": "error", "message": str(e)}


    @router.post("/sendlog/refresh/today")
    async def refresh_today_sendlog(data: dict = Body(...)):
        """
        今日寄送任務資料刷新

        1.  POST /sendlog/refresh/today
        2.  Body: {"uuids": ["task1_uuid", "task2_uuid", ...]}
        3.  Response: {"status": "success", "message": "已更新 x 筆今日任務", "updated": [...]}

        :param data: dict, POST request body, keys: uuids
        :return: dict, status, message, and updated uuids
        """
        try:
            uuids = data.get("uuids", [])
            if not uuids:
                return {"status": "error", "message": "沒有收到 uuids"}

            updated = []
            for uuid in uuids:
                df_new = await get_se2_data.get_sendlog(uuid)
                if df_new is None or df_new.empty:
                    continue
                new_data = df_new[sendlog_columns].to_dict(orient="records")
                db_data = await db.get_db(uuid, column_names=sendlog_columns, include_inactive=True)
                if normalize(new_data) != normalize(db_data):
                    await db.clear_table(uuid)
                    await db.insert_db(uuid, new_data)
                    updated.append(uuid)
            if updated:
                await db_user.refresh_sendlog_stats(updated)
            return {"status": "success", "message": f"已更新 {len(updated)} 筆今日任務", "updated": updated}
        except Exception as e:
            logger.error(f"Error in refresh_today_sendlog: {str(e)}")
            return {"status": "error", "message": str(e)}


    class UuidsRequest(BaseModel):
        uuids: list[str] = []

    @router.post("/sendlog_stats/get")
    async def get_sendlog_stats_batch(request: UuidsRequest):
        """
        取得多個任務的統計資料

        1.  POST /sendlog_stats/get
        2.  Body: {"uuids": ["task1_uuid", "task2_uuid", ...]}

        :param request: UuidsRequest
        :return: dict
        """
        try:
            uuids = request.uuids
            if not uuids:
                return {"status": "error", "message": "沒有收到 uuids", "data": []}
            rows = await db.get_db("sendlog_stats", column_names=["sendtask_uuid"], value=uuids, include_inactive=True)
            return {"status": "success", "data": rows}
        except Exception as e:
            logger.error(f"Error in get_sendlog_stats_batch: {str(e)}")
            return {"status": "error", "message": str(e), "data": []}

    @router.get("/mtmpl/get")
    async def get_mtmpl(): 
        return {"status": "error", "message": "test"} 
    #     try:
    #         df = await get_se2_data.get_mtmpl_subject_list()
    #         data = df.to_dict(orient="records")

    #         return {"status": "success", "data": data}
    #     except Exception as e:
    #         logger.error(f"Error in get_mtmpl: {str(e)}")
    #         return {"status": "error", "message": str(e)}
    
    return router

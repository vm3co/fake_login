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
# 確保環境變數已經載入

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
    :param db_user: 資料庫運用實例
    :return: APIRouter 實例
    """
    router = APIRouter()
    logger = Logger().get_logger()

    sendlog_columns = ["uuid", "target_email", "person_info", "template_uuid", "plan_time", "send_time",
                    "send_res", "access_time", "access_src", "access_dev", "click_time", "click_src",
                    "click_dev", "file_time", "file_src", "file_dev"]


    ## sendtasks 相關的 API
    class OrgsRequest(BaseModel):
        orgs: list[str] = []

    @router.post("/get_sendtasks")
    async def get_sendtasks(request: OrgsRequest):
        try:
            column_names = ["sendtask_id", "sendtask_uuid", "sendtask_owner_gid", "sendtask_create_ut", "is_pause", "stop_time_new"]
            my_tasksname_list = await db.get_db("sendtasks", column_names=column_names, include_inactive=False)
            if request.orgs and request.orgs != ["admin"]:
                my_tasksname_list = [
                    task for task in my_tasksname_list
                    if has_common_orgs(task.get("sendtask_owner_gid", []), request.orgs)
                ]
            return {"status": "success", "data": my_tasksname_list}
        except Exception as e:
            logger.error(f"Error in get_sendtasks: {str(e)}")
            return {"status": "error", "message": str(e)}

    @router.post("/check_sendtasks")
    async def check_sendtasks(request: OrgsRequest):
        """
        檢查sendtask是否有變更
        1. 讀取sendtask清單
        2. 與資料庫sendtask清單做diff
        3. 新增到sendtask資料庫
        4. 刪除sendtask資料庫的is_active=False
        """
        try:
            sendtasks_columns = ["sendtask_uuid", "sendtask_id", "sendtask_owner_gid", "pre_test_end_ut",
                                  "pre_test_start_ut", "pre_send_end_ut", "sendtask_create_ut", "test_end_ut", 
                                  "test_start_ut", "is_pause", "stop_time_new"]
            all_tasksname_list = await db_user.get_se2_sendtasks(column_names=sendtasks_columns)

            my_tasksname_list = await db.get_db("sendtasks", column_names=sendtasks_columns)

            if request.orgs and request.orgs != ["admin"]:
                all_tasksname_list = [
                    task for task in all_tasksname_list
                    if has_common_orgs(task.get("sendtask_owner_gid", []), request.orgs)
                ]
                my_tasksname_list = [
                    task for task in my_tasksname_list
                    if has_common_orgs(task.get("sendtask_owner_gid", []), request.orgs)
                ]

            all_set = set(dict_to_hashable(d) for d in all_tasksname_list)
            my_set = set(dict_to_hashable(d) for d in my_tasksname_list)
            # 找出差異
            added = all_set - my_set
            removed = my_set - all_set

            # 再轉回 list[dict] 格式
            added_list = [hashable_to_dict(t) for t in added]
            removed_list = [hashable_to_dict(t) for t in removed]

            # 新增
            if added_list:
                refresh_list = []
                for task in added_list:
                    status = await db.upsert_db(
                        table_name="sendtasks", 
                        data=task, 
                        conflict_keys=["sendtask_uuid"])
                    if status == "changed":
                        refresh_list.append(task["sendtask_uuid"])
                sendlog_stats_status = await db_user.refresh_sendlog_stats(refresh_list)

            # 刪除(is_active=FALSE)
            for item in removed_list:
                await db.update_db(
                    table_name="sendtasks",
                    data={"is_active": False},
                    condition={"sendtask_uuid": item["sendtask_uuid"]}
                    )

            data = {"added": added_list, "removed": removed_list, "sendlog_stats_status": sendlog_stats_status}
            return {"status": "success", "data": data}
        except Exception as e:
            logger.error(f"Error in check_sendtasks: {str(e)}")
            return {"status": "error", "message": str(e)}
        
    @router.post("/refresh_today_create_task")
    async def refresh_today_create_task(request: OrgsRequest):
        """
        刷新今天建立的任務
        1. 讀取今天建立的sendtask清單
        2. 與資料庫sendtask清單做diff
        3. 新增到sendtask資料庫
        4. 刪除sendtask資料庫的is_active=False

        :param request: OrgsRequest, 包含組織列表
        :return: dict, 包含新增和刪除的任務列表
        """
        today_create_task_list = await db_user.refresh_today_create_task()
        if request.orgs and request.orgs != ["admin"]:
            today_create_task_list = [
                task for task in today_create_task_list
                if has_common_orgs(task.get("sendtask_owner_gid", []), request.orgs)
            ]
        if not today_create_task_list:
            logger.warning(f"today create task list is empty.")
            return {"status": "success", "data": []}
        
        refresh_list = []
        for task in today_create_task_list:
            status = await db.upsert_db(
                table_name="sendtasks", 
                data=task, 
                conflict_keys=["sendtask_uuid"])
            if status == "changed": refresh_list.append(task["sendtask_uuid"])

        sendlog_stats_status = await db_user.refresh_sendlog_stats(refresh_list)

        return {"status": "success", "data": sendlog_stats_status}




    ## sendlog 相關的 API
    class SendLogRequest(BaseModel):
        sendtask_uuids: list[str] = []

    @router.post("/refresh_sendlog_stats")
    async def refresh_sendlog_stats(request: SendLogRequest):
        """
        刷新寄送任務統計資料

        1.  POST /refresh_sendlog_stats
        2.  request: ["task1_uuid", "task2_uuid", ...]
        3.  Response: {"status": "success", "sendlog_stats_status": {"task1_uuid": "updated", "task2_uuid": "unchanged", ...}}

        :param data: dict, POST request body, keys: uuids
        :return: dict, response data, keys: status, message, updated
        """
        try:
            uuids = request.sendtask_uuids
            if not uuids:
                return {"status": "error", "message": "沒有收到 uuids"}

            sendlog_stats_status = await db_user.refresh_sendlog_stats(uuids)
            return {"status": "success", "sendlog_stats_status": sendlog_stats_status}
        except Exception as e:
            logger.error(f"Error in refresh_sendlog_stats: {str(e)}")
            return {"status": "error", "message": str(e)}

    @router.post("/get_sendlog_stats")
    async def get_sendlog_stats_batch(request: SendLogRequest):
        """
        取得多個任務的統計資料

        1.  POST /get_sendlog_stats
        2.  Body: {"uuids": ["task1_uuid", "task2_uuid", ...]}

        :param request: UuidsRequest
        :return: dict
        """
        try:
            sendtask_uuids = request.sendtask_uuids
            if not sendtask_uuids:
                return {"status": "error", "message": "沒有收到 sendtask_uuids", "data": []}
            rows = await db.get_db(
                table_name="sendlog_stats", 
                column_names=["sendtask_uuid"],  # WHERE 條件欄位
                value=sendtask_uuids,           # 要查詢的 UUID 列表
                include_inactive=True           # 對 sendlog_stats 來說這個參數無效，但不會出錯
            )
            return {"status": "success", "data": rows}
        except Exception as e:
            logger.error(f"Error in get_sendlog_stats_batch: {str(e)}")
            return {"status": "error", "message": str(e), "data": []}

    return router

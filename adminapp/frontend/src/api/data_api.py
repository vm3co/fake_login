# -*- coding: utf-8 -*-
"""
Created on Thu May  8 14:32:44 2025

@author: 2501053

用api到se2系統抓取資料
"""
from fastapi import APIRouter
import os
import csv
import pandas as pd
from dotenv import load_dotenv

from app.services.log_manager import Logger
from app.services.getSe2data import get_se2_data
from app.core.db_controller import db
load_dotenv()
LOG_FILE = os.getenv("LOG_FILE", "/data/visit_log.csv")
router = APIRouter()

@router.get("/gettasks")
async def get_tasks():
    try:
        column_names = ["sendtask_id", "sendtask_uuid", "sendtask_create_ut"]
        my_tasksname_list = await db.get_db("sendtasks", column_names=column_names)
        return {"status": "success", "data": my_tasksname_list}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.get("/checktasks")
async def check_tasks():
    try:
        df = await get_se2_data.get_sendtasks()
        if df is None:
            return {"status": "error", "message": "get_se2_data error"}
        
        # 只取任務名稱及uuid
        column_names = ["sendtask_id", "sendtask_uuid", "sendtask_create_ut"]
        all_tasksname_list = df[column_names].to_dict(orient="records")
        my_tasksname_list = await db.get_db("sendtasks", column_names=column_names)

        all_set = set(tuple(sorted(d.items())) for d in all_tasksname_list)
        my_set = set(tuple(sorted(d.items())) for d in my_tasksname_list)
        # 找出差異
        added = all_set - my_set
        removed = my_set - all_set

        # 再轉回 list[dict] 格式
        added_list = [dict(t) for t in added]
        removed_list = [dict(t) for t in removed]

        # 新增
        await db.insert_db("sendtasks", added_list)
        for task in added_list:
            columns = {"id": "SERIAL PRIMARY KEY", 
                        "uuid": "TEXT",
                        "target_email": "TEXT", 
                        "access_active": "TEXT[]",
                        "access_ip": "TEXT[]",
                        "access_time": "BIGINT[]",
                        "person_info": "TEXT"
                        }
            await db.create_table(task["sendtask_uuid"], columns)
            df_sendlog = await get_se2_data.get_sendlog(task["sendtask_uuid"])
            if df_sendlog is not None:
                sendlog_columns = ["uuid", "target_email", "person_info"]
                sendlog = df_sendlog[sendlog_columns].to_dict(orient="records")
                await db.insert_db(task["sendtask_uuid"], sendlog)

        # 刪除(is_active=FASLE)
        for item in removed_list:
            await db.update_db(
                table_name="sendtasks",
                data={"is_active": False},
                condition={"sendtask_uuid": item["sendtask_uuid"]}
                )

        data = {"added": added_list, "removed": removed_list}
        return {"status": "success", "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.get("/showlog")
async def show_log():
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            data = [row for row in reader]

        return {"status": "success", "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.get("/createsendlogdata/{uuid}")
async def create_participant_data(uuid: str): 
    try:
        data = await db.get_db(uuid, include_inactive=True)
        if not data:
            return {"status": "success", "data": data}
        for dd in data:
            dd.pop("id", None)
        return {"status": "success", "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# -*- coding: utf-8 -*-
"""
Created on Thu May  8 14:32:44 2025

@author: 2501053

用api到se2系統抓取資料
"""
from fastapi import APIRouter, Request, Body, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any
import os
import csv
import io
import sys
import pandas as pd
from datetime import datetime, timedelta
import zipfile
import urllib.parse

from backend.services.log_manager import Logger
from backend.services.getSe2data import get_se2_data
from backend.services.time_utils import format_datetime
from backend.core.security import verify_password
from backend.core.security import hash_password
from backend.api.user_api import get_current_user


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

def process_data_for_excel(data: List[dict]) -> List[dict]:
    """
    處理撈出的原始資料，特別是 _time 結尾的欄位。
    """
    processed_data = []
    if not data:
        return []
        
    for row in data:  # row 是一個 dict
        processed_row = {}
        for col_name, value in row.items():
            
            # 檢查：欄位是否以 _time 結尾，且值不是 None
            if col_name.endswith('_time') and value is not None:
                
                # Case 1: 值是一個 list (例如 access_time)
                if isinstance(value, list) and value:
                    formatted_list = []
                    for ts in value:
                        try:
                            formatted_list.append(format_datetime(ts))
                        except (ValueError, TypeError, OSError):
                            formatted_list.append(str(ts))
                    processed_row[col_name] = "\n".join(formatted_list)
                
                # Case 2: 值是單一數字 (例如 plan_time)
                elif isinstance(value, (int, float)):
                    try:
                        processed_row[col_name] = format_datetime(value)
                    except (ValueError, TypeError, OSError):
                        processed_row[col_name] = str(value)
                
                # Case 3: 其他類型
                else:
                    processed_row[col_name] = value
            
            # Case 4: 非 time 欄位，或值為 None
            else:
                processed_row[col_name] = value
        
        processed_data.append(processed_row)
    return processed_data

def get_router(db, db_user):
    """
    初始化路由
    :param db: 資料庫實例
    :param db_user: 資料庫運用實例
    :return: APIRouter 實例
    """
    # router = APIRouter()
    router = APIRouter(dependencies=[Depends(get_current_user)])
    logger = Logger().get_logger()

    async def refresh_and_notify(refresh_list: list, username: str):
        await db_user.refresh_sendlog_stats(refresh_list)
        # Add notification
        await db.insert_db("notifications", {
            "username": username,
            "title": "統計資料刷新完成",
            "subtitle": f"已刷新 {len(refresh_list)} 個任務",
            "heading": "系統通知",
            "path": "send_list",
            "icon_name": "notifications",
            "icon_color": "primary"
        })

    ## sendtasks 相關的 API
    class OrgsRequest(BaseModel):
        orgs: list[str] = []

    @router.post(
        "/get_sendtasks",
        tags=["data"]
        )
    async def get_sendtasks(request: OrgsRequest):
        try:
            my_tasksname_list = await db.get_db("sendtasks")
            if request.orgs and request.orgs != ["admin"]:
                my_tasksname_list = [
                    task for task in my_tasksname_list
                    if has_common_orgs(task.get("sendtask_owner_gid", []), request.orgs)
                ]
            return {"status": "success", "data": my_tasksname_list}
        except Exception as e:
            logger.error(f"Error in get_sendtasks: {str(e)}")
            return {"status": "error", "message": str(e)}

    @router.post(
        "/check_sendtasks",
        tags=["data"]
        )
    async def check_sendtasks(request: OrgsRequest):
        """
        檢查sendtask是否有變更
        1. 讀取sendtask清單
        2. 與資料庫sendtask清單做diff
        3. 新增及刪除到sendtask資料庫
        """
        try:
            sendtasks_columns = ["sendtask_uuid", "sendtask_id", "sendtask_owner_gid", "person_count",
                                "pre_test_end_ut", "pre_test_start_ut", "pre_send_end_ut", "sendtask_create_ut", 
                                "test_end_ut", "test_start_ut", "is_pause", "pre_test_enable", "stop_time_new"]
            all_tasksname_list = await db_user.get_se2_sendtasks(column_names=sendtasks_columns)

            my_tasksname_list = await db.get_db("sendtasks", select_columns=sendtasks_columns)

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

            sendlog_stats_status = {}
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

            # 刪除
            for item in removed_list:
                uuid = item["sendtask_uuid"]
                # sendtasks刪除資料
                await db.delete_db(table_name="sendtasks", condition={"sendtask_uuid": uuid})
                # sendlog_stats 刪除資料
                await db.delete_db(table_name="sendlog_stats", condition={"sendtask_uuid": uuid})
                # 刪除table
                await db.drop_table(table_name=uuid)


            data = {"added": added_list, "removed": removed_list, "sendlog_stats_status": sendlog_stats_status}
            return {"status": "success", "data": data}
        except Exception as e:
            logger.error(f"Error in check_sendtasks: {str(e)}")
            return {"status": "error", "message": str(e)}
        
    @router.post(
        "/refresh_today_create_task",
        tags=["data"]
        )
    async def refresh_today_create_task(request: OrgsRequest, background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
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
            refresh_list.append(task["sendtask_uuid"])

        # sendlog_stats_status = await db_user.refresh_sendlog_stats(refresh_list)
        # background_tasks.add_task(db_user.refresh_sendlog_stats, refresh_list)
        username = current_user.get("username", "unknown")
        background_tasks.add_task(refresh_and_notify, refresh_list, username)

        return {"status": "success", "message": "已開始刷新任務統計資料 (背景執行中)", "data": {}}

    class CustomerGetSendtasksRequest(BaseModel):
        sendtask_uuids: list[str] = []

    @router.post(
        "/customer_get_sendtasks",
        tags=["data"]
        )
    async def get_sendtasks(request: CustomerGetSendtasksRequest):
        sendtask_uuids = request.sendtask_uuids
        if not sendtask_uuids:
            return {"status": "error", "message": "未收到sendtask_uuid"}

        try:
            data = await db.get_db("sendtasks", where_column="sendtask_uuid", values=sendtask_uuids)
            return {"status": "success", "data": data}
        except Exception as e:
            logger.error(f"Error in customer_get_sendtasks: {str(e)}")
            return {"status": "error", "message": str(e)}

    ## sendlog 相關的 API
    class SendLogRequest(BaseModel):
        sendtask_uuids: list[str] = []

    @router.post(
        "/refresh_sendlog_stats",
        tags=["data"]
        )
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
            return {"status": "success", "data": sendlog_stats_status}
        except Exception as e:
            logger.error(f"Error in refresh_sendlog_stats: {str(e)}")
            return {"status": "error", "message": str(e)}

    @router.post(
        "/get_sendlog_stats",
        tags=["data"]
        )
    async def get_sendlog_stats_batch(request: SendLogRequest):
        """
        取得多個任務的統計資料

        1.  POST /get_sendlog_stats
        2.  Body: {"uuids": ["task1_uuid", "task2_uuid", ...]}

        :param request: SendLogRequest
        :return: dict
        """
        try:
            sendtask_uuids = request.sendtask_uuids
            if not sendtask_uuids:
                return {"status": "error", "message": "沒有收到 sendtask_uuids", "data": []}
            rows = await db.get_db(
                table_name="sendlog_stats", 
                where_column="sendtask_uuid",
                values=sendtask_uuids
            )
            return {"status": "success", "data": rows}
        except Exception as e:
            logger.error(f"Error in get_sendlog_stats_batch: {str(e)}")
            return {"status": "error", "message": str(e), "data": []}

    class GetSendlogDetailRequest(BaseModel):
        sendtask_uuid: str
        page: int = 1
        acctControl: list[bool]
        rowsPerPage: int = 20
        searchText: str | None = None
        dateFrom: str | None = None
        dateTo: str | None = None
        resultType: str = "all"
        showAccessed: bool = False
        showClicked: bool = False
        showFiled: bool = False
        sort: str = "desc"
        sortBy: str = "plan_time"
        paginate: bool = True

    async def _query_sendlog_details(request: GetSendlogDetailRequest):
        """
        共用的查詢 sendlog 詳細資料的邏輯。
        """
        if not request.sendtask_uuid:
            raise ValueError("沒有收到 sendtask_uuid")

        where_clauses = []
        params = []
        param_idx = 1

        # 搜尋文字
        if request.searchText:
            where_clauses.append(f"(target_email ILIKE ${param_idx} OR person_info ILIKE ${param_idx})")
            params.append(f"%{request.searchText}%")
            param_idx += 1

        # 日期範圍篩選 (send_time)
        if request.dateFrom:
            try:
                start_date = datetime.strptime(request.dateFrom, "%Y-%m-%d")
                start_timestamp = int(start_date.timestamp())
                where_clauses.append(f"send_time >= ${param_idx}")
                params.append(start_timestamp)
                param_idx += 1
            except ValueError:
                pass  # 忽略無效的日期格式

        if request.dateTo:
            try:
                end_date = datetime.strptime(request.dateTo, "%Y-%m-%d")
                # 包含結束日期的整天，所以設定到當天的 23:59:59
                end_timestamp = int((end_date + timedelta(days=1)).timestamp()) - 1
                where_clauses.append(f"send_time <= ${param_idx}")
                params.append(end_timestamp)
                param_idx += 1
            except ValueError:
                pass # 忽略無效的日期格式

        
        # 寄送狀態
        isSend, isFailed, isNotyet, isNotTriggered, isTriggered = request.acctControl
        sent_base = "send_time IS NOT NULL AND send_time > 0"
        sent_success = "send_res IS NOT NULL AND send_res ILIKE '%True%'"
        sent_failure = "send_res IS NOT NULL AND send_res ILIKE '%False%'"
        not_sent = "send_time IS NULL OR send_time = 0"

        not_triggered_cond = "array_length(access_time, 1) IS NULL AND array_length(access_src, 1) IS NULL AND array_length(access_dev, 1) IS NULL"
        triggered_cond = "array_length(access_time, 1) > 0 OR array_length(access_src, 1) > 0 OR array_length(access_dev, 1) > 0"

        if request.resultType == 'all':
            
            if isSend and isFailed and isNotyet and isNotTriggered and isTriggered:
                pass
            elif not isSend and not isFailed and not isNotyet and not isNotTriggered and not isTriggered:
                where_clauses.append("(1=0)")
            else:
                all_clauses = []
                if isFailed:
                    all_clauses.append(f"({sent_base} AND {sent_failure})")
                if isNotyet:
                    all_clauses.append(f"({not_sent})")
                if isSend:
                    if isNotTriggered and not isTriggered:
                        all_clauses.append(f"({sent_base} AND {sent_success} AND {not_triggered_cond})")
                    elif not isNotTriggered and isTriggered:
                        all_clauses.append(f"({triggered_cond})")
                    else:
                        all_clauses.append(f"({sent_base} AND {sent_success})")
                where_clauses.append(" OR ".join(all_clauses))

        elif request.resultType == 'send':
            where_clauses.append(f"({sent_base} AND {sent_success})")
        elif request.resultType == 'notyet':
            where_clauses.append(f"({not_sent})")
        elif request.resultType == 'failed':
            where_clauses.append(f"({sent_base} AND {sent_failure})")
        elif request.resultType == 'notTriggered':
            where_clauses.append(f"({sent_base} AND {sent_success} AND {not_triggered_cond})")
        elif request.resultType == 'triggered':
            where_clauses.append(f"({triggered_cond})")

        # 行為過濾
        if request.showAccessed:
            where_clauses.append("array_length(access_time, 1) > 0")
        if request.showClicked:
            where_clauses.append("array_length(click_time, 1) > 0")
        if request.showFiled:
            where_clauses.append("array_length(file_time, 1) > 0")

        # 排序
        sort_map = {
            "target_email": "target_email",
            "plan_time": "plan_time",
            "send_time": "send_time",
            "person_info": "person_info"
        }
        sort = {
            "asc": "ASC",
            "desc": "DESC"
        }
        order_by = f"{sort_map.get(request.sortBy, "plan_time DESC")} {sort.get(request.sort, "DESC")}"

        result = await db.get_paginated_db(
            table_name=request.sendtask_uuid,
            paginate=request.paginate,
            page=request.page,
            rows_per_page=request.rowsPerPage,
            where_clauses=where_clauses,
            params=params,
            order_by=order_by
        )

        # 處理觸發紀錄，只留最後一筆
        trigger_columns = ["access_time", "access_src", "access_dev",
                            "click_time", "click_src", "click_dev", 
                            "file_time", "file_src", "file_dev",
                            "second_access_time", "second_access_src", "second_access_dev", 
                            "second_input_time", "second_input_src", 
                            "second_input_dev", "second_input_info"]
        for data in result["data"]:
            for col in trigger_columns:
                if col in data and isinstance(data[col], list):
                    data[col] = data[col][-1] if data[col] else None

        return result

    @router.post(
        "/get_sendlog_detail",
        tags=["data"]
        )
    async def get_sendlog_detail(request: GetSendlogDetailRequest):
        """
        根據條件取得單一任務的詳細 sendlog 資料 (支援分頁、篩選、排序)
        """
        if not request.sendtask_uuid:
            return {"status": "error", "message": "沒有收到 sendtask_uuid"}

        try:
            result = await _query_sendlog_details(request)
            if not result['data']:
                return {"status": "error", "message": "沒有符合條件的資料", "data": [], "total_count": 0}
            
            return {"status": "success", "data": result['data'], "total_count": result['total_count']}
        except Exception as e:
            logger.error(f"Error in get_sendlog_detail for {request.sendtask_uuid}: {str(e)}")
            if "does not exist" in str(e):
                return {"status": "error", "message": f"找不到任務 {request.sendtask_uuid} 的日誌資料表。", "data": [], "total_count": 0}
            return {"status": "error", "message": str(e), "data": [], "total_count": 0}

    class DownloadRequest(BaseModel):
        sendtask_uuid: str
        name: str

    @router.post("/download_sendlog_xlsx")
    async def api_download_sendlog_xlsx(request: DownloadRequest):
        
        await db.check_db_connection()
        
        try:
            # --- A. 獲取資料 (簡化邏輯) ---
            # 直接使用你 db_controller.py 中的 get_db 函式
            
            data = await db.get_db(
                table_name=request.sendtask_uuid
            )

            if not data:
                return StreamingResponse(
                    io.BytesIO(b"No data found for this task uuid."), 
                    status_code=404, 
                    media_type="text/plain"
                )

            # --- B. 處理資料 (使用我們提煉的函式) ---
            processed_data = process_data_for_excel(data)

            mtmpl_list = await db.get_db(
                table_name="mtmpl",
                select_columns=["mtmpl_uuid", "mtmpl_title"]
            )

            for data in processed_data:
                del data["uuid"]
                data["mtmpl_name"] = ""
                for mtmpl in mtmpl_list:
                    if mtmpl.get("mtmpl_uuid") == data.get("template_uuid"):
                        data["mtmpl_name"] = mtmpl.get("mtmpl_title", "")
                        del data["template_uuid"]
                        break
                for col_name, value in data.items():
                    if isinstance(value, list) and value:
                        data[col_name] = "\n".join(value)
                    elif not value:
                        data[col_name] = "-"
                        
            # --- C. 轉換為 Pandas 並存入記憶體 ---
            df = pd.DataFrame(processed_data)

            # 重新命名欄位，讓 Excel 標頭更易讀
            df.rename(columns={
                'target_email': '受測人信箱',
                'mtmpl_name': '信件名稱', 
                'person_info': '受測人姓名',
                'plan_time': '預計寄送時間',
                'send_time': '實際寄送時間',
                'send_res': '寄送結果',
                'second_access_time': '連結點擊時間',
                'second_access_src': '連結點擊IP', 
                'second_access_dev': '連結點擊資訊', 
                'second_input_time': '表單填寫時間', 
                'second_input_src': '表單填寫IP', 
                'second_input_dev': '表單填寫資訊', 
                'second_input_info': '表單填寫內容', 
                'access_time': '郵件讀取時間',
                'access_src': '郵件讀取IP',
                'access_dev': '郵件讀取資訊',
                'click_time': '按鈕點擊時間',
                'click_src': '按鈕點擊IP',
                'click_dev': '按鈕點擊資訊',
                'file_time': '附件下載時間',
                'file_src': '附件下載IP',
                'file_dev': '附件下載資訊'
            }, inplace=True)

            # 建立一個在記憶體中的 Excel 檔案
            output_buffer = io.BytesIO()
            df.to_excel(output_buffer, index=False)
            output_buffer.seek(0) # 將指標移回開頭

            # --- D. 回傳檔案串流 ---

            filename = urllib.parse.quote(f"{request.name}.xlsx")
            headers = {
                'Content-Disposition': f'attachment; filename="{request.sendtask_uuid}.xlsx"; filename*=UTF-8\'\'{filename}'
            }
            
            return StreamingResponse(
                output_buffer, 
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers=headers
            )

        except Exception as e:
            error_message = f"Error generating file: {e}"
            print(f"下載 Excel 失敗: {error_message}", file=sys.stderr)
            
            return StreamingResponse(
                io.BytesIO(error_message.encode('utf-8')), 
                status_code=500,
                media_type="text/plain; charset=utf-8"
            )

    class DownloadSendlogRequest(GetSendlogDetailRequest):
        sendtask_uuid: str
        selected_uuids: list[str] | None = None
        searchText: str | None = None
        dateFrom: str | None = None
        dateTo: str | None = None
        resultType: str = "all"
        showAccessed: bool = False
        showClicked: bool = False
        showFiled: bool = False
        sort: str = "desc"
        sortBy: str = "plan_time"
        paginate: bool = False

    @router.post(
        "/download_se2_sendlog_xlsx",
        tags=["data"]
        )
    async def download_se2_sendlog_xlsx(request: DownloadSendlogRequest):
        """
        根據條件下載 sendlog 資料為 CSV 檔案。
        如果提供了 selected_uuids，則只下載這些 uuid 的資料。
        否則，下載符合篩選條件的所有資料。
        """
        try:
            if request.selected_uuids:
                all_data = await db.get_db(
                    table_name=request.sendtask_uuid,
                    where_column="uuid",
                    values=request.selected_uuids
                )
            else:
                result = await _query_sendlog_details(request)
                all_data = result.get('data', [])

            if not all_data:
                return {"status": "error", "message": "沒有可下載的資料"}

            # 處理時間格式與觸發紀錄(只留最後一筆)
            timestamp_columns = ["plan_time", "send_time", "access_time", "click_time", "file_time"]

            processed_data = []
            for data in all_data:
                for col in timestamp_columns:
                    if col in data:
                        data[col] = format_datetime(data.get(col))
                mtmpl_name = await db.get_db(
                    table_name="mtmpl",
                    where_column="mtmpl_uuid",
                    values=[data.get("template_uuid", "")]
                )
                data["mtmpl_name"] = mtmpl_name[0].get("mtmpl_title", "")

                final_columns = ["target_email", "person_info", "mtmpl_name", "plan_time",
                                "send_time", "send_res", "access_time", "access_src", "access_dev",
                                "click_time", "click_src", "click_dev", "file_time", "file_src", "file_dev"]

                filtered_row = {col: data.get(col, "") for col in final_columns}
                processed_data.append(filtered_row)

            # 將資料轉換為 CSV
            output = io.StringIO()
            writer = csv.writer(output)
            
            # 寫入標頭
            if processed_data:
                writer.writerow(processed_data[0].keys())
                # 寫入資料
                for row in processed_data:
                    writer.writerow(row.values())

            output.seek(0)
            csv_data = output.getvalue().encode('utf-8-sig')

            return StreamingResponse(
                io.BytesIO(csv_data),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=sendlog_{request.sendtask_uuid}.csv"}
            )

        except Exception as e:
            logger.error(f"Error in download_se2_sendlog_xlsx for {request.sendtask_uuid}: {str(e)}")
            return {"status": "error", "message": str(e)}

    ## mtmpl 相關的 API
    @router.get(
        "/get_mtmpl",
        tags=["data"]
        )
    async def get_mtmpl():
        """
        取得 mtmpl (郵件樣板) 資料表中的所有資料

        1. GET /get_mtmpl
        """
        try:
            mtmpl_data = await db.get_db(table_name="mtmpl")
            return {"status": "success", "data": mtmpl_data}
        except Exception as e:
            logger.error(f"Error in get_mtmpl: {str(e)}")
            return {"status": "error", "message": str(e), "data": []}
        
    @router.post(
        "/update_mtmpl",
        tags=["data"]
        )
    async def update_mtmpl():
        """
        從 SE2 獲取最新的郵件樣板資料，並與本地資料庫比對更新。

        1. POST /update_mtmpl
        """
        try:
            # 1. 從 SE2 獲取最新資料
            se2_mtmpl_list = await db_user.get_se2_mtmpl()
            if se2_mtmpl_list is None:
                return {"status": "error", "message": "從 SE2 獲取郵件樣板失敗"}

            # 2. 從本地資料庫獲取現有資料
            local_mtmpl_list = await db.get_db("mtmpl")

            # 3. 準備比對用的集合 (使用 mtmpl_uuid 作為唯一鍵)
            se2_uuids = {item['mtmpl_uuid']: item for item in se2_mtmpl_list}
            local_uuids = {item['mtmpl_uuid']: item for item in local_mtmpl_list}

            # 4. 找出差異
            added_uuids = set(se2_uuids.keys()) - set(local_uuids.keys())
            removed_uuids = set(local_uuids.keys()) - set(se2_uuids.keys())

            added_list = [se2_uuids[uuid] for uuid in added_uuids]
            removed_list = [local_uuids[uuid] for uuid in removed_uuids]

            # 5. 執行更新
            # 新增樣板
            if added_list:
                for item in added_list:
                    await db.insert_db("mtmpl", item)
                logger.info(f"Added {len(added_list)} new mail templates.")

            # 刪除樣板
            if removed_list:
                for item in removed_list:
                    await db.delete_db("mtmpl", {"mtmpl_uuid": item["mtmpl_uuid"]})
                logger.info(f"Removed {len(removed_list)} old mail templates.")

            # 6. 回傳結果
            return {
                "status": "success",
                "data": {
                    "added": added_list,
                    "removed": removed_list
                }
            }
        except Exception as e:
            logger.error(f"Error in update_mtmpl: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    ## 匯出csv API
    class ExportCsvRequest(BaseModel):
        sendtasks: dict | None = None
    
    @router.post(
        "/export_xlsx",
        tags=["data"]
        )
    async def export_xlsx(request: ExportCsvRequest):
        """
        匯出 sendtask 的參與人員清單
        Body: {sendtask_id_A: [sendtasks_uuid_A, pre_test_enable_A], sendtask_id_B: [sendtasks_uuid_B, pre_test_enable_B], ...}
        """
        sendtasks = request.sendtasks
        if not sendtasks:
            return {"status": "error", "message": "缺少 sendtasks"}

        zip_buffer = io.BytesIO()
        failed_tasks = []
        downloaded_tasks = []
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for sendtask_id, sendtask_content in sendtasks.items():
                try:
                    xlsx_content = await get_se2_data.export_xlsx(sendtask_content)
                    if not xlsx_content:
                        failed_tasks.append(sendtask_id)
                        continue  # 若無資料則跳過
                    filename = f"{sendtask_id}.xlsx"
                    zip_file.writestr(filename, xlsx_content)
                    downloaded_tasks.append(sendtask_id)
                except Exception as e:
                    logger.error(f"Error in export_xlsx: {str(e)}")
                    failed_tasks.append(sendtask_id)
                    continue
            # 新增 下載狀況.txt 檔案
            summary_content = "下載成功的任務:\n"
            summary_content += "\n".join(downloaded_tasks) + "\n\n"
            summary_content += "下載失敗的任務:\n"
            summary_content += "\n".join(failed_tasks) + "\n"
            zip_file.writestr("下載狀況.txt", summary_content)

        zip_buffer.seek(0)
        now_str = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename=sendtasks_export_{now_str}.zip"}
        )

    ## customer 相關的 API
    class GetCustomersRequest(BaseModel):
        acct_uuid: str = ""

    @router.post(
        "/get_customers",
        tags=["data"]
        )
    async def get_customers(request: GetCustomersRequest):
        """
        取得客戶帳號列表

        1. POST /get_customers
        2. Body: {"acct_uuid": string}

        :param request: 包含acct_uuid的請求數據
        :return: dict, 包含客戶帳號列表
        """
        acct_uuid = request.acct_uuid
        if not acct_uuid:
            return {"status": "error", "message": "沒有收到 acct_uuid"}
        try:
            customers = await db.get_db(
                table_name="customer_accts", 
                where_column="acct_uuid", 
                values=[acct_uuid]
            )
            return {"status": "success", "data": customers}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    class CreateCustomerRequest(BaseModel):
        customer_name: str = ""
        customer_full_name: str = ""
        password: str = ""
        acct_uuid: str = ""

    @router.post(
        "/create_customer",
        tags=["data"]
        )
    async def create_customer(request: CreateCustomerRequest):
        """
        建立客戶帳號

        1. POST /create_customer
        2. Body: {"customer_name": ..., "customer_full_name": ..., "password_hash": ..., "acct_uuid": ...}

        :param request: 包含客戶名稱、密碼、任務列表、創建人uuid
        :return: dict, 請求的結果狀態
        """
        data = {
            "customer_name": request.customer_name,
            "customer_full_name": request.customer_full_name,
            "password_hash": hash_password(request.password),
            "acct_uuid": request.acct_uuid
        }
        if not data:
            return {"status": "error", "message": "沒有收到客戶資料"}
        try:
            if await db_user.customer_exists(customer_name=data["customer_name"]):
                return {"status": "error", "message": "客戶帳號已存在"}
            else:
                return await db_user.insert_customer(data=data)
        except Exception as e:
            return {"status": "error", "message": str(e)}

    class SendtaskItem(BaseModel):
        uuid: str
        send: bool
        notyet: bool
        failed: bool
        notTriggered: bool
        triggered: bool

    class UpdateCustomerSendtasksRequest(BaseModel):
        customer_name: str = ""
        sendtasks_for_db: List[SendtaskItem] = []

    @router.post(
        "/update_customer_sendtasks",
        tags=["data"]
        )
    async def update_customer_sendtasks(request: UpdateCustomerSendtasksRequest):
        """
        更新客戶帳號裡的任務

        1. POST /update_customer_sendtasks
        2. Body: {"customer_name": ..., "sendtasks_for_db": [...]}

        :param request: 包含客戶名稱和任務列表的請求數據
        :return: dict, 請求的結果狀態
        """
        customer_name = request.customer_name
        sendtasks_data = request.sendtasks_for_db

        if not customer_name or not sendtasks_data:
            return {"status": "error", "message": "沒有收到資料"}

        try:
            sendtasks_list_of_dicts = [task.model_dump() for task in sendtasks_data]
            status = await db_user.update_customer_sendtasks(customer_name, sendtasks_list_of_dicts)
            return {"status": "success", "message": status}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    class DeleteCustomerRequest(BaseModel):
        del_customer_names: list[str] = []

    @router.post(
        "/delete_customer",
        tags=["data"]
        )
    async def delete_customer(request: DeleteCustomerRequest):
        """
        刪除客戶帳號

        1. POST /delete_customer
        2. Body: {"del_customer_names": list[str]}

        :param request: 包含客戶名稱的請求數據
        :return: dict, 請求的結果狀態
        """
        del_customer_names = request.del_customer_names
        if not del_customer_names:
            return {"status": "error", "message": "沒有收到資料"}
        try:
            for name in del_customer_names:
                await db.delete_db("customer_accts", condition={"customer_name": name})
            return {"status": "success", "message": del_customer_names}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    class UpdateCustomerPasswordRequest(BaseModel):
        customer_name: str = ""
        old_password: str = ""
        new_password: str = ""

    @router.post(
        "/update_customer_password",
        tags=["data"]
        )
    async def update_customer_password(request: UpdateCustomerPasswordRequest):
        """
        更新客戶帳號密碼

        1. POST /update_customer_password
        2. Body: {"customer_name": ..., "old_password":..., "new_password": ...}

        :param request: 包含客戶名稱、舊密碼及新密碼的請求數據
        :return: dict, 請求的結果狀態
        """
        customer_name = request.customer_name
        old_password = request.old_password
        new_password = request.new_password

        if not customer_name or not old_password or not new_password:
            return {"status": "error", "message": "沒有收到資料"}
        try:
            # 驗證舊密碼
            customer_info = await db.get_db(
                table_name="customer_accts", 
                where_column="customer_name", 
                values=[customer_name]
            )
            if not customer_info or not verify_password(old_password, customer_info[0]["password_hash"]):
                return {"status": "error", "message": "舊密碼錯誤"}

            # 更新新密碼
            new_password_hash = hash_password(new_password)
            await db.update_db(
                table_name="customer_accts", 
                condition={"customer_name": customer_name}, 
                data={"password_hash": new_password_hash}
            )
            return {"status": "success", "message": "密碼更新成功"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    return router





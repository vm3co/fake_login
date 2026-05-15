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
import re

from sqlalchemy import select, update, delete, func, desc, asc, text, String, cast, literal
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.dialects.postgresql import insert as pg_insert
from backend.repository.db_controller import db_controller
from backend.repository.models import SendTask, Mtmpl, Notification, SendLogStats, SendLogDetail, CustomerAcct, CustomerTask
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

_CN_DIGITS = ["", "一", "二", "三", "四", "五", "六", "七", "八", "九"]


def _parse_person_info(person_info: str) -> tuple[str, str, str]:
    """解析 'Name / (Group-Sub)' → (name, group, subgroup)。"""
    if not person_info:
        return ("", "", "")
    if " / " not in person_info:
        return (person_info.strip(), "", "")
    name_part, rest = person_info.split(" / ", 1)
    name = name_part.strip()
    rest = rest.strip()
    if rest.startswith("(") and rest.endswith(")"):
        inner = rest[1:-1]
        if "-" in inner:
            group, subgroup = inner.split("-", 1)
            return (name, group.strip(), subgroup.strip())
        return (name, inner.strip(), "")
    return (name, rest, "")


def _fmt_ts(ts) -> str:
    """單一 timestamp → 'yyyy-mm-dd hh:mm:ss'，空值回空字串。"""
    if not ts:
        return ""
    return format_datetime(ts)


def _fmt_ts_list(arr) -> str:
    """list[int] → 每筆 format_datetime 後以換行合併。"""
    if not arr:
        return ""
    return "\n".join(_fmt_ts(ts) for ts in arr if ts)


def _join_list(arr) -> str:
    """list[str] → 換行合併；空/None 回空字串。"""
    if not arr:
        return ""
    return "\n".join(str(v) for v in arr if v is not None)


def _alias(i: int) -> str:
    """依序產生 '信件一'、'信件二'... 最多支援到九十九，超過則 fallback 阿拉伯數字。"""
    num = i + 1
    if num <= 9:
        cn = _CN_DIGITS[num]
    elif num == 10:
        cn = "十"
    elif num < 20:
        cn = "十" + _CN_DIGITS[num % 10]
    elif num <= 99:
        tens = num // 10
        ones = num % 10
        cn = _CN_DIGITS[tens] + "十" + _CN_DIGITS[ones]
    else:
        cn = str(num)
    return f"信件{cn}"


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

def get_router(db_user):
    """
    初始化路由
    :param db_user: 資料庫運用實例
    :return: APIRouter 實例
    """
    # router = APIRouter()
    router = APIRouter(dependencies=[Depends(get_current_user)])
    logger = Logger().get_logger()

    async def refresh_and_notify(refresh_list: list, username: str):
        await db_user.refresh_sendlog_stats(refresh_list)
        # Add notification
        await db_controller.create(Notification, {
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
            tasks = await db_controller.get(SendTask)
            
            # Convert to list of dicts
            my_tasksname_list = []
            for t in tasks:
                # Manually convert or use a helper
                my_tasksname_list.append({c.name: getattr(t, c.name) for c in t.__table__.columns})

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
            result = await db_user.sync_sendtasks(orgs=request.orgs)

            sendlog_stats_status = {}
            if result["added"]:
                refresh_list = [task["sendtask_uuid"] for task in result["added"]]
                sendlog_stats_status = await db_user.refresh_sendlog_stats(
                    refresh_list,
                    ignore_archived=True,
                    skip_sendtask_sync=True,
                )

            data = {
                "added": result["added"],
                "changed": result["changed"],
                "archived": result["archived"],
                "removed": result["deleted"],
                "sendlog_stats_status": sendlog_stats_status,
            }
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
        
        
        refresh_list = [task["sendtask_uuid"] for task in today_create_task_list]
        await db_controller.upsert(
            SendTask,
            today_create_task_list,
            index_elements=['sendtask_uuid']
        )

        sendlog_stats_status = await db_user.refresh_sendlog_stats(refresh_list)

        # Send notification in background
        username = current_user.get("username", "unknown")
        background_tasks.add_task(refresh_and_notify, refresh_list, username)

        return {"status": "success", "message": "刷新完成", "data": sendlog_stats_status}

    class CustomerGetSendtasksRequest(BaseModel):
        sendtask_uuids: list[str] = []

    # 客戶端只需要看到的 sendtask 欄位（排除敏感資訊如 owner_gid、server_url 等）
    CUSTOMER_SENDTASK_FIELDS = [
        "sendtask_uuid", "sendtask_id", "test_start_ut", "test_end_ut",
        "stop_time_new", "is_pause", "pre_test_enable",
        "pre_test_start_ut", "pre_test_end_ut",
    ]

    @router.post(
        "/customer_get_sendtasks",
        tags=["data"]
        )
    async def customer_get_sendtasks(request: CustomerGetSendtasksRequest, current_user: dict = Depends(get_current_user)):
        sendtask_uuids = request.sendtask_uuids
        if not sendtask_uuids:
            return {"status": "error", "message": "未收到sendtask_uuid"}

        try:
            # 客戶身份驗證：確認請求的 sendtask_uuids 屬於該客戶
            if current_user.get("user_type") == "customer":
                customer = await db_controller.get_one(
                    CustomerAcct, {"customer_name": current_user.get("username")}
                )
                if not customer:
                    return {"status": "error", "message": "找不到客戶帳號"}
                # 從客戶帳號取得允許的 sendtask uuid 清單
                allowed_uuids = {t["uuid"] for t in (customer.sendtasks or []) if isinstance(t, dict)}
                # 過濾：只保留客戶有權查看的 uuid
                sendtask_uuids = [u for u in sendtask_uuids if u in allowed_uuids]
                if not sendtask_uuids:
                    return {"status": "success", "data": []}

            rows = await db_controller.get(SendTask, filters={"sendtask_uuid": sendtask_uuids})

            # 客戶身份：只回傳安全欄位；管理員/使用者：回傳全部欄位
            if current_user.get("user_type") == "customer":
                data = [
                    {field: getattr(r, field) for field in CUSTOMER_SENDTASK_FIELDS if hasattr(r, field)}
                    for r in rows
                ]
            else:
                data = [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in rows]

            return {"status": "success", "data": data}
        except Exception as e:
            logger.error(f"Error in customer_get_sendtasks: {str(e)}")
            return {"status": "error", "message": str(e)}

    ## sendlog 相關的 API
    class SendLogRequest(BaseModel):
        sendtask_uuids: list[str] = []
        ignore_archived: bool = False

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

            sendlog_stats_status = await db_user.refresh_sendlog_stats(uuids, ignore_archived=request.ignore_archived)
            return {"status": "success", "data": sendlog_stats_status}
        except Exception as e:
            logger.error(f"Error in refresh_sendlog_stats: {str(e)}")
            return {"status": "error", "message": str(e)}

    # 客戶端只需要看到的 sendlog_stats 欄位
    CUSTOMER_STATS_FIELDS = [
        "sendtask_uuid", "totalplanned", "totalsend", "totalsuccess",
        "totalfailed", "totaltriggered",
    ]

    @router.post(
        "/get_sendlog_stats",
        tags=["data"]
        )
    async def get_sendlog_stats_batch(request: SendLogRequest, current_user: dict = Depends(get_current_user)):
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

            # 客戶身份驗證：確認請求的 sendtask_uuids 屬於該客戶
            if current_user.get("user_type") == "customer":
                customer = await db_controller.get_one(
                    CustomerAcct, {"customer_name": current_user.get("username")}
                )
                if not customer:
                    return {"status": "error", "message": "找不到客戶帳號", "data": []}
                allowed_uuids = {t["uuid"] for t in (customer.sendtasks or []) if isinstance(t, dict)}
                sendtask_uuids = [u for u in sendtask_uuids if u in allowed_uuids]
                if not sendtask_uuids:
                    return {"status": "success", "data": []}

            rows_obj = await db_controller.get(SendLogStats, filters={"sendtask_uuid": sendtask_uuids})

            # 客戶身份：只回傳精簡欄位；管理員/使用者：回傳全部欄位
            if current_user.get("user_type") == "customer":
                rows = [
                    {field: getattr(r, field) for field in CUSTOMER_STATS_FIELDS if hasattr(r, field)}
                    for r in rows_obj
                ]
            else:
                rows = [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in rows_obj]

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
        filterIp: str | None = None  # 以逗點分隔的排除 IP 字串

    async def _query_sendlog_details(request: GetSendlogDetailRequest):
        """
        共用的查詢 sendlog 詳細資料的邏輯。
        """
        if not request.sendtask_uuid:
            raise ValueError("沒有收到 sendtask_uuid")

        # Start building the query
        stmt = select(SendLogDetail).where(SendLogDetail.sendtask_uuid == request.sendtask_uuid)

        # 搜尋文字
        if request.searchText:
            search_text = f"%{request.searchText}%"
            stmt = stmt.where(
                (SendLogDetail.target_email.ilike(search_text)) | 
                (SendLogDetail.person_info.ilike(search_text))
            )

        # 日期範圍篩選 (send_time)
        if request.dateFrom:
            try:
                start_date = datetime.strptime(request.dateFrom, "%Y-%m-%d")
                start_timestamp = int(start_date.timestamp())
                stmt = stmt.where(SendLogDetail.send_time >= start_timestamp)
            except ValueError:
                pass

        if request.dateTo:
            try:
                end_date = datetime.strptime(request.dateTo, "%Y-%m-%d")
                end_timestamp = int((end_date + timedelta(days=1)).timestamp()) - 1
                stmt = stmt.where(SendLogDetail.send_time <= end_timestamp)
            except ValueError:
                pass
        
        # 寄送狀態
        isSend, isFailed, isNotyet, isNotTriggered, isTriggered = request.acctControl
        
        # Define conditions
        sent_base = (SendLogDetail.send_time.isnot(None)) & (SendLogDetail.send_time > 0)
        sent_success = SendLogDetail.send_res.ilike('%True%')
        sent_failure = SendLogDetail.send_res.ilike('%False%')
        not_sent = (SendLogDetail.send_time.is_(None)) | (SendLogDetail.send_time == 0)

        # Array length checks for triggered/not triggered
        # func.array_length requires (array, dimension)
        # We check if array_length > 0 or array_length IS NULL
        
        has_access = func.array_length(SendLogDetail.access_time, 1) > 0
        has_src = func.array_length(SendLogDetail.access_src, 1) > 0
        has_dev = func.array_length(SendLogDetail.access_dev, 1) > 0
        
        triggered_cond = has_access | has_src | has_dev
        not_triggered_cond = (~has_access | func.array_length(SendLogDetail.access_time, 1).is_(None)) & \
                             (~has_src | func.array_length(SendLogDetail.access_src, 1).is_(None)) & \
                             (~has_dev | func.array_length(SendLogDetail.access_dev, 1).is_(None))


        if request.resultType == 'all':
            if isSend and isFailed and isNotyet and isNotTriggered and isTriggered:
                pass
            elif not isSend and not isFailed and not isNotyet and not isNotTriggered and not isTriggered:
                stmt = stmt.where(text("1=0")) # No results
            else:
                conditions = []
                if isFailed:
                    conditions.append(sent_base & sent_failure)
                if isNotyet:
                    conditions.append(not_sent)
                if isSend:
                    if isNotTriggered and not isTriggered:
                        conditions.append(sent_base & sent_success & not_triggered_cond)
                    elif not isNotTriggered and isTriggered:
                        conditions.append(triggered_cond)
                    else:
                        conditions.append(sent_base & sent_success)
                
                if conditions:
                    from sqlalchemy import or_
                    stmt = stmt.where(or_(*conditions))

        elif request.resultType == 'send':
            stmt = stmt.where(sent_base & sent_success)
        elif request.resultType == 'notyet':
            stmt = stmt.where(not_sent)
        elif request.resultType == 'failed':
            stmt = stmt.where(sent_base & sent_failure)
        elif request.resultType == 'notTriggered':
            stmt = stmt.where(sent_base & sent_success & not_triggered_cond)
        elif request.resultType == 'triggered':
            stmt = stmt.where(triggered_cond)

        # 行為過濾
        if request.showAccessed:
            stmt = stmt.where(func.array_length(SendLogDetail.access_time, 1) > 0)
        if request.showClicked:
            stmt = stmt.where(func.array_length(SendLogDetail.click_time, 1) > 0)
        if request.showFiled:
            stmt = stmt.where(func.array_length(SendLogDetail.file_time, 1) > 0)

        # 排序
        sort_column = getattr(SendLogDetail, request.sortBy, SendLogDetail.plan_time)
        if request.sort == "asc":
            stmt = stmt.order_by(asc(sort_column))
        else:
            stmt = stmt.order_by(desc(sort_column))

        # Pagination
        # Get total count first
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_counts = await db_controller.execute_scalars(count_stmt)
        total_count = total_counts[0] if total_counts else 0

        if request.paginate:
            stmt = stmt.offset((request.page - 1) * request.rowsPerPage).limit(request.rowsPerPage)

        rows = await db_controller.execute_scalars(stmt)
            
        # 解析排除 IP，準備在 Python 層級過濾紀錄
        exact_ips = []
        wildcard_regex = None
        if request.filterIp:
            import re
            ip_list = [ip.strip() for ip in request.filterIp.split(',') if ip.strip()]
            wildcard_patterns = []
            for ip in ip_list:
                if not re.match(r'^[0-9a-fA-F\.\:\*]+$', ip):
                    continue
                if '*' in ip:
                    wildcard_patterns.append(ip.replace('.', r'\.').replace('*', '.*'))
                else:
                    exact_ips.append(ip)
            if wildcard_patterns:
                wildcard_regex = re.compile('^(' + '|'.join(wildcard_patterns) + ')$')

        def is_ip_excluded(ip_addr):
            if not ip_addr:
                return False
            if ip_addr in exact_ips:
                return True
            if wildcard_regex and wildcard_regex.match(ip_addr):
                return True
            return False

        # Convert to dicts
        data = []
        trigger_columns = ["access_time", "access_src", "access_dev",
                            "click_time", "click_src", "click_dev", 
                            "file_time", "file_src", "file_dev",
                            "second_access_time", "second_access_src", "second_access_dev", 
                            "second_qrcode_time", "second_qrcode_src", "second_qrcode_dev",
                            "second_input_time", "second_input_src", 
                            "second_input_dev", "second_input_info"]
        
        src_bases = ["access", "click", "file", "second_access", "second_qrcode", "second_input"]

        for row in rows:
            item = {c.name: getattr(row, c.name) for c in row.__table__.columns}
            
            # 如果有設定排除 IP，過濾陣列中對應的紀錄
            if exact_ips or wildcard_regex:
                for base in src_bases:
                    src_col = f"{base}_src"
                    # 找出同群組的其他欄位
                    related_cols = [c for c in trigger_columns if c.startswith(base) and c != src_col]

                    if item.get(src_col) and isinstance(item[src_col], list):
                        src_list = item[src_col]
                        keep_indices = []
                        for i, ip_addr in enumerate(src_list):
                            if not is_ip_excluded(ip_addr):
                                keep_indices.append(i)
                        
                        # 把不需要的 index 濾掉
                        filtered_src_list = [src_list[i] for i in keep_indices]
                        item[src_col] = filtered_src_list if filtered_src_list else None
                        
                        for r_col in related_cols:
                            if item.get(r_col) and isinstance(item[r_col], list):
                                r_list = item[r_col]
                                filtered_r_list = [r_list[i] for i in keep_indices if i < len(r_list)]
                                item[r_col] = filtered_r_list if filtered_r_list else None

            # 處理觸發紀錄，只留最後一筆
            for col in trigger_columns:
                if col in item and isinstance(item[col], list):
                    item[col] = item[col][-1] if item[col] else None
            data.append(item)

        return {"data": data, "total_count": total_count}

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
        
        try:
            # --- A. 獲取資料 (簡化邏輯) ---
            rows = await db_controller.get(SendLogDetail, filters={"sendtask_uuid": request.sendtask_uuid})
            data = [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in rows]

            if not data:
                return StreamingResponse(
                    io.BytesIO(b"No data found for this task uuid."), 
                    status_code=404, 
                    media_type="text/plain"
                )

            # --- B. 處理資料 (使用我們提煉的函式) ---
            processed_data = process_data_for_excel(data)

            # Get templates
            mtmpl_models = await db_controller.get(Mtmpl)
            mtmpl_list = [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in mtmpl_models]

            for data in processed_data:
                # data is a dict here from process_data_for_excel
                # remove uuid if present
                if "uuid" in data:
                    del data["uuid"]
                data["mtmpl_name"] = ""
                for mtmpl in mtmpl_list:
                    if mtmpl.get("mtmpl_uuid") == data.get("template_uuid"):
                        data["mtmpl_name"] = mtmpl.get("mtmpl_title", "")
                        if "template_uuid" in data:
                            del data["template_uuid"]
                        break
                for col_name, value in data.items():
                    if isinstance(value, list) and value:
                        data[col_name] = "\n".join(value)
                    elif not value:
                        data[col_name] = "-"
                        
            # --- C. 轉換為 Pandas 並存入記憶體 ---
            df = pd.DataFrame(processed_data)
            
            # ... (Rename logic same as before) ...
            # 重新命名欄位，讓 Excel 標頭更易讀
            df.rename(columns={
                'target_email': '受測人信箱',
                'mtmpl_name': '信件名稱', 
                'person_info': '受測人姓名',
                'plan_time': '預計寄送時間',
                'send_time': '實際寄送時間',
                'send_res': '寄送結果',
                'second_access_time': 'url連線時間',
                'second_access_src': 'url連線IP', 
                'second_access_dev': 'url連線資訊', 
                'second_qrcode_time': 'QR Code 掃描時間',
                'second_qrcode_src': 'QR Code 掃描IP',
                'second_qrcode_dev': 'QR Code 掃描資訊',
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

    class DownloadJessRequest(BaseModel):
        sendtask_uuid: str
        name: str

    @router.post("/download_sendlog_jess")
    async def api_download_sendlog_jess(request: DownloadJessRequest):
        """
        下載 JESS 格式報告，包含五個分頁：
        - log:      寄送紀錄明細 (橫向欄位)
        - info:     任務基本資訊 (直向鍵值)
        - template: 樣板資訊 (橫向欄位)
        - member:   (保留空白)
        - overflow: (保留空白)
        """
        try:
            # --- A. 獲取資料 ---
            task = await db_controller.get_one(SendTask, {"sendtask_uuid": request.sendtask_uuid})
            if not task:
                return StreamingResponse(
                    io.BytesIO(b"No sendtask found for this uuid."),
                    status_code=404,
                    media_type="text/plain"
                )

            detail_rows = await db_controller.get(SendLogDetail, filters={"sendtask_uuid": request.sendtask_uuid})
            details = [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in detail_rows]

            # 取得實際使用到的 template_uuid（去重）
            used_template_uuids = list({d["template_uuid"] for d in details if d.get("template_uuid")})
            mtmpl_rows = await db_controller.get(Mtmpl, filters={"mtmpl_uuid": used_template_uuids}) if used_template_uuids else []
            mtmpl_map = {getattr(r, "mtmpl_uuid"): r for r in mtmpl_rows}

            # SE2 輔助資料（失敗時 fallback 空 dict/list）
            tags_map: dict = {}
            try:
                tags_result = await get_se2_data.get_tags()
                if isinstance(tags_result, dict):
                    tags_map = tags_result
            except Exception:
                pass

            attached_map: dict = {}
            try:
                attached_list = await get_se2_data.get_attachedfile_list()
                if isinstance(attached_list, list):
                    for item in attached_list:
                        key = item.get("attachedfile_uuid")
                        name = item.get("attachedfile_display_name")
                        if key:
                            attached_map[str(key)] = name
            except Exception:
                pass

            # --- B.1 組裝 log 分頁資料 ---
            is_pre_test = bool(task.pre_test_enable)
            test_type = "pretest" if is_pre_test else "test"

            log_data: list[dict] = []
            for d in details:
                name, group, subgroup = _parse_person_info(d.get("person_info", ""))
                mtmpl = mtmpl_map.get(d.get("template_uuid", ""))
                subject = getattr(mtmpl, "mtmpl_title", "") if mtmpl else ""
                log_data.append({
                    "TestType":      test_type,
                    "Group":         group,
                    "Sub-group":     subgroup,
                    "Name":          name,
                    "EMail":         d.get("target_email", ""),
                    "Order":         d.get("order_no", ""),
                    "Subject":       subject,
                    "EstimatedTime": _fmt_ts(d.get("plan_time")),
                    "SendTime":      _fmt_ts(d.get("send_time")),
                    "SendRes":       d.get("send_res", ""),
                    "Method":        d.get("trigger_man", ""),
                    "Selection":     d.get("template_selection", ""),
                    "AccessTime":    _fmt_ts_list(d.get("access_time")) or "-",
                    "AccessSrc":     _join_list(d.get("access_src")) or "-",
                    "AccessDev":     _join_list(d.get("access_dev")) or "-",
                    "ClickLinkTime": _fmt_ts_list(d.get("click_time")) or "-",
                    "ClickLinkSrc":  _join_list(d.get("click_src")) or "-",
                    "ClickLinkDev":  _join_list(d.get("click_dev")) or "-",
                    "OpenFileTime":  _fmt_ts_list(d.get("file_time")) or "-",
                    "OpenFileSrc":   _join_list(d.get("file_src")) or "-",
                    "OpenFileDev":   _join_list(d.get("file_dev")) or "-",
                    "SubjectID":     d.get("template_uuid", ""),
                    "EMailID":       d.get("sendtask_uuid", ""),
                })

            # --- B.2 組裝 info 分頁資料 ---
            is_pre_test = bool(task.pre_test_enable)
            if is_pre_test:
                start_ts = task.pre_test_start_ut
                end_ts   = task.pre_test_end_ut
                sent_end_ts = getattr(task, "pre_send_end_ut", task.pre_test_end_ut)
            else:
                start_ts = task.test_start_ut
                end_ts   = task.test_end_ut
                sent_end_ts = task.send_end_ut

            # sent_date：呼叫 get_testcase 取得 mail_delivery_d
            sent_date_str = "[]"
            try:
                testcase_data = await get_se2_data.get_testcase(request.sendtask_uuid)
                if testcase_data and "mail_delivery_d" in testcase_data:
                    mail_delivery_d = testcase_data.get("mail_delivery_d", [])
                    if isinstance(mail_delivery_d, list):
                        sent_date_str = "[" + ", ".join(str(d) for d in mail_delivery_d) + "]"
            except Exception as e:
                logger.error(f"Error fetching mail_delivery_d for sent_date: {e}")

            info_data: dict = {
                "customer_name": "[customer_name]",
                "project_name":  "[project_name]",
                "doc_name":      "[doc_name]",
                "doc_id":        "[doc_id]",
                "version_id":    "V1.0",
                "start_date":    start_ts,
                "end_date":      end_ts,
                "sent_end_date": sent_end_ts,
                "sent_time":     "[]",
                "sent_date":     sent_date_str,
            }

            # --- B.3 組裝 template 分頁資料 ---
            template_data: list[dict] = []
            for i, mtmpl_uuid in enumerate(used_template_uuids):
                mtmpl = mtmpl_map.get(mtmpl_uuid)
                if not mtmpl:
                    continue

                # tag：mtmpl_tag 陣列 → 查中文名稱 → 逗號分隔
                raw_tags = getattr(mtmpl, "mtmpl_tag", None) or []
                tag_names = []
                for t in raw_tags:
                    # tags_map 的 key 是 tag uuid/id，value 是中文名稱
                    cn_name = tags_map.get(t, None) if isinstance(tags_map, dict) else None
                    tag_names.append(cn_name if cn_name else t)
                tag_str = ", ".join(tag_names)

                # sender
                mail_from = getattr(mtmpl, "mail_from", "") or ""
                mail_from_addr = getattr(mtmpl, "mail_from_address", "") or ""
                sender = f"{mail_from} <{mail_from_addr}>".strip()

                # attachment：mtmpl_mail_attached 陣列 → 查中文檔名 → 逗號分隔
                raw_attached = getattr(mtmpl, "mtmpl_mail_attached", None) or []
                att_names = [attached_map.get(str(a), str(a)) for a in raw_attached]
                attachment_str = ", ".join(att_names)

                template_data.append({
                    "tag":        tag_str,
                    "subject":    getattr(mtmpl, "mtmpl_title", "") or "",
                    "sender":     sender,
                    "attachment": attachment_str,
                    "alias":      _alias(i),
                    "subjectId":  mtmpl_uuid,
                })

            # --- C. 建立各分頁 DataFrame ---
            log_columns = [
                "TestType", "Group", "Sub-group", "Name", "EMail", "Order",
                "Subject", "EstimatedTime", "SendTime", "SendRes", "Method",
                "Selection", "AccessTime", "AccessSrc", "AccessDev",
                "ClickLinkTime", "ClickLinkSrc", "ClickLinkDev",
                "OpenFileTime", "OpenFileSrc", "OpenFileDev",
                "SubjectID", "EMailID"
            ]
            info_keys = [
                "customer_name", "project_name", "doc_name", "doc_id",
                "version_id", "start_date", "end_date",
                "sent_end_date", "sent_time", "sent_date"
            ]
            template_columns = [
                "tag", "subject", "sender", "attachment", "alias", "subjectId"
            ]
            member_columns = ["unit", "member"]
            overflow_columns = [
                "EmailID", "FieldName", "PartIndex", "Content"
            ]

            df_log = pd.DataFrame(log_data, columns=log_columns) if log_data else pd.DataFrame(columns=log_columns)
            df_info = pd.DataFrame([{"欄位": k, "值": info_data.get(k, "")} for k in info_keys])
            df_template = pd.DataFrame(template_data, columns=template_columns) if template_data else pd.DataFrame(columns=template_columns)

            # member / overflow 分頁：為定值固定不變
            member = [
                {'unit': 'OOO', 'member': '林OO'},
                {'unit': 'OOO', 'member': '王OO'},
            ]
            df_member = pd.DataFrame(member, columns=member_columns)
            df_overflow = pd.DataFrame(columns=overflow_columns)

            # --- D. 寫入 Excel (多分頁) ---
            output_buffer = io.BytesIO()
            with pd.ExcelWriter(output_buffer, engine="openpyxl") as writer:
                df_log.to_excel(writer, sheet_name="log", index=False)
                df_info.to_excel(writer, sheet_name="info", header=False, index=False)
                df_template.to_excel(writer, sheet_name="template", index=False)
                df_member.to_excel(writer, sheet_name="member", index=False)
                df_overflow.to_excel(writer, sheet_name="overflow", index=False)
            output_buffer.seek(0)

            # --- E. 回傳檔案串流 ---
            filename = urllib.parse.quote(f"{request.name}.xlsx")
            headers = {
                "Content-Disposition": (
                    f'attachment; filename="{request.sendtask_uuid}_dashboard.xlsx"; '
                    f"filename*=UTF-8''{filename}"
                )
            }
            return StreamingResponse(
                output_buffer,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers=headers
            )

        except Exception as e:
            error_message = f"Error generating JESS file: {e}"
            print(f"下載 JESS Excel 失敗: {error_message}", file=sys.stderr)
            return StreamingResponse(
                io.BytesIO(error_message.encode("utf-8")),
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

    class ClearTriggerRequest(BaseModel):
        uuid: str
        sendtask_uuid: str

    @router.post("/clear_trigger_data")
    async def clear_trigger_data(request: ClearTriggerRequest):
        try:
            await db_user.clear_trigger_data(request.uuid, request.sendtask_uuid)
            return {"status": "success", "message": "已清除觸發紀錄"}
        except Exception as e:
            return {"status": "error", "message": f"清除失敗: {str(e)}"}

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
                rows = await db_controller.get(SendLogDetail, filters={"uuid": request.selected_uuids})
                all_data = [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in rows]
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
                mtmpl_name = []
                mtmpl_name = []
                mtmpl = await db_controller.get_one(Mtmpl, {"mtmpl_uuid": data.get("template_uuid", "")})
                if mtmpl:
                    mtmpl_name.append(mtmpl)
                
                data["mtmpl_name"] = mtmpl_name[0].mtmpl_title if mtmpl_name else ""

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
            rows = await db_controller.get(Mtmpl)
            mtmpl_data = [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in rows]
                
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
            local_mtmpls = await db_controller.get(Mtmpl)
            local_mtmpl_list = [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in local_mtmpls]

            # 3. 準備比對用的集合 (使用 mtmpl_uuid 作為唯一鍵)
            se2_uuids = {item['mtmpl_uuid']: item for item in se2_mtmpl_list}
            local_uuids = {item['mtmpl_uuid']: item for item in local_mtmpl_list}

            # 4. 找出差異
            added_uuids = set(se2_uuids.keys()) - set(local_uuids.keys())
            removed_uuids = set(local_uuids.keys()) - set(se2_uuids.keys())

            added_list = [se2_uuids[uuid] for uuid in added_uuids]
            removed_list = [local_uuids[uuid] for uuid in removed_uuids]

            # 5. 更新資料庫
            if added_list:
                # Prepare data
                valid_keys = {"mtmpl_uuid", "mtmpl_title", "create_time"}
                clean_added_list = []
                for item in added_list:
                    clean_item = {k: v for k, v in item.items() if k in valid_keys}
                    clean_added_list.append(clean_item)
                
                await db_controller.batch_create(Mtmpl, clean_added_list)
                logger.info(f"Added {len(added_list)} new mail templates.")

            if removed_list:
                for item in removed_list:
                    await db_controller.delete(Mtmpl, {"mtmpl_uuid": item["mtmpl_uuid"]})
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
            customers = await db_controller.get(CustomerAcct, {"acct_uuid": acct_uuid})
            data = [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in customers]
            return {"status": "success", "data": data}
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

    class UpdateCustomerTaskCreationRequest(BaseModel):
        customer_name: str = ""
        enabled: bool = False
        org_uuid: str = ""

    @router.post(
        "/update_customer_task_creation",
        tags=["data"]
        )
    async def update_customer_task_creation(request: UpdateCustomerTaskCreationRequest):
        """
        更新客戶的「建立任務功能」開關狀態與指定組織

        1. POST /update_customer_task_creation
        2. Body: {"customer_name": ..., "enabled": true/false, "org_uuid": ...}
        """
        if not request.customer_name:
            return {"status": "error", "message": "沒有收到客戶名稱"}

        try:
            result = await db_user.update_customer_task_creation(
                request.customer_name, 
                request.enabled, 
                request.org_uuid
            )
            return result
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @router.get(
        "/get_org_name_list",
        tags=["data"]
        )
    async def get_org_name_list():
        """
        取得組織名稱清單 (來自 SE2)
        1. GET /get_org_name_list
        """
        try:
            result = await get_se2_data.get_org_name_list()
            if result:
                return result
            return {"status": "error", "message": "無法取得組織清單"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @router.get(
        "/get_mtmpl_name_list",
        tags=["data"]
        )
    async def get_mtmpl_name_list(unit_uuid: str):
        """
        取得特定組織的郵件樣本名稱清單 (來自 SE2)
        1. GET /get_mtmpl_name_list?unit_uuid=...
        """
        if not unit_uuid:
            return {"status": "error", "message": "缺少 unit_uuid 參數"}
        
        try:
            result = await get_se2_data.get_mtmpl_name_list(unit_uuid)
            if result:
                return result
            return {"status": "error", "message": "無法取得郵件樣本清單"}
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
            # 取得要刪除的客戶，擷取其 customer_uuid
            customers = await db_controller.get(CustomerAcct, {"customer_name": del_customer_names})
            if customers:
                customer_uuids = [c.customer_uuid for c in customers if c.customer_uuid]
                if customer_uuids:
                    # 一併刪除 customer_tasks 裡面的資料
                    await db_controller.delete(CustomerTask, {"customer_uuid": customer_uuids})

            # 刪除客戶帳號
            await db_controller.delete(CustomerAcct, {"customer_name": del_customer_names})
            return {"status": "success", "message": del_customer_names}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    class DeleteSendtaskRequest(BaseModel):
        uuid: str

    @router.post(
        "/delete_sendtask",
        tags=["data"]
        )
    async def delete_sendtask(request: DeleteSendtaskRequest, current_user: dict = Depends(get_current_user)):
        """
        刪除任務及其相關紀錄
        """
        uuid = request.uuid
        try:
            # 刪除 sendtasks 資料
            await db_controller.delete(SendTask, {"sendtask_uuid": uuid})
            # 刪除 sendlog_stats 資料
            await db_controller.delete(SendLogStats, {"sendtask_uuid": uuid})
            # 刪除 send_log_details 資料
            await db_controller.delete(SendLogDetail, {"sendtask_uuid": uuid})
            
            return {"status": "success", "message": "任務已刪除"}
        except Exception as e:
            logger.error(f"Failed to delete sendtask {uuid}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

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
            # 使用 db_user 統一的 update_password 方法
            result = await db_user.update_password(
                user_type="customer",
                identifier=customer_name,
                new_password=new_password,
                old_password=old_password
            )
            if result["status"] == "success":
                return {"status": "success", "message": "密碼更新成功"}
            else:
                 return {"status": "error", "message": result["message"]}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @router.get(
        "/customer/get_my_sendtasks",
        tags=["data"]
        )
    async def get_my_sendtasks(current_user: dict = Depends(get_current_user)):
        """取得當前客戶的 sendtasks 清單（用於更新 Cookie）"""
        if current_user.get("user_type") != "customer":
            return {"status": "error", "message": "非客戶帳號"}

        try:
            customer = await db_controller.get_one(
                CustomerAcct,
                {"customer_name": current_user.get("username")}
            )
            if not customer:
                return {"status": "error", "message": "找不到客戶帳號"}

            return {"status": "success", "sendtasks": customer.sendtasks or []}
        except Exception as e:
            logger.error(f"Error in get_my_sendtasks: {str(e)}")
            return {"status": "error", "message": str(e)}

    return router





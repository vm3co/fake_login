from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel
from typing import List, Optional
from dateutil import parser
import pandas as pd
import io

from backend.services.create_se_tasks import se_task_service
from backend.services.getSe2data import get_se2_data
from backend.services.log_manager import Logger
from backend.services.db_user import DBUser
from backend.repository.db_controller import db_controller
from backend.repository.models import CustomerTask, CustomerAcct, SendTask

logger = Logger().get_logger()
router = APIRouter()

# --- 資料模型 (Pydantic Models) ---

class CreateTaskRequest(BaseModel):
    task_name: str
    task_type: str  # 'pre' or 'official'
    start_date: str
    end_date: str
    stop_date: Optional[str] = None
    participant_data: str
    template_uuids: List[str]
    unit_uuid: str
    customer_uuid: str  # 客戶 UUID，用於追蹤

class SendtaskUuidRequest(BaseModel):
    """通用的 sendtask_uuid 請求模型（啟動/停止/暫停/刪除共用）"""
    sendtask_uuid: str


# --- 工具函式 ---

def parse_date_to_timestamp(date_str: str) -> int:
    try:
        dt = parser.parse(date_str)
        return int(dt.timestamp())
    except Exception as e:
        logger.error(f"日期解析錯誤: {date_str}, {e}")
        return 0

def process_participant_data(csv_text: str) -> tuple[int, str]:
    """
    處理參與人員 CSV 文字：
    1. 計算參與人數（不含標題列）
    2. 將 CSV 轉為 SE2 所需的格式字串
    """
    try:
        df = pd.read_csv(io.StringIO(csv_text))
        participant_count = len(df)
        if participant_count == 0:
            raise ValueError("CSV 資料中沒有任何資料列")

        df_filled = df.fillna('')
        df_str = df_filled.astype(str)
        formatted_rows = df_str.apply(lambda row: ','.join(row), axis=1)
        content_string = '\\n'.join(formatted_rows)
        test_participant = f'"{content_string}"'

        logger.info(f"解析出 {participant_count} 位參與者")
        return participant_count, test_participant
    except Exception as e:
        logger.error(f"解析參與人員 CSV 時發生錯誤: {e}")
        raise


async def _add_sendtask_to_customer(customer_uuid: str, sendtask_uuid: str):
    """
    將指定 sendtask_uuid 加入客戶的 sendtasks JSONB 欄位。
    若已存在則跳過。
    """
    customer = await db_controller.get_one(CustomerAcct, {"customer_uuid": customer_uuid})
    if not customer:
        logger.error(f"Customer {customer_uuid} not found, cannot add sendtask.")
        return

    current_tasks = customer.sendtasks or []
    # 檢查是否已存在
    existing_uuids = {t.get("uuid") for t in current_tasks if isinstance(t, dict)}
    if sendtask_uuid in existing_uuids:
        logger.info(f"sendtask {sendtask_uuid} already in customer {customer_uuid}'s sendtasks.")
        return

    # 加入新任務，預設開啟所有可見性
    new_task = {
        "uuid": sendtask_uuid,
        "send": True,
        "failed": True,
        "notyet": True,
        "notTriggered": True,
        "triggered": True,
    }
    updated_tasks = current_tasks + [new_task]
    await db_controller.update(
        CustomerAcct,
        {"customer_uuid": customer_uuid},
        {"sendtasks": updated_tasks}
    )
    logger.info(f"Added sendtask {sendtask_uuid} to customer {customer_uuid}'s sendtasks.")


async def _remove_sendtask_from_customer(customer_uuid: str, sendtask_uuid: str):
    """
    從客戶的 sendtasks JSONB 欄位移除指定的 sendtask_uuid。
    """
    customer = await db_controller.get_one(CustomerAcct, {"customer_uuid": customer_uuid})
    if not customer:
        logger.error(f"Customer {customer_uuid} not found, cannot remove sendtask.")
        return

    current_tasks = customer.sendtasks or []
    updated_tasks = [t for t in current_tasks if not (isinstance(t, dict) and t.get("uuid") == sendtask_uuid)]

    if len(updated_tasks) == len(current_tasks):
        logger.info(f"sendtask {sendtask_uuid} not found in customer {customer_uuid}'s sendtasks, skip.")
        return

    await db_controller.update(
        CustomerAcct,
        {"customer_uuid": customer_uuid},
        {"sendtasks": updated_tasks}
    )
    logger.info(f"Removed sendtask {sendtask_uuid} from customer {customer_uuid}'s sendtasks.")


# --- 端點 ---

@router.post("/task/create_testcase")
async def create_testcase(request: CreateTaskRequest):
    """建立專案"""
    logger.info(f"收到建立專案請求: {request.task_name}")
    
    pre_test_enable = (request.task_type == 'pre')
    
    test_start = parse_date_to_timestamp(request.start_date)
    test_end = parse_date_to_timestamp(request.end_date)
    send_end = parse_date_to_timestamp(request.stop_date) if request.stop_date else test_end
    
    # 將 UUID 列表轉為 SE2 格式 [{"uuid": "xxx"}, ...]
    mail_template = [{"uuid": uuid} for uuid in request.template_uuids]

    # 處理參與人員 CSV
    try:
        participant_count, test_participant = process_participant_data(request.participant_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"無法解析參與人員資料: {e}")
    
    try:
        uuid = await se_task_service.create_testcase(
            id=request.task_name,
            unit=request.unit_uuid,
            pre_test_enable=pre_test_enable,
            mail_template=mail_template,
            test_start=test_start,
            test_end=test_end,
            send_end=send_end,
            participant_count=participant_count,
            participant_data=test_participant
        )
        
        if uuid:
            # 寫入 DB 追蹤記錄
            await db_controller.create(CustomerTask, {
                "customer_uuid": request.customer_uuid,
                "sendtask_uuid": uuid,
                "task_name": request.task_name,
                "task_type": request.task_type,
                "status": "created"
            })

            return {
                "status": "success",
                "message": "專案建立成功",
                "sendtask_uuid": uuid,
                "data": {
                    "sendtask_uuid": uuid,
                    "id": request.task_name,
                    "task_type": request.task_type,
                    "start_date": request.start_date,
                    "end_date": request.end_date,
                    "stop_date": request.stop_date,
                    "mail_template": request.template_uuids,
                    "participant_count": participant_count,
                }
            }
        else:
            raise HTTPException(status_code=500, detail="專案建立失敗")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"呼叫 SeTask 時發生錯誤: {e}")
        raise HTTPException(status_code=500, detail=f"後端處理時發生錯誤: {e}")


@router.post("/task/create_sendtask")
async def create_sendtask(request: SendtaskUuidRequest):
    """啟動任務（request.sendtask_uuid 其實是 testcase_uuid）"""
    testcase_uuid = request.sendtask_uuid
    logger.info(f"收到啟動任務請求 (testcase_uuid): {testcase_uuid}")

    try:
        se2_response = await se_task_service.create_sendtask(
            testcase_uuid=testcase_uuid,
            to_scheduler=False
        )

        if se2_response:
            # 從 SE2 回傳中提取真正的 sendtask_uuid
            real_sendtask_uuid = None
            if isinstance(se2_response, dict):
                real_sendtask_uuid = se2_response.get("data", {}).get("sendtask_uuid") if isinstance(se2_response.get("data"), dict) else None
                if not real_sendtask_uuid:
                    real_sendtask_uuid = se2_response.get("sendtask_uuid")
            logger.info(f"SE2 回傳的 sendtask_uuid: {real_sendtask_uuid}")

            # 用真正的 sendtask_uuid 更新 DB（如果有取得到的話）
            update_data = {"status": "active"}
            if real_sendtask_uuid and real_sendtask_uuid != testcase_uuid:
                update_data["sendtask_uuid"] = real_sendtask_uuid

            await db_controller.update(
                CustomerTask,
                {"sendtask_uuid": testcase_uuid},
                update_data
            )

            # 使用真正的 sendtask_uuid 加入客戶可見清單
            final_uuid = real_sendtask_uuid or testcase_uuid
            task_record = await db_controller.get_one(CustomerTask, {"sendtask_uuid": final_uuid})
            if task_record:
                await _add_sendtask_to_customer(task_record.customer_uuid, final_uuid)

            # 從 SE2 同步任務資料到本地 SendTask 表
            try:
                _db_user = DBUser()
                record = await _db_user._build_sendtask_record_from_detail(final_uuid)
                if record:
                    await db_controller.upsert(
                        SendTask,
                        [record],
                        index_elements=['sendtask_uuid']
                    )
                    # 同步 sendlog_stats
                    await _db_user.refresh_sendlog_stats([final_uuid], skip_sendtask_sync=True)
                    logger.info(f"已從 SE2 同步任務 {final_uuid} 的資料到本地 DB")
                else:
                    logger.warning(f"無法從 SE2 取得任務 {final_uuid} 的詳細資料")
            except Exception as sync_err:
                logger.warning(f"同步任務資料到本地 DB 時發生非致命錯誤: {sync_err}")

            return {
                "status": "success",
                "message": "任務啟動成功",
                "sendtask_uuid": final_uuid
            }
        else:
            raise HTTPException(status_code=500, detail="程式端啟動任務失敗，詳情請查看伺服器日誌。")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"啟動任務時發生錯誤: {e}")
        raise HTTPException(status_code=500, detail=f"後端處理時發生錯誤: {e}")

@router.post("/task/pause_sendtask")
async def pause_sendtask(request: SendtaskUuidRequest):
    """暫停任務"""
    logger.info(f"收到暫停任務請求: {request.sendtask_uuid}")

    try:
        state = await se_task_service.pause_sendtask(
            sendtask_uuid=request.sendtask_uuid
        )

        if state:
            # 更新 DB 狀態為 paused
            await db_controller.update(
                CustomerTask,
                {"sendtask_uuid": request.sendtask_uuid},
                {"status": "paused"}
            )
            return {
                "status": "success",
                "message": "任務已暫停",
                "sendtask_uuid": request.sendtask_uuid
            }
        else:
            raise HTTPException(status_code=500, detail="程式端暫停任務失敗，詳情請查看伺服器日誌。")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"暫停任務時發生錯誤: {e}")
        raise HTTPException(status_code=500, detail=f"後端處理時發生錯誤: {e}")

@router.post("/task/resume_sendtask")
async def resume_sendtask(request: SendtaskUuidRequest):
    """恢復（繼續執行）任務"""
    logger.info(f"收到恢復任務請求: {request.sendtask_uuid}")

    try:
        result = await get_se2_data.resume_sendtask(request.sendtask_uuid)

        if result and result.get("sub_code") == 20000:
            # 更新 DB 狀態為 active
            await db_controller.update(
                CustomerTask,
                {"sendtask_uuid": request.sendtask_uuid},
                {"status": "active"}
            )
            return {
                "status": "success",
                "message": "任務已恢復執行",
                "sendtask_uuid": request.sendtask_uuid
            }
        else:
            raise HTTPException(status_code=500, detail="程式端恢復任務失敗，詳情請查看伺服器日誌。")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"恢復任務時發生錯誤: {e}")
        raise HTTPException(status_code=500, detail=f"後端處理時發生錯誤: {e}")

@router.post("/task/delete_sendtask")
async def delete_sendtask(request: SendtaskUuidRequest):
    """停止（刪除）任務 — 會從 customer_accts.sendtasks 移除該 uuid"""
    logger.info(f"收到刪除任務請求: {request.sendtask_uuid}")

    try:
        state = await se_task_service.delete_sendtask(
            sendtasks_uuid=request.sendtask_uuid
        )

        if state:
            # 更新 DB 狀態為 stopped
            await db_controller.update(
                CustomerTask,
                {"sendtask_uuid": request.sendtask_uuid},
                {"status": "stopped"}
            )

            # 從客戶的可見清單中移除此任務
            task_record = await db_controller.get_one(CustomerTask, {"sendtask_uuid": request.sendtask_uuid})
            if task_record:
                await _remove_sendtask_from_customer(task_record.customer_uuid, request.sendtask_uuid)

            return {
                "status": "success",
                "message": "任務刪除成功",
                "sendtask_uuid": request.sendtask_uuid
            }
        else:
            raise HTTPException(status_code=500, detail="程式端刪除任務失敗，詳情請查看伺服器日誌。")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"刪除任務時發生錯誤: {e}")
        raise HTTPException(status_code=500, detail=f"後端處理時發生錯誤: {e}")

@router.post("/task/delete_testcase")
async def delete_testcase(request: SendtaskUuidRequest):
    """刪除專案"""
    logger.info(f"收到刪除專案請求: {request.sendtask_uuid}")

    try:
        state = await se_task_service.delete_testcase(
            testcase_uuid=request.sendtask_uuid
        )

        if state:
            # 更新 DB 狀態為 deleted
            await db_controller.update(
                CustomerTask,
                {"sendtask_uuid": request.sendtask_uuid},
                {"status": "deleted"}
            )
            return {
                "status": "success",
                "message": "專案刪除成功",
                "sendtask_uuid": request.sendtask_uuid
            }
        else:
            raise HTTPException(status_code=500, detail="程式端刪除專案失敗，詳情請查看伺服器日誌。")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"刪除專案時發生錯誤: {e}")
        raise HTTPException(status_code=500, detail=f"後端處理時發生錯誤: {e}")


# --- 查詢端點 ---

@router.get("/task/get_customer_tasks")
async def get_customer_tasks(customer_uuid: str = Query(..., description="客戶 UUID")):
    """取得指定客戶的所有專案/任務記錄"""
    try:
        tasks = await db_controller.get(
            CustomerTask,
            {"customer_uuid": customer_uuid},
            order_by=CustomerTask.created_at.desc()
        )
        return {
            "status": "success",
            "data": [
                {
                    "id": t.id,
                    "customer_uuid": t.customer_uuid,
                    "sendtask_uuid": t.sendtask_uuid,
                    "task_name": t.task_name,
                    "task_type": t.task_type,
                    "status": t.status,
                    "created_at": t.created_at.isoformat() + "Z" if t.created_at else None,
                }
                for t in tasks
            ]
        }
    except Exception as e:
        logger.error(f"查詢客戶任務失敗: {e}")
        raise HTTPException(status_code=500, detail=f"查詢失敗: {e}")


class SyncCustomerTasksRequest(BaseModel):
    customer_uuid: str

@router.post("/task/sync_customer_tasks")
async def sync_customer_tasks(request: SyncCustomerTasksRequest):
    """
    同步客戶自建任務的狀態。
    從 SE2 取得每個任務的實際狀態，更新 customer_tasks 表。
    """
    logger.info(f"同步客戶任務狀態: {request.customer_uuid}")

    try:
        tasks = await db_controller.get(
            CustomerTask,
            {"customer_uuid": request.customer_uuid}
        )

        updated = []
        for task in tasks:
            # 已刪除或已停止的不需同步
            if task.status in ('deleted', 'stopped'):
                continue

            se2_data = await get_se2_data.get_sendtask(task.sendtask_uuid)

            if se2_data is None:
                continue

            if se2_data.get("error", {}).get("code") == 404:
                if task.status == 'created':
                    new_status = "created"
                else:
                    new_status = "deleted"
            else:
                metadata = se2_data.get("metadata", {})
                is_pause = metadata.get("pause", False)

                if task.status == 'created':
                    # created 狀態：檢查是否已在主系統啟動
                    # 如果 metadata 存在且有 summary，表示已有 sendtask
                    summary = metadata.get("summary", {})
                    if summary.get("person_count", 0) > 0:
                        new_status = "active"
                    else:
                        new_status = task.status
                elif task.status == 'active':
                    if is_pause:
                        new_status = "paused"
                    else:
                        new_status = "active"
                elif task.status == 'paused':
                    if not is_pause:
                        new_status = "active"
                    else:
                        new_status = "paused"
                else:
                    new_status = task.status

            if new_status != task.status:
                await db_controller.update(
                    CustomerTask,
                    {"sendtask_uuid": task.sendtask_uuid},
                    {"status": new_status}
                )
                updated.append({
                    "sendtask_uuid": task.sendtask_uuid,
                    "old_status": task.status,
                    "new_status": new_status
                })

        return {"status": "success", "updated": updated}
    except Exception as e:
        logger.error(f"同步客戶任務狀態失敗: {e}")
        raise HTTPException(status_code=500, detail=f"同步失敗: {e}")


@router.get("/task/get_testcase_detail")
async def get_testcase_detail(testcase_uuid: str = Query(..., description="專案/testcase UUID")):
    """取得專案的詳細資料（從 SE2 取得，供唯讀檢視用）"""
    try:
        data = await get_se2_data.get_testcase(testcase_uuid)
        if not data:
            raise HTTPException(status_code=404, detail="找不到專案資料")

        # SE2 get_testcase 回傳的 data 本身就是 testcase 物件
        tc = data if isinstance(data, dict) else {}
        pre_test_enable = bool(tc.get("pre_test_enable"))

        if pre_test_enable:
            test_start_ut = tc.get("pre_test_start_ut")
            test_end_ut   = tc.get("pre_test_end_ut")
            send_end_ut   = tc.get("pre_send_end_ut")
            person_count  = tc.get("pre_test_person_count")
        else:
            test_start_ut = tc.get("test_start_ut")
            test_end_ut   = tc.get("test_end_ut")
            send_end_ut   = tc.get("send_end_ut")
            person_count  = tc.get("test_person_count")

        # mail_template 是純 UUID 字串陣列
        template_uuids = [t for t in (tc.get("mail_template") or []) if isinstance(t, str)]

        # testcase_unit 是組織 UUID
        unit_uuid = tc.get("testcase_unit") or ""

        template_names = []
        if unit_uuid and template_uuids:
            try:
                tmpl_list_resp = await get_se2_data.get_mtmpl_name_list(unit_uuid)
                tmpl_list = (tmpl_list_resp or {}).get("data") if isinstance(tmpl_list_resp, dict) else None
                if isinstance(tmpl_list, list):
                    name_map = {t.get("mtmpl_uuid"): t.get("mtmpl_name") for t in tmpl_list if isinstance(t, dict)}
                    template_names = [
                        {"mtmpl_uuid": u, "mtmpl_name": name_map.get(u, u)}
                        for u in template_uuids
                    ]
            except Exception as e:
                logger.warning(f"取得郵件樣本名稱失敗: {e}")

        if not template_names:
            template_names = [{"mtmpl_uuid": u, "mtmpl_name": u} for u in template_uuids]

        participants = await get_se2_data.get_test_participant(testcase_uuid, pre_test_enable)

        return {
            "status": "success",
            "data": {
                "task_name": tc.get("testcase_id") or "",
                "task_type": "pre" if pre_test_enable else "official",
                "test_start_ut": test_start_ut,
                "test_end_ut":   test_end_ut,
                "send_end_ut":   send_end_ut,
                "person_count":  person_count,
                "template_uuids": template_uuids,
                "templates":     template_names,
                "unit_uuid":     unit_uuid,
                "participants":  participants or [],
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"取得專案細節失敗: {e}")
        raise HTTPException(status_code=500, detail=f"取得專案細節失敗: {e}")

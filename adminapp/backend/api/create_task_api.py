from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from dateutil import parser
import pandas as pd
import io

from backend.services.create_se_tasks import se_task_service
from backend.services.log_manager import Logger

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

class SendtaskRequest(BaseModel):
    """啟動任務的請求模型"""
    testcase_uuid: str

class DeleteSendtaskRequest(BaseModel):
    """刪除(停止)任務的請求模型"""
    sendtask_uuid: str

class DeleteTestcaseRequest(BaseModel):
    """刪除專案的請求模型"""
    testcase_uuid: str


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

# --- 端點 ---

@router.post("/task/create_testcase")
async def create_testcase(request: CreateTaskRequest):
    """建立專案與任務"""
    logger.info(f"Received create task request: {request.task_name}")
    
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
            return {
                "status": "success",
                "message": "專案建立成功",
                "testcase_uuid": uuid,
                "data": {
                    "testcase_uuid": uuid,
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
async def create_sendtask(request: SendtaskRequest):
    """啟動任務"""
    logger.info(f"收到啟動任務請求: {request.testcase_uuid}")

    try:
        state = await se_task_service.create_sendtask(
            testcase_uuid=request.testcase_uuid,
            to_scheduler=False
        )

        if state:
            return {
                "status": "success",
                "message": "任務啟動成功",
                "sendtask_uuid": request.testcase_uuid
            }
        else:
            raise HTTPException(status_code=500, detail="程式端啟動任務失敗，詳情請查看伺服器日誌。")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"啟動任務時發生錯誤: {e}")
        raise HTTPException(status_code=500, detail=f"後端處理時發生錯誤: {e}")

@router.post("/task/delete_sendtask")
async def delete_sendtask(request: DeleteSendtaskRequest):
    """刪除（停止）任務"""
    logger.info(f"收到刪除任務請求: {request.sendtask_uuid}")

    try:
        state = await se_task_service.delete_sendtask(
            sendtasks_uuid=request.sendtask_uuid
        )

        if state:
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
async def delete_testcase(request: DeleteTestcaseRequest):
    """刪除專案"""
    logger.info(f"收到刪除專案請求: {request.testcase_uuid}")

    try:
        state = await se_task_service.delete_testcase(
            testcase_uuid=request.testcase_uuid
        )

        if state:
            return {
                "status": "success",
                "message": "專案刪除成功",
                "testcase_uuid": request.testcase_uuid
            }
        else:
            raise HTTPException(status_code=500, detail="程式端刪除專案失敗，詳情請查看伺服器日誌。")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"刪除專案時發生錯誤: {e}")
        raise HTTPException(status_code=500, detail=f"後端處理時發生錯誤: {e}")

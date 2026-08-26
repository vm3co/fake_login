from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from backend.services.job_manager import JobManager
from backend.api.user_api import get_current_user
from backend.services.db_user import DBUser
from backend.repository.db_controller import db_controller
from backend.repository.models import SendTask, Mtmpl, Notification, SendLogStats
from sqlalchemy import select, update, delete
from backend.api.data_api import filter_tasks_by_scope, get_sendtask_scope
from backend.services.log_manager import Logger

logger = Logger().get_logger()
router = APIRouter(
    prefix="/jobs",
    tags=["jobs"]
)

job_manager = JobManager()
# db = ApplianceDB() # Removed
db_user = DBUser()

class JobRequest(BaseModel):
    job_type: str
    params: Dict[str, Any] = {}

@router.get("/current")
async def get_current_job(current_user: dict = Depends(get_current_user)):
    username = current_user.get("username")
    job = job_manager.get_current_job(username)
    if job:
        return {
            "job_id": job['job_id'],
            "type": job['type'],
            "status": job['status'],
            "start_time": job['start_time'],
            "message": job.get('message'),
            "result": job.get('result'),
            "error": job.get('error')
        }
    return None

@router.post("/cancel")
async def cancel_job(current_user: dict = Depends(get_current_user)):
    username = current_user.get("username")
    success = await job_manager.cancel_job(username)
    return {"status": "success", "cancelled": success}

@router.post("/start")
async def start_job(request: JobRequest, current_user: dict = Depends(get_current_user)):
    username = current_user.get("username")
    job_type = request.job_type
    params = request.params
    
    try:
        if job_type == "refresh_today_create_task":
            orgs = get_sendtask_scope(current_user)
            # Logic from refresh_today_create_task
            async def task_func():
                today_create_task_list = await db_user.refresh_today_create_task()
                today_create_task_list = filter_tasks_by_scope(today_create_task_list, orgs)
                
                if not today_create_task_list:
                    return {"message": "無今日建立任務"}

                refresh_list = [task["sendtask_uuid"] for task in today_create_task_list]
                
                # Batch upsert sendtasks
                await db_controller.upsert(
                    model=SendTask,
                    data_list=today_create_task_list,
                    index_elements=['sendtask_uuid']
                )

                # Also refresh stats
                await db_user.refresh_sendlog_stats(refresh_list)
                
                # Add notification
                details_msg = "更新任務:\n" + "\n".join([t.get("sendtask_id", "Unknown") for t in today_create_task_list])
                
                await db_controller.create(Notification, {
                    "username": username,
                    "title": "檢查今日建立任務完成",
                    "subtitle": f"已更新 {len(refresh_list)} 筆任務",
                    "heading": "系統通知",
                    "path": "send_list",
                    "icon_name": "check_circle",
                    "icon_color": "success",
                    "details": details_msg
                })

                return {"updated_count": len(refresh_list)}

            await job_manager.start_job(username, "檢查今日建立任務", task_func)

        elif job_type == "update_mtmpl":
            async def task_func():
                # 1. 從 SE2 全量 upsert（含所有 model 欄位）
                result = await db_user.refresh_mtmpl()
                upserted = result.get("upserted", 0)
                if upserted == 0:
                    raise Exception("從 SE2 獲取郵件樣板失敗")

                # 2. 找出本地已不在 SE2 的樣板並刪除
                se2_mtmpl_list = await db_user.get_se2_mtmpl()
                se2_uuids = {item["mtmpl_uuid"] for item in se2_mtmpl_list}

                local_rows = await db_controller.get(Mtmpl)
                removed_count = 0
                for row in local_rows:
                    if row.mtmpl_uuid not in se2_uuids:
                        await db_controller.delete(Mtmpl, {"mtmpl_uuid": row.mtmpl_uuid})
                        removed_count += 1
                        logger.info(f"Removed mtmpl {row.mtmpl_uuid}")

                details_msg = f"更新/新增: {upserted} 筆\n刪除: {removed_count} 筆"

                await db_controller.create(Notification, {
                    "username": username,
                    "title": "更新郵件樣板完成",
                    "subtitle": "同步完成",
                    "heading": "系統通知",
                    "path": "send_list",
                    "icon_name": "list_alt",
                    "icon_color": "info",
                    "details": details_msg
                })

                return {"upserted": upserted, "removed": removed_count}

            await job_manager.start_job(username, "更新郵件樣板列表", task_func)

        elif job_type == "check_sendtasks":
            orgs = get_sendtask_scope(current_user)
            # Logic from check_sendtasks
            async def task_func():
                result = await db_user.sync_sendtasks(orgs=orgs)

                # 只對新增的 uuid 刷 sendlog_stats（原本邏輯）；跳過重複的 SendTask sync
                added_uuids = [t["sendtask_uuid"] for t in result["added"]]
                if added_uuids:
                    await db_user.refresh_sendlog_stats(
                        added_uuids,
                        ignore_archived=True,
                        skip_sendtask_sync=True,
                    )

                added_cnt = len(result["added"])
                changed_cnt = len(result["changed"])
                details_msg = ""
                if result["added"]:
                    details_msg += "● 新增任務:\n" + "\n".join(t.get("sendtask_id", "Unknown") for t in result["added"]) + "\n"
                if result["changed"]:
                    details_msg += "● 內容更新任務:\n" + "\n".join(t.get("sendtask_id", "Unknown") for t in result["changed"]) + "\n"

                await db_controller.create(Notification, {
                    "username": username,
                    "title": "任務列表更新完成",
                    "subtitle": f"新增 {added_cnt}，更新 {changed_cnt}，刪除 {result['deleted']}，封存 {result['archived']}",
                    "heading": "系統通知",
                    "path": "send_list",
                    "icon_name": "sync",
                    "icon_color": "info",
                    "details": details_msg,
                })
                return result

            await job_manager.start_job(username, "更新任務列表", task_func)

        elif job_type == "refresh_sendlog_stats":
            orgs = get_sendtask_scope(current_user)
            # Logic from refresh_sendlog_stats
            async def task_func():
                uuids = params.get("uuids", [])
                ignore_archived = params.get("ignore_archived", False)
                if not uuids:
                    return {"message": "未指定任務 UUID"}

                if orgs is not None:
                    tasks = await db_controller.get(SendTask, filters={"sendtask_uuid": uuids})
                    uuids = [task.sendtask_uuid for task in filter_tasks_by_scope(tasks, orgs)]
                    if not uuids:
                        raise HTTPException(status_code=403, detail="無權存取指定任務")
                
                # Chunking is handled by frontend in original code, but here we can handle it or just process all.
                # Since it's async background job, we can process all (maybe with some sleep to yield if needed).
                # db_user.refresh_sendlog_stats handles list of uuids.
                
                result = await db_user.refresh_sendlog_stats(uuids, ignore_archived=ignore_archived)
                
                updated_count = len(result) # Rough estimate or use logic
                
                updated_uuids = list(result.keys())
                details_msg = "更新統計資料:\n" + "\n".join(updated_uuids)

                await db_controller.create(Notification, {
                    "username": username,
                    "title": "任務更新完成",
                    "subtitle": f"已更新 {updated_count} 筆任務",
                    "heading": "系統通知",
                    "path": "send_list",
                    "icon_name": "update",
                    "icon_color": "primary",
                    "details": details_msg
                })
                return {"stats": result}

            await job_manager.start_job(username, "更新任務統計", task_func)
            
        else:
            raise HTTPException(status_code=400, detail=f"Unknown job type: {job_type}")

        return {"status": "success", "message": "任務已開始"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start job {job_type}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

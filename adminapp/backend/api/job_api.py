from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from backend.services.job_manager import JobManager
from backend.api.user_api import get_current_user
from backend.services.db_user import DBUser
from backend.repository.db_controller import db_controller
from backend.repository.models import SendTask, Mtmpl, Notification, SendLogStats
from sqlalchemy import select, update, delete
from backend.api.data_api import has_common_orgs
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
            # Logic from refresh_today_create_task
            async def task_func():
                orgs = params.get("orgs", [])
                today_create_task_list = await db_user.refresh_today_create_task()
                
                if orgs and orgs != ["admin"]:
                    today_create_task_list = [
                        task for task in today_create_task_list
                        if has_common_orgs(task.get("sendtask_owner_gid", []), orgs)
                    ]
                
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
            # Logic from update_mtmpl
            async def task_func():
                # 1. 從 SE2 獲取最新資料
                se2_mtmpl_list = await db_user.get_se2_mtmpl()
                if se2_mtmpl_list is None:
                    # 改為拋出例外或回傳錯誤訊息，讓 Job Manager 捕捉
                    raise Exception("從 SE2 獲取郵件樣板失敗")

                # 2. 從本地資料庫獲取現有資料
                results = await db_controller.get(Mtmpl)
                local_mtmpl_list = []
                for row in results:
                        local_mtmpl_list.append({
                            "mtmpl_uuid": row.mtmpl_uuid,
                            "mtmpl_title": row.mtmpl_title,
                            "create_time": row.create_time
                        })

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
                    # Filter/Prepare data for Mtmpl model
                    mtmpl_data_list = []
                    for item in added_list:
                        mtmpl_data_list.append({
                            "mtmpl_uuid": item.get("mtmpl_uuid"),
                            "mtmpl_title": item.get("mtmpl_title"),
                            "create_time": item.get("create_time")
                        })
                    await db_controller.batch_create(Mtmpl, mtmpl_data_list)
                    logger.info(f"Added {len(added_list)} new mail templates.")

                # 刪除樣板
                if removed_list:
                    for item in removed_list:
                        await db_controller.delete(Mtmpl, {"mtmpl_uuid": item["mtmpl_uuid"]})
                    logger.info(f"Removed {len(removed_list)} old mail templates.")

                # Add notification
                details_msg = f"新增: {len(added_list)} 筆\n刪除: {len(removed_list)} 筆"
                
                # Add notification
                details_msg = f"新增: {len(added_list)} 筆\n刪除: {len(removed_list)} 筆"
                
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

                return {
                    "added": len(added_list),
                    "removed": len(removed_list)
                }

            await job_manager.start_job(username, "更新郵件樣板列表", task_func)

        elif job_type == "check_sendtasks":
            # Logic from check_sendtasks
            async def task_func():
                orgs = params.get("orgs", [])
                # This logic was in check_sendtasks_job in main.py, 
                # but also exposed as API /api/check_sendtasks (I assume, based on useCheckTasks.js)
                # I need to replicate that logic here.
                
                sendtasks_columns = ["sendtask_uuid", "sendtask_id", "sendtask_owner_gid", "person_count",
                                     "pre_test_end_ut", "pre_test_start_ut", "pre_send_end_ut", "sendtask_create_ut", 
                                     "test_end_ut", "test_start_ut", "is_pause", "pre_test_enable", "stop_time_new"]
                
                # Get from SE2
                all_tasksname_list = await db_user.get_se2_sendtasks(sendtasks_columns)
                
                # Filter by orgs if needed (though check_sendtasks usually checks all, 
                # but for user specific update we might want to filter? 
                # The original useCheckTasks passed orgs.
                
                if orgs and orgs != ["admin"]:
                     all_tasksname_list = [
                        task for task in all_tasksname_list
                        if has_common_orgs(task.get("sendtask_owner_gid", []), orgs)
                    ]

                # Get local
                tasks = await db_controller.get(SendTask)
                my_tasksname_list = []
                for t in tasks:
                    t_dict = {c: getattr(t, c) for c in sendtasks_columns if hasattr(t, c)}
                    my_tasksname_list.append(t_dict)
                
                # ... (diff logic) ...
                # To avoid duplicating code, it would be best if this logic was in db_user.
                # But for now I will copy-paste or refactor. 
                # Refactoring db_user to have sync_sendtasks method would be better.
                
                # Let's assume I'll implement a simplified version or call a helper.
                # For now, I'll implement the diff logic here.
                
                def dict_to_hashable(d):
                    return tuple(sorted(
                        (k, tuple(v) if isinstance(v, list) else v)
                        for k, v in d.items()
                    ))
                def hashable_to_dict(t):
                    return {k: list(v) if isinstance(v, tuple) else v for k, v in t}

                all_set = set(dict_to_hashable(d) for d in all_tasksname_list)
                my_set = set(dict_to_hashable(d) for d in my_tasksname_list)
                
                added = all_set - my_set
                removed = my_set - all_set
                
                added_list = [hashable_to_dict(t) for t in added]
                removed_list = [hashable_to_dict(t) for t in removed]
                
                if added_list:
                    refresh_list = []
                    refresh_list = [task["sendtask_uuid"] for task in added_list]
                    await db_controller.upsert(SendTask, added_list, index_elements=['sendtask_uuid'])
                    
                    await db_user.refresh_sendlog_stats(refresh_list)
                
                del_count = 0
                archive_count = 0
                if removed_list:
                    from backend.services.getSe2data import get_se2_data
                    
                    for item in removed_list:
                        uuid = item["sendtask_uuid"]
                        
                        # 智慧檢查: 確認是否真的已刪除 (404)
                        data = await get_se2_data.get_sendtask(uuid)
                        
                        if data and data.get("error", {}).get("code") == 404:
                            # sendtasks刪除資料
                            await db_controller.delete(SendTask, {"sendtask_uuid": uuid})
                            # sendlog_stats 刪除資料
                            await db_controller.delete(SendLogStats, {"sendtask_uuid": uuid})
                            del_count += 1
                        elif data is None:
                            # API 回傳 None = 網路問題或 Token 失效，跳過，不做任何封存或刪除
                            logger.warning(f"SE2 API returned None for {uuid}, skipping (possible network/token issue).")
                        else:
                            # 任務仍存在於 SE2（只是本地資料有差異），僅封存
                            await db_controller.update(SendTask, {"sendtask_uuid": uuid}, {"is_archived": True})
                            archive_count += 1
                
                details_msg = ""
                if added_list:
                    details_msg += "● 新增任務:\n" + "\n".join([t.get("sendtask_id", "Unknown") for t in added_list]) + "\n"
                if removed_list:
                    details_msg += "● 封存任務:\n" + "\n".join([t.get("sendtask_id", "Unknown") for t in removed_list])

                await db_controller.create(Notification, {
                    "username": username,
                    "title": "任務列表更新完成",
                    "subtitle": f"新增 {len(added_list)} 筆，刪除 {del_count} 筆，封存 {archive_count} 筆",
                    "heading": "系統通知",
                    "path": "send_list",
                    "icon_name": "sync",
                    "icon_color": "info",
                    "details": details_msg
                })
                
                return {"added": added_list, "removed": removed_list}

            await job_manager.start_job(username, "更新任務列表", task_func)

        elif job_type == "refresh_sendlog_stats":
            # Logic from refresh_sendlog_stats
            async def task_func():
                uuids = params.get("uuids", [])
                ignore_archived = params.get("ignore_archived", False)
                if not uuids:
                    return {"message": "未指定任務 UUID"}
                
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
        
    except Exception as e:
        logger.error(f"Failed to start job {job_type}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

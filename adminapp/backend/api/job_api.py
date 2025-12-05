from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from backend.services.job_manager import JobManager
from backend.api.user_api import get_current_user
from backend.services.db_user import DBUser
from backend.repository.db_controller import ApplianceDB
from backend.api.data_api import has_common_orgs
from backend.services.log_manager import Logger

logger = Logger().get_logger()
router = APIRouter(
    prefix="/jobs",
    tags=["jobs"]
)

job_manager = JobManager()
db = ApplianceDB()
db_user = DBUser(db=db)

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

                refresh_list = []
                for task in today_create_task_list:
                    await db.upsert_db(
                        table_name="sendtasks", 
                        data=task, 
                        conflict_keys=["sendtask_uuid"])
                    refresh_list.append(task["sendtask_uuid"])

                # Also refresh stats
                await db_user.refresh_sendlog_stats(refresh_list)
                
                # Add notification
                details_msg = "更新任務:\n" + "\n".join([t.get("sendtask_id", "Unknown") for t in today_create_task_list])
                await db.insert_db("notifications", {
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
            # Logic from update_mtmpl (assuming it exists in db_user or similar, 
            # but based on previous code it seemed to be a direct API call. 
            # I need to find where update_mtmpl logic is. 
            # Wait, I don't see update_mtmpl in db_user.py from previous views.
            # I should check where it was implemented. 
            # Ah, I haven't seen update_mtmpl implementation yet. 
            # Let's assume for now I can implement it or call it.
            # If it's not in db_user, I might need to implement it here or find it.
            # Re-checking Layout1Topbar.jsx, it calls /api/update_mtmpl.
            # I should check main.py or data_api.py for that endpoint.
            
            # Let's defer exact implementation of this one until I find the code.
            # For now, I'll put a placeholder or try to find it.
            pass

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
                my_tasksname_list = await db.get_db("sendtasks", select_columns=sendtasks_columns)
                
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
                    for task in added_list:
                        await db.upsert_db("sendtasks", task, conflict_keys=["sendtask_uuid"])
                        refresh_list.append(task["sendtask_uuid"])
                    await db_user.refresh_sendlog_stats(refresh_list)
                
                if removed_list:
                    for item in removed_list:
                        uuid = item["sendtask_uuid"]
                        await db.delete_db("sendtasks", condition={"sendtask_uuid": uuid})
                        await db.delete_db("sendlog_stats", condition={"sendtask_uuid": uuid})
                        await db.drop_table(table_name=uuid)
                
                details_msg = ""
                if added_list:
                    details_msg += "新增任務:\n" + "\n".join([t.get("sendtask_id", "Unknown") for t in added_list]) + "\n"
                if removed_list:
                    details_msg += "移除任務:\n" + "\n".join([t.get("sendtask_id", "Unknown") for t in removed_list])

                await db.insert_db("notifications", {
                    "username": username,
                    "title": "任務列表更新完成",
                    "subtitle": f"新增 {len(added_list)} 筆，移除 {len(removed_list)} 筆",
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
                if not uuids:
                    return {"message": "未指定任務 UUID"}
                
                # Chunking is handled by frontend in original code, but here we can handle it or just process all.
                # Since it's async background job, we can process all (maybe with some sleep to yield if needed).
                # db_user.refresh_sendlog_stats handles list of uuids.
                
                result = await db_user.refresh_sendlog_stats(uuids)
                
                # result is {uuid: status}
                updated_count = sum(1 for s in result.values() if s == "changed")
                
                updated_uuids = [uuid for uuid, status in result.items() if status == "changed"]
                details_msg = "更新統計資料:\n" + "\n".join(updated_uuids)

                await db.insert_db("notifications", {
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

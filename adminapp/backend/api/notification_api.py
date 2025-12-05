from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from backend.services.log_manager import Logger
from backend.repository.db_controller import ApplianceDB
from backend.api.user_api import get_current_user

logger = Logger().get_logger()
router = APIRouter(
    prefix="/notification",
    tags=["notification"]
)

db = ApplianceDB()

class Notification(BaseModel):
    id: Optional[int] = None
    username: Optional[str] = None
    title: str
    subtitle: Optional[str] = None
    heading: Optional[str] = None
    timestamp: Optional[datetime] = None
    path: Optional[str] = None
    icon_name: Optional[str] = "notifications"
    icon_color: Optional[str] = "primary"
    details: Optional[str] = None
    is_read: bool = False

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class NotificationIcon(BaseModel):
    name: Optional[str]
    color: Optional[str]

class NotificationResponse(BaseModel):
    id: Optional[int]
    heading: Optional[str]
    icon: NotificationIcon
    timestamp: Optional[datetime]
    title: Optional[str]
    subtitle: Optional[str]
    path: Optional[str]
    details: Optional[str]

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

@router.get("", response_model=List[NotificationResponse])
async def get_notifications(current_user: dict = Depends(get_current_user)):
    """
    取得當前使用者的所有通知
    """
    username = current_user.get("username")
    if not username:
        raise HTTPException(status_code=400, detail="User not found")

    try:
        notifications = await db.get_db(
            table_name="notifications",
            where_column="username",
            values=username
        )
        # Sort by timestamp desc
        notifications.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        # Convert icon structure for frontend compatibility if needed
        # The frontend expects: icon: { name: "...", color: "..." }
        # But our DB stores flat fields. We'll return flat fields and let frontend handle it 
        # OR we can transform it here. 
        # Looking at NotificationBar.jsx: notification.icon.name, notification.icon.color
        # So we should transform the response to match frontend expectation OR modify frontend.
        # Let's modify the response model to match frontend expectation.
        
        result = []
        for n in notifications:
            result.append({
                "id": n.get("id"),
                "heading": n.get("heading"),
                "icon": {
                    "name": n.get("icon_name"),
                    "color": n.get("icon_color")
                },
                "timestamp": n.get("timestamp"),
                "title": n.get("title"),
                "subtitle": n.get("subtitle"),
                "path": n.get("path"),
                "details": n.get("details")
            })
            
        return result
    except Exception as e:
        logger.error(f"Error fetching notifications: {e}")
        return []

@router.post("/add")
async def add_notification(notification: Notification, current_user: dict = Depends(get_current_user)):
    """
    新增通知 (通常由系統內部呼叫，但這裡開放 API 方便測試)
    """
    username = current_user.get("username")
    data = notification.dict(exclude={"id", "timestamp"})
    data["username"] = username
    
    # Flatten icon for DB
    # data["icon_name"] = ... (already in model)
    
    try:
        await db.insert_db("notifications", data)
        # Return updated list
        return await get_notifications(current_user)
    except Exception as e:
        logger.error(f"Error adding notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/delete")
async def delete_notification(payload: dict, current_user: dict = Depends(get_current_user)):
    """
    刪除指定 ID 的通知
    """
    notification_id = payload.get("id")
    if not notification_id:
        raise HTTPException(status_code=400, detail="Missing notification ID")

    try:
        await db.delete_db("notifications", {"id": notification_id})
        return await get_notifications(current_user)
    except Exception as e:
        logger.error(f"Error deleting notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/delete-all")
async def delete_all_notifications(current_user: dict = Depends(get_current_user)):
    """
    刪除當前使用者的所有通知
    """
    username = current_user.get("username")
    try:
        await db.delete_db("notifications", {"username": username})
        return []
    except Exception as e:
        # delete_db might raise error if no records found, which is fine
        logger.warning(f"Error deleting all notifications (might be empty): {e}")
        return []

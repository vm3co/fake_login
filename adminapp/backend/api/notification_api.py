from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone
from backend.services.log_manager import Logger
from backend.repository.models import Notification as NotificationModel
from backend.repository.db_controller import db_controller
from sqlalchemy import select, delete
from backend.api.user_api import get_current_user

logger = Logger().get_logger()
router = APIRouter(
    prefix="/notification",
    tags=["notification"]
)

def serialize_datetime(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

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
        async with db_controller.get_session() as session:
            stmt = select(NotificationModel).where(NotificationModel.username == username)
            stmt = stmt.order_by(NotificationModel.timestamp.desc())
            result = await session.execute(stmt)
            notifications = result.scalars().all()
            
            result_list = []
            for n in notifications:
                result_list.append({
                    "id": n.id,
                    "heading": n.heading,
                    "icon": {
                        "name": n.icon_name,
                        "color": n.icon_color
                    },
                    "timestamp": serialize_datetime(n.timestamp),
                    "title": n.title,
                    "subtitle": n.subtitle,
                    "path": n.path,
                    "details": n.details
                })
            
            return result_list
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
        await db_controller.create(NotificationModel, {
            "username": username,
            "title": data.get("title"),
            "subtitle": data.get("subtitle"),
            "heading": data.get("heading"),
            "path": data.get("path"),
            "icon_name": data.get("icon_name"),
            "icon_color": data.get("icon_color"),
            "details": data.get("details"),
            "is_read": data.get("is_read", False)
        })
            
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
        await db_controller.delete(NotificationModel, {"id": notification_id})
            
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
        await db_controller.delete(NotificationModel, {"username": username})
        return []
    except Exception as e:
        logger.error(f"Error deleting all notifications: {e}")
        return []

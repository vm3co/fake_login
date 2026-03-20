'''
Security utilities for password hashing and verification.
This module provides functions to hash passwords and verify them using bcrypt.
'''
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from backend.core.security import verify_password
from backend.core.security import hash_password
from backend.core.security import create_access_token
from backend.services.log_manager import Logger
from jose import jwt, JWTError
from sqlalchemy import select
from backend.repository.db_controller import db_controller
from backend.repository.models import User, CustomerAcct, Acct

logger = Logger().get_logger()

# Load environment variables from .env file
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent.parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "super-secret-very-long-random-string")
ALGORITHM = "HS256"

async def get_current_user(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少或無效的授權資訊")
    
    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("username")
        if username is None:
            raise HTTPException(status_code=401, detail="Token 無效")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token 已過期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token 無效")

def get_router(db_user):
    """
    Initializes the user API router.
    :param db_user: DBUser instance
    :return: APIRouter instance for user-related endpoints
    """
    router = APIRouter()

    class UserRequest(BaseModel):
        username: str
        password: str

    @router.post(
        "/auth/register",
        tags=["user"]
        )
    async def register(data: UserRequest):
        # 檢查帳號是否已註冊
        if await db_user.user_exists(data.username):
            return {"status": "error", "message": "帳號已註冊"}
        # 密碼加密
        password_hash = hash_password(data.password)
        # 寫入資料庫並取得accts裡的資料
        result = await db_user.insert_user(username=data.username, password_hash=password_hash)
        if not result:
            return {"status": "error", "message": "註冊失敗，請稍後再試"}
        elif result["status"] == "error":
            return {"status": "error", "message": result["message"]}
        access_token = create_access_token({"acct_uuid": result["acct_uuid"], "name": result["username"]})
        user_obj = {
            "acct_uuid": result["acct_uuid"],
            "name": result["username"],
        }
        return {
            "status": "success", 
            "message": "註冊成功",
            "accessToken": access_token,
            "user": user_obj
        }

    @router.post(
        "/auth/login",
        tags=["user"]
        )
    async def login(data: UserRequest, request: Request):
        username = data.username
        password = data.password
        # 檢查是否為管理員登入
        if username == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            user =  {"acct_uuid": "admin", "username": ADMIN_EMAIL, "orgs": ["admin"]}
            access_token = create_access_token({
                "acct_uuid": "admin", 
                "username": ADMIN_EMAIL,
                "user_type": "admin"
            })
            user_obj = {
                "acct_uuid": "admin",
                "name": ADMIN_EMAIL,
                "orgs": ["admin"],
                "user_type": "admin",
                "full_name": "admin"
            }
            await db_user.add_login_log(
                username=username,
                action="login",
                status="success",
                ip_address=request.client.host,
                details="Admin login"
            )
            return {
                "status": "success", 
                "message": "管理員登入成功",
                "accessToken": access_token,
                "user": user_obj
            }
        
        # users
        user = await db_controller.get_one(User, {"username": username})

        if user:
            if verify_password(password, user.password_hash):
                # 一般使用者登入成功
                access_token = create_access_token({
                    "acct_uuid": user.acct_uuid, 
                    "username": user.username,
                    "user_type": "user"
                })
                user_obj = {
                    "acct_uuid": user.acct_uuid,
                    "name": user.username,
                    "orgs": user.orgs or [],
                    "user_type": "user",
                    "full_name": user.full_name or ""
                }
                await db_user.add_login_log(
                    username=username,
                    action="login",
                    status="success",
                    ip_address=request.client.host,
                    details="User login"
                )
                return {
                    "status": "success", 
                    "message": "使用者登入成功",
                    "accessToken": access_token,
                    "user": user_obj
                }

        # customer_accts
        customer = await db_controller.get_one(CustomerAcct, {"customer_name": username})
            
        if customer:
            if verify_password(password, customer.password_hash):
                # 客戶登入成功
                access_token = create_access_token({
                    "acct_uuid": customer.acct_uuid, 
                    "username": customer.customer_name,
                    "user_type": "customer"
                })
                customer_obj = {
                    "acct_uuid": customer.acct_uuid,
                    "name": customer.customer_name,
                    "sendtasks": customer.sendtasks or [],
                    "user_type": "customer",
                    "full_name": customer.customer_full_name or "",
                    "task_creation_enabled": customer.task_creation_enabled or False
                }
                await db_user.add_login_log(
                    username=username,
                    action="login",
                    status="success",
                    ip_address=request.client.host,
                    details="Customer login"
                )
                return {
                    "status": "success", 
                    "message": "客戶登入成功",
                    "accessToken": access_token,
                    "user": customer_obj
                }
    
        # 都找不到，登入失敗
        await db_user.add_login_log(
            username=username,
            action="login",
            status="failed",
            ip_address=request.client.host,
            details="Invalid credentials"
        )
        return {"status": "error", "message": "帳號或密碼錯誤"}    

    @router.post("/auth/logout", tags=["user"])
    async def logout(request: Request, current_user: dict = Depends(get_current_user)):
        username = current_user.get("username", "unknown")
        await db_user.add_login_log(
            username=username,
            action="logout",
            status="success",
            ip_address=request.client.host,
            details="User logout"
        )
        return {"status": "success", "message": "登出成功"}

    @router.get(
        "/auth/profile",
        tags=["user"]
        )
    async def profile(request: Request):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="缺少或無效的授權資訊")
        
        token = auth_header.split(" ")[1]
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("username")
            acct_uuid = payload.get("acct_uuid")
            user_type = payload.get("user_type")            

            # 根據用戶類型返回相應的資料
            if user_type == "admin":
                user_obj = {
                    "acct_uuid": "admin", 
                    "name": ADMIN_EMAIL, 
                    "orgs": ["admin"],
                    "user_type": "admin"
                }
                return {"user": user_obj}
            
            elif user_type == "user":
                # 查詢一般使用者
                user = await db_controller.get_one(User, {"username": username})

                if not user:
                    raise HTTPException(status_code=404, detail="找不到使用者")
                
                user_obj = {
                    "acct_uuid": user.acct_uuid,
                    "name": user.username,
                    "orgs": user.orgs or [],
                    "user_type": "user",
                    "full_name": user.full_name or ""
                }
                return {"user": user_obj}
            
            elif user_type == "customer":
                # 查詢客戶
                customer = await db_controller.get_one(CustomerAcct, {"customer_name": username})

                if not customer:
                    raise HTTPException(status_code=404, detail="找不到客戶")
                
                customer_obj = {
                    "acct_uuid": customer.acct_uuid,
                    "name": customer.customer_name,
                    "sendtasks": customer.sendtasks or [],
                    "user_type": "customer",
                    "full_name": customer.customer_full_name or "",
                    "task_creation_enabled": customer.task_creation_enabled or False
                }
                return {"user": customer_obj}
            
            else:
                raise HTTPException(status_code=401, detail="無效的使用者類型")
                
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token 已過期")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Token 無效")

    # 更新密碼
    class ChangePasswordRequest(BaseModel):
        acct_uuid: str
        old_password: str
        new_password: str

    @router.post(
        "/auth/change_password",
        tags=["user"]
        )
    async def change_password(request: ChangePasswordRequest):
        """
        更新使用者密碼 API
        :param request: 包含使用者名稱、舊密碼和新密碼的請求數據
        :param db_user: DBUser 實例
        :return: 更新結果
        """
        acct_uuid = request.acct_uuid
        old_password = request.old_password
        new_password = request.new_password

        try:
            # 更新新密碼
            result = await db_user.update_password(
                user_type="user",
                identifier=acct_uuid,
                new_password=new_password,
                old_password=old_password
            )
            if result["status"] == "success":
                return {"status": "success", "message": "密碼更新成功"}
            else:
                raise HTTPException(status_code=400, detail=result["message"])

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"更新密碼時發生錯誤: {str(e)}")

    @router.get(
        "/users/all",
        tags=["user"]
    )
    async def get_all_users(current_user: dict = Depends(get_current_user)):
        # 這裡可以加上權限檢查，例如只允許 admin 訪問
        if current_user.get("user_type") != "admin":
            raise HTTPException(status_code=403, detail="權限不足")
        
        users = await db_user.get_all_users_with_registration_status()
        return users

    @router.post(
        "/users/sync-accts",
        tags=["user"]
    )
    async def sync_accts(current_user: dict = Depends(get_current_user)):
        if current_user.get("user_type") != "admin":
            raise HTTPException(status_code=403, detail="權限不足")
        
        try:
            changed_count = 0
            se2_list = await db_user.get_se2_accts(db_user.accts_columns)
            
            if se2_list:
                await db_controller.upsert(Acct, se2_list, index_elements=['acct_uuid'])
            
            return {"status": "success", "message": f"同步完成。總共處理 {len(se2_list)} 筆帳號。"}
        except Exception as e:
            logger.error(f"Error syncing accts: {str(e)}")
            raise HTTPException(status_code=500, detail=f"同步帳號時發生錯誤: {str(e)}")

    @router.get(
        "/auth/logs",
        tags=["user"]
    )
    async def get_login_logs(limit: int = 100, current_user: dict = Depends(get_current_user)):
        if current_user.get("user_type") != "admin":
            raise HTTPException(status_code=403, detail="權限不足")
        
        logs = await db_user.get_login_logs(limit)
        return logs

    return router

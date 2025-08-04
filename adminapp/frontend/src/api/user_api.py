'''
Security utilities for password hashing and verification.
This module provides functions to hash passwords and verify them using bcrypt.
'''
import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from app.core.security import verify_password
from app.core.security import hash_password
from app.core.security import create_access_token
from app.services.log_manager import Logger
from jose import jwt, JWTError

logger = Logger().get_logger()

# Load environment variables from .env file
env_path = Path(__file__).parent.parent.parent.parent.parent / ".env"
load_dotenv(env_path)
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@acercsi.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
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

def get_router(db, db_user):
    """
    Initializes the user API router.
    :param db: Database instance
    :param db_user: DBUser instance
    :return: APIRouter instance for user-related endpoints
    """
    router = APIRouter()

    class UserRequest(BaseModel):
        username: str
        password: str

    @router.post("/auth/register")
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

    @router.post("/auth/login")
    async def login(data: UserRequest):
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
            return {
                "status": "success", 
                "message": "管理員登入成功",
                "accessToken": access_token,
                "user": user_obj
            }
        
        # users
        user_list = await db.get_db("users", where_column="username", values=username)
        if user_list:
            user = user_list[0]
            if verify_password(password, user["password_hash"]):
                # 一般使用者登入成功
                access_token = create_access_token({
                    "acct_uuid": user["acct_uuid"], 
                    "username": user["username"],
                    "user_type": "user"
                })
                user_obj = {
                    "acct_uuid": user["acct_uuid"],
                    "name": user["username"],
                    "orgs": user.get("orgs", []),
                    "user_type": "user",
                    "full_name": user.get("full_name", "")
                }
                return {
                    "status": "success", 
                    "message": "使用者登入成功",
                    "accessToken": access_token,
                    "user": user_obj
                }

        # customer_accts
        customer_list = await db.get_db("customer_accts", where_column="customer_name", values=username)
        if customer_list:
            customer = customer_list[0]
            if verify_password(password, customer["password_hash"]):
                # 客戶登入成功
                access_token = create_access_token({
                    "acct_uuid": customer["acct_uuid"], 
                    "username": customer["customer_name"],
                    "user_type": "customer"
                })
                customer_obj = {
                    "acct_uuid": customer["acct_uuid"],
                    "name": customer["customer_name"],
                    "sendtask_uuids": customer.get("sendtask_uuids", []),
                    "user_type": "customer",
                    "full_name": customer.get("customer_full_name", "")
                }
                return {
                    "status": "success", 
                    "message": "客戶登入成功",
                    "accessToken": access_token,
                    "user": customer_obj
                }
    
        # 都找不到，登入失敗
        return {"status": "error", "message": "帳號或密碼錯誤"}    

    @router.get("/auth/profile")
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
                user_list = await db.get_db("users", where_column="username", values=username)
                if not user_list:
                    raise HTTPException(status_code=404, detail="找不到使用者")
                
                user = user_list[0]
                user_obj = {
                    "acct_uuid": user["acct_uuid"],
                    "name": user["username"],
                    "orgs": user.get("orgs", []),
                    "user_type": "user",
                    "full_name": user.get("full_name", "")
                }
                return {"user": user_obj}
            
            elif user_type == "customer":
                # 查詢客戶
                customer_list = await db.get_db("customer_accts", where_column="customer_name", values=username)
                if not customer_list:
                    raise HTTPException(status_code=404, detail="找不到客戶")
                
                customer = customer_list[0]
                customer_obj = {
                    "acct_uuid": customer["acct_uuid"],
                    "name": customer["customer_name"],
                    "sendtask_uuids": customer.get("sendtask_uuids", []),
                    "user_type": "customer",
                    "full_name": customer.get("customer_full_name", "")
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

    @router.post("/auth/change_password")
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

    return router

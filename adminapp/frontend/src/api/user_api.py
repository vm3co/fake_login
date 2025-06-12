'''
Security utilities for password hashing and verification.
This module provides functions to hash passwords and verify them using bcrypt.
'''
import os
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.core.security import verify_password
from app.core.security import hash_password
from app.services.log_manager import Logger


logger = Logger().get_logger()

# Load environment variables from .env file
load_dotenv()
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")



def get_router(db, db_user):
    """
    Initializes the user API router.
    :param db: Database instance
    :param db_user: DBUser instance
    :return: APIRouter instance for user-related endpoints
    """
    router = APIRouter()

    class RegisterRequest(BaseModel):
        email: str
        password: str

    class LoginRequest(BaseModel):
        email: str
        password: str

    @router.post("/register")
    async def register(data: RegisterRequest):
        # 檢查帳號是否已註冊
        if await db_user.user_exists(data.email):
            return {"status": "error", "msg": "帳號已註冊"}
        # 密碼加密
        password_hash = hash_password(data.password)
        # 寫入資料庫
        result = await db_user.insert_user(email=data.email, password_hash=password_hash)
        return result

    @router.post("/login")
    async def login(data: LoginRequest):
        email = data.email
        password = data.password
        # 檢查是否為管理員登入
        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            return {"status": "success", "msg": "登入成功", "orgs": ["admin"]}

        # 查詢使用者
        user = await db.get_db("users", ["email"], email)
        if not user:
            return {"status": "error", "msg": "帳號或密碼錯誤"}
        # 取第一個使用者
        user = user[0]
        # 驗證密碼
        if not verify_password(data.password, user["password_hash"]):
            return {"status": "error", "msg": "帳號或密碼錯誤"}
        return {"status": "success", "msg": "登入成功", "orgs": user.get("orgs", [])}

    return router

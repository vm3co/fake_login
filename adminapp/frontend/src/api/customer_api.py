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

    @router.post("/auth/customer/register")
    async def customer_register(data: RegisterRequest):
        # 檢查帳號是否已註冊
        if await db_user.customer_exists(data.name):
            return {"status": "error", "msg": "帳號已註冊"}
        # 密碼加密
        password_hash = hash_password(data.password)
        # 寫入資料庫並取得accts裡的資料
        result = await db_user.insert_customer(name=data.name, password_hash=password_hash)
        if not result:
            return {"status": "error", "msg": "新增客戶失敗，請稍後再試"}
        elif result["status"] == "error":
            return {"status": "error", "msg": result["msg"]}
        access_token = create_access_token({"email": result["email"], "name": result["username"]})
        user_obj = {
            "email": result["email"],
            "name": result["username"],
        }
        return {
            "status": "success", 
            "msg": "註冊成功",
            "accessToken": access_token,
            "user": user_obj
        }
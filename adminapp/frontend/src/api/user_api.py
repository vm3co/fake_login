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

    @router.post("/auth/register")
    async def register(data: RegisterRequest):
        # 檢查帳號是否已註冊
        if await db_user.user_exists(data.email):
            return {"status": "error", "msg": "帳號已註冊"}
        # 密碼加密
        password_hash = hash_password(data.password)
        # 寫入資料庫並取得accts裡的資料
        result = await db_user.insert_user(email=data.email, password_hash=password_hash)
        await db_user.check_customer([data.email])
        if not result:
            return {"status": "error", "msg": "註冊失敗，請稍後再試"}
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

    @router.post("/auth/login")
    async def login(data: LoginRequest):
        email = data.email
        password = data.password
        # 檢查是否為管理員登入
        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            user =  {"email": "admin@acercsi.com", "username": "admin", "orgs": ["admin"]}
        else:
            # 查詢使用者
            user_list = await db.get_db("users", where_column="username", values=email)
            if not user_list:
                return {"status": "error", "msg": "帳號或密碼錯誤"}
            # 取第一個使用者
            user = user_list[0]
            # 驗證密碼
            if not verify_password(data.password, user["password_hash"]):
                return {"status": "error", "msg": "帳號或密碼錯誤"}
            
        # 產生 JWT token
        access_token = create_access_token({"email": user["email"], "name": user["username"]})

        # 回傳 user 物件
        user_obj = {
            "email": user["email"],
            "name": user["username"],
            "orgs": user.get("orgs", []),
        }
        return {
            "status": "success", 
            "msg": "登入成功",
            "accessToken": access_token,
            "user": user_obj
        }
    
    @router.get("/auth/profile")
    async def profile(request: Request):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="缺少或無效的授權資訊")
        token = auth_header.split(" ")[1]
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            email = payload.get("email")
            if not email:
                raise HTTPException(status_code=401, detail="Token 無效")
            
            # 檢查是否為管理員
            if email == ADMIN_EMAIL:
                user_obj = {
                    "email": "admin@acercsi.com",
                    "name": "admin",
                    "orgs": ["admin"],
                }
                return {"user": user_obj}
            
            # 查詢一般使用者
            user_list = await db.get_db("users", where_column="username", values=email)
            if not user_list:
                raise HTTPException(status_code=404, detail="找不到使用者")
            
            user = user_list[0]
            user_obj = {
                "email": user["email"],
                "name": user["username"],
                "orgs": user.get("orgs", []),
            }
            return {"user": user_obj}
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token 已過期")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Token 無效")

    return router

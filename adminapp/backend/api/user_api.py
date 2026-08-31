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
from sqlalchemy import select, func
from backend.repository.db_controller import db_controller
from backend.repository.models import User, CustomerAcct, Acct, SystemConfig

logger = Logger().get_logger()

# Load environment variables from .env file
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent.parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
ADMIN_CONTROL_PASSWORD = os.environ.get("ADMIN_CONTROL_PASSWORD", "")
PLATFORM_ADMIN_EMAIL = os.environ.get("PLATFORM_ADMIN_EMAIL", "platform@acercsi.com")
PLATFORM_ADMIN_PASSWORD = os.environ.get("PLATFORM_ADMIN_PASSWORD", "")
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "super-secret-very-long-random-string")
ALGORITHM = "HS256"

async def get_current_user(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少或無效的授權資訊")
    
    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        acct_uuid: str = payload.get("acct_uuid")
        username: str = payload.get("username")
        if acct_uuid is None or (username is None and payload.get("user_type") != "user"):
            raise HTTPException(status_code=401, detail="Token 無效")

        if payload.get("user_type") == "user":
            stmt = (
                select(Acct)
                .join(User, User.acct_uuid == Acct.acct_uuid)
                .where(User.acct_uuid == acct_uuid)
                .limit(1)
            )
            accounts = await db_controller.execute_scalars(stmt)
            if not accounts:
                raise HTTPException(status_code=401, detail="找不到使用者")
            if accounts[0].is_active is False:
                raise HTTPException(status_code=403, detail="帳號已停用")
            payload["username"] = accounts[0].acct_id
            payload["admin_role"] = accounts[0].admin_role is True
            payload["orgs"] = accounts[0].orgs or []
        elif payload.get("user_type") == "admin":
            payload["admin_role"] = True
            payload["orgs"] = []
        else:
            payload["admin_role"] = False
            payload["orgs"] = []

        return payload
    except HTTPException:
        raise
    except JWTError:
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
        access_token = create_access_token({
            "acct_uuid": result["acct_uuid"],
            "username": result["username"],
            "user_type": "user",
        })
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

        # 登入帳號（email）一律不分大小寫，這裡先取小寫版本供各種比對使用
        username_lower = username.lower() if username else username

        # ----------------------------------------------------------------
        # Step 1: 優先判斷是否為 platform_admin（不受維護模式限制）
        # ----------------------------------------------------------------
        is_platform_admin = (
            PLATFORM_ADMIN_EMAIL is not None
            and username_lower == PLATFORM_ADMIN_EMAIL.lower()
            and password == PLATFORM_ADMIN_PASSWORD
        )

        # ----------------------------------------------------------------
        # Step 2: 非 platform_admin 的人，皆需通過維護模式檢查
        # ----------------------------------------------------------------
        if not is_platform_admin:
            maintenance_record = await db_controller.get_one(SystemConfig, {"config_key": "maintenance_mode"})
            if maintenance_record and maintenance_record.config_value == "true":
                await db_user.add_login_log(
                    username=username,
                    action="login",
                    status="blocked",
                    ip_address=request.client.host,
                    details="Login blocked due to maintenance mode"
                )
                return {"status": "maintenance", "message": "系統更新中，請洽詢服務人員"}

        # ----------------------------------------------------------------
        # Step 3: 正式登入流程
        # ----------------------------------------------------------------

        # 3a. platform_admin 登入（已在 Step 1 驗證密碼）
        if is_platform_admin:
            access_token = create_access_token({
                "acct_uuid": "platform_admin",
                "username": PLATFORM_ADMIN_EMAIL,
                "user_type": "platform_admin"
            })
            user_obj = {
                "acct_uuid": "platform_admin",
                "name": PLATFORM_ADMIN_EMAIL,
                "orgs": ["platform_admin"],
                "user_type": "platform_admin",
                "admin_role": False,
                "full_name": "Platform Admin"
            }
            await db_user.add_login_log(
                username=username,
                action="login",
                status="success",
                ip_address=request.client.host,
                details="Platform admin login"
            )
            return {
                "status": "success",
                "message": "平台管理員登入成功",
                "accessToken": access_token,
                "user": user_obj
            }

        # 3b. .env 超級管理員登入
        if ADMIN_EMAIL is not None and username_lower == ADMIN_EMAIL.lower() and password == ADMIN_PASSWORD:
            access_token = create_access_token({
                "acct_uuid": "admin",
                "username": ADMIN_EMAIL,
                "user_type": "admin"
            })
            user_obj = {
                "acct_uuid": "admin",
                "name": ADMIN_EMAIL,
                "orgs": [],
                "user_type": "admin",
                "admin_role": True,
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

        # 3c. 一般使用者：以 Acct.acct_id 登入，acct_uuid 作為穩定身分。
        registered_account = await db_user.get_registered_account(acct_id=username)
        if registered_account:
            potential_user, acct = registered_account
        else:
            potential_user, acct = None, None

        if potential_user and acct.is_active is not False and verify_password(password, potential_user.password_hash):
            access_token = create_access_token({
                "acct_uuid": potential_user.acct_uuid,
                "username": acct.acct_id,
                "user_type": "user"
            })
            user_obj = {
                "acct_uuid": potential_user.acct_uuid,
                "name": acct.acct_id,
                "orgs": acct.orgs or [],
                "user_type": "user",
                "admin_role": acct.admin_role is True,
                "full_name": acct.acct_full_name or ""
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

        # 3d. 客戶帳號（customer_name 不分大小寫）
        customer = (await db_controller.execute_scalars(
            select(CustomerAcct).where(func.lower(CustomerAcct.customer_name) == username_lower).limit(1)
        ) or [None])[0]
        if customer and verify_password(password, customer.password_hash):
            access_token = create_access_token({
                "acct_uuid": customer.acct_uuid,
                "username": customer.customer_name,
                "user_type": "customer"
            })
            customer_obj = {
                "acct_uuid": customer.acct_uuid,
                "customer_uuid": customer.customer_uuid,  # 客戶 UUID
                "name": customer.customer_name,
                "sendtasks": customer.sendtasks or [],
                "user_type": "customer",
                "full_name": customer.customer_full_name or "",
                "task_creation_enabled": customer.task_creation_enabled or False,
                "task_creation_org_uuid": customer.task_creation_org_uuid or "",
                "allowed_email_domains": customer.allowed_email_domains or [],
                "max_task_count": customer.max_task_count or None
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
                    "orgs": [],
                    "user_type": "admin",
                    "admin_role": True,
                }
                return {"user": user_obj}
            
            elif user_type == "platform_admin":
                user_obj = {
                    "acct_uuid": "platform_admin",
                    "name": PLATFORM_ADMIN_EMAIL,
                    "orgs": ["platform_admin"],
                    "user_type": "platform_admin",
                    "admin_role": False,
                    "full_name": "Platform Admin"
                }
                return {"user": user_obj}

            elif user_type == "user":
                registered_account = await db_user.get_registered_account(acct_uuid=acct_uuid)
                if not registered_account:
                    raise HTTPException(status_code=404, detail="找不到使用者")
                user, acct = registered_account
                if acct.is_active is False:
                    raise HTTPException(status_code=403, detail="帳號已停用")
                
                user_obj = {
                    "acct_uuid": user.acct_uuid,
                    "name": acct.acct_id,
                    "orgs": acct.orgs or [],
                    "user_type": "user",
                    "admin_role": acct.admin_role is True,
                    "full_name": acct.acct_full_name or ""
                }
                return {"user": user_obj}
            
            elif user_type == "customer":
                # 查詢客戶
                customer = await db_controller.get_one(CustomerAcct, {"customer_name": username})

                if not customer:
                    raise HTTPException(status_code=404, detail="找不到客戶")
                
                customer_obj = {
                    "acct_uuid": customer.acct_uuid,
                    "customer_uuid": customer.customer_uuid,  # 客戶 UUID
                    "name": customer.customer_name,
                    "sendtasks": customer.sendtasks or [],
                    "user_type": "customer",
                    "full_name": customer.customer_full_name or "",
                    "task_creation_enabled": customer.task_creation_enabled or False,
                    "task_creation_org_uuid": customer.task_creation_org_uuid or "",
                    "allowed_email_domains": customer.allowed_email_domains or [],
                    "max_task_count": customer.max_task_count or None
                }
                return {"user": customer_obj}
            
            else:
                raise HTTPException(status_code=401, detail="無效的使用者類型")
                
        except HTTPException:
            raise
        except JWTError:
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

    # =========================================================
    # 系統設定 API（維護模式 + 更新公告）
    # =========================================================

    @router.get(
        "/system/config",
        tags=["system"]
    )
    async def get_system_config():
        """
        取得系統設定（維護模式狀態與公告內容），不需驗證，前端可直接呼叫
        """
        maintenance = await db_controller.get_one(SystemConfig, {"config_key": "maintenance_mode"})
        announcement = await db_controller.get_one(SystemConfig, {"config_key": "announcement"})
        return {
            "maintenance_mode": (maintenance.config_value == "true") if maintenance else False,
            "announcement": announcement.config_value if announcement else ""
        }

    class SystemConfigUpdateRequest(BaseModel):
        control_password: str
        maintenance_mode: bool = None
        announcement: str = None

    RUNTIME_CONFIG_KEYS = (
        "scheduler_refresh_token_enabled",
        "scheduler_refresh_today_create_task_enabled",
        "scheduler_refresh_notyet_today_tasks_enabled",
        "scheduler_nightly_sync_enabled",
        "scheduler_archiving_enabled",
        "startup_cache_warming_enabled",
        "sync_worker_enabled",
    )
    RUNTIME_CONFIG_DEFAULTS = {
        key: key == "scheduler_refresh_token_enabled"
        for key in RUNTIME_CONFIG_KEYS
    }

    class RuntimeConfigUpdateRequest(BaseModel):
        control_password: str
        scheduler_refresh_token_enabled: bool
        scheduler_refresh_today_create_task_enabled: bool
        scheduler_refresh_notyet_today_tasks_enabled: bool
        scheduler_nightly_sync_enabled: bool
        scheduler_archiving_enabled: bool
        startup_cache_warming_enabled: bool
        sync_worker_enabled: bool

    async def upsert_system_config(key: str, value: str):
        existing = await db_controller.get_one(SystemConfig, {"config_key": key})
        if existing:
            await db_controller.update(SystemConfig, {"config_key": key}, {"config_value": value})
        else:
            await db_controller.create(SystemConfig, {"config_key": key, "config_value": value})

    async def get_runtime_config_values():
        values = {}
        for key in RUNTIME_CONFIG_KEYS:
            record = await db_controller.get_one(SystemConfig, {"config_key": key})
            values[key] = record.config_value == "true" if record else RUNTIME_CONFIG_DEFAULTS[key]
        return values

    @router.post(
        "/system/config",
        tags=["system"]
    )
    async def update_system_config(
        data: SystemConfigUpdateRequest,
        current_user: dict = Depends(get_current_user)
    ):
        """
        更新系統設定（需要 admin 身份 + 控制密碼驗證）
        """
        if current_user.get("user_type") != "platform_admin":
            raise HTTPException(status_code=403, detail="權限不足")

        if not ADMIN_CONTROL_PASSWORD:
            raise HTTPException(status_code=500, detail="控制密碼未設定，請聯繫系統管理員")

        if data.control_password != ADMIN_CONTROL_PASSWORD:
            raise HTTPException(status_code=401, detail="控制密碼錯誤")

        updated = []

        if data.maintenance_mode is not None:
            await upsert_system_config("maintenance_mode", "true" if data.maintenance_mode else "false")
            updated.append(f"維護模式 {'開啟' if data.maintenance_mode else '關閉'}")
            logger.info(f"Admin updated maintenance_mode to: {data.maintenance_mode}")

        if data.announcement is not None:
            await upsert_system_config("announcement", data.announcement)
            updated.append("公告內容已更新")
            logger.info(f"Admin updated announcement.")

        if not updated:
            raise HTTPException(status_code=400, detail="未提供任何要更新的設定")

        return {"status": "success", "message": "、".join(updated)}

    @router.get(
        "/system/runtime-config",
        tags=["system"]
    )
    async def get_runtime_config(
        request: Request,
        current_user: dict = Depends(get_current_user)
    ):
        if current_user.get("user_type") != "platform_admin":
            raise HTTPException(status_code=403, detail="權限不足")

        configured = await get_runtime_config_values()
        get_runtime_status = getattr(request.app.state, "get_runtime_status", None)
        actual = get_runtime_status() if get_runtime_status else configured.copy()
        return {"configured": configured, "actual": actual}

    @router.post(
        "/system/runtime-config",
        tags=["system"]
    )
    async def update_runtime_config(
        data: RuntimeConfigUpdateRequest,
        request: Request,
        current_user: dict = Depends(get_current_user)
    ):
        if current_user.get("user_type") != "platform_admin":
            raise HTTPException(status_code=403, detail="權限不足")
        if not ADMIN_CONTROL_PASSWORD:
            raise HTTPException(status_code=500, detail="控制密碼未設定，請聯繫系統管理員")
        if data.control_password != ADMIN_CONTROL_PASSWORD:
            raise HTTPException(status_code=401, detail="控制密碼錯誤")

        values = {key: getattr(data, key) for key in RUNTIME_CONFIG_KEYS}
        apply_runtime_config = getattr(request.app.state, "apply_runtime_config", None)
        if apply_runtime_config is None:
            raise HTTPException(status_code=503, detail="背景服務控制器尚未就緒")

        actual = await apply_runtime_config(values)
        for key, enabled in values.items():
            await upsert_system_config(key, "true" if enabled else "false")

        logger.info(f"Platform admin updated runtime config: {values}")
        return {
            "status": "success",
            "message": "背景服務設定已更新",
            "configured": values,
            "actual": actual,
        }

    @router.get(
        "/users/all",
        tags=["user"]
    )
    async def get_all_users(current_user: dict = Depends(get_current_user)):
        if current_user.get("user_type") != "platform_admin":
            raise HTTPException(status_code=403, detail="權限不足")
        
        users = await db_user.get_all_users_with_registration_status()
        return users

    # 管理員重設使用者密碼（不需舊密碼）
    class AdminResetPasswordRequest(BaseModel):
        acct_uuid: str
        new_password: str

    @router.post(
        "/users/reset-password",
        tags=["user"]
    )
    async def admin_reset_password(
        data: AdminResetPasswordRequest,
        current_user: dict = Depends(get_current_user)
    ):
        """
        管理員重設使用者密碼 API（不需驗證舊密碼）
        :param data: 包含 acct_uuid 與 new_password
        :return: 更新結果
        """
        if current_user.get("user_type") != "platform_admin":
            raise HTTPException(status_code=403, detail="權限不足")

        if not data.new_password or len(data.new_password) < 4:
            raise HTTPException(status_code=400, detail="新密碼長度至少需要 4 個字元")

        result = await db_user.update_password(
            user_type="user",
            identifier=data.acct_uuid,
            new_password=data.new_password
        )

        if result["status"] == "success":
            logger.info(f"Admin reset password for user: {data.acct_uuid}")
            return {"status": "success", "message": "密碼重設成功"}
        raise HTTPException(status_code=400, detail=result["message"])

    @router.post(
        "/users/sync-accts",
        tags=["user"]
    )
    async def sync_accts(current_user: dict = Depends(get_current_user)):
        if current_user.get("user_type") != "platform_admin":
            raise HTTPException(status_code=403, detail="權限不足")
        
        try:
            se2_list = await db_user.get_se2_accts()
            
            if se2_list:
                await db_controller.upsert(Acct, se2_list, index_elements=['acct_uuid'])
            
            return {
                "status": "success",
                "message": f"同步完成。總共處理 {len(se2_list)} 筆帳號。"
            }
        except Exception as e:
            logger.error(f"Error syncing accts: {str(e)}")
            raise HTTPException(status_code=500, detail=f"同步帳號時發生錯誤: {str(e)}")

    @router.get(
        "/auth/logs",
        tags=["user"]
    )
    async def get_login_logs(limit: int = 100, current_user: dict = Depends(get_current_user)):
        if current_user.get("user_type") != "platform_admin":
            raise HTTPException(status_code=403, detail="權限不足")
        
        logs = await db_user.get_login_logs(limit)
        return logs

    return router

'''
Domain 管理 API：維護全域可選的 trigger page domain 清單。
'''
import re
from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.responses import JSONResponse

from backend.services.log_manager import Logger
from backend.repository.models import Domain, TriggerPage
from backend.repository.db_controller import db_controller
from backend.api.user_api import get_current_user

logger = Logger().get_logger()

router = APIRouter()

# 簡單 hostname 驗證 (RFC 1123 寬鬆版)：英數、點、連字號；不含 scheme、port、路徑
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$")


def _require_admin(current_user: dict):
    user_type = current_user.get("user_type")
    if user_type != "platform_admin":
        raise HTTPException(status_code=403, detail="僅 platform admin 可操作 domain 設定")


def _normalize(domain: str) -> str:
    return domain.strip().lower()


@router.get("/list", summary="取得所有 domain", tags=["domain"])
async def list_domains(current_user: dict = Depends(get_current_user)):
    """任何登入者可讀（CreateUrl 下拉需要）；寫入操作才限 platform_admin。"""
    rows = await db_controller.get(Domain, order_by=Domain.create_time.desc())
    return JSONResponse(content=[
        {
            "id": row.id,
            "domain": row.domain,
            "label": row.label,
            "source_company": row.source_company,
            "notes": row.notes,
            "is_active": row.is_active,
            "create_time": row.create_time.isoformat() if row.create_time else None,
        }
        for row in rows
    ])


@router.post("/create", summary="新增 domain", tags=["domain"])
async def create_domain(
    domain: str = Form(..., description="網域名稱，例如 trigger-a.example.com"),
    label: str = Form("", description="顯示名稱"),
    source_company: str = Form("", description="來源公司"),
    notes: str = Form("", description="註記"),
    current_user: dict = Depends(get_current_user)
):
    _require_admin(current_user)

    normalized = _normalize(domain)
    if not DOMAIN_RE.match(normalized):
        raise HTTPException(status_code=422, detail="網域格式不正確")

    exists = await db_controller.get_one(Domain, {"domain": normalized})
    if exists:
        raise HTTPException(status_code=409, detail=f"網域 '{normalized}' 已存在")

    obj = await db_controller.create(Domain, {
        "domain": normalized,
        "label": label or normalized,
        "source_company": source_company or None,
        "notes": notes or None,
        "is_active": True,
    })
    return {"status": "success", "id": obj.id, "domain": obj.domain}


@router.post("/update", summary="修改 domain", tags=["domain"])
async def update_domain(
    id: int = Form(...),
    label: str = Form(None),
    source_company: str = Form(None),
    notes: str = Form(None),
    is_active: bool = Form(None),
    current_user: dict = Depends(get_current_user)
):
    _require_admin(current_user)

    existing = await db_controller.get_one(Domain, {"id": id})
    if not existing:
        raise HTTPException(status_code=404, detail="找不到指定 domain")

    payload = {}
    if label is not None:
        payload["label"] = label
    if source_company is not None:
        payload["source_company"] = source_company or None
    if notes is not None:
        payload["notes"] = notes or None
    if is_active is not None:
        payload["is_active"] = is_active

    if not payload:
        return {"status": "success", "message": "無更新欄位"}

    await db_controller.update(Domain, {"id": id}, payload)
    return {"status": "success"}


@router.post("/delete", summary="刪除 domain", tags=["domain"])
async def delete_domain(
    id: int = Form(...),
    current_user: dict = Depends(get_current_user)
):
    _require_admin(current_user)

    existing = await db_controller.get_one(Domain, {"id": id})
    if not existing:
        raise HTTPException(status_code=404, detail="找不到指定 domain")

    # 檢查是否被 TriggerPage 引用
    in_use = await db_controller.get_one(TriggerPage, {"allowed_domain_id": id})
    if in_use:
        raise HTTPException(
            status_code=409,
            detail=f"此 domain 仍被頁面 '{in_use.page_value}' 使用，無法刪除"
        )

    await db_controller.delete(Domain, {"id": id})
    return {"status": "success"}

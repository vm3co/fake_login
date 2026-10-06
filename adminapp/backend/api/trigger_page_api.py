'''
處理trigger網頁
'''
import os
import shutil
import re
import time
from pathlib import Path
from fastapi import (
    APIRouter, 
    Depends, 
    Form, 
    UploadFile, 
    File, 
    HTTPException, 
    status,
    Request,
    Request,
    Query
)
from fastapi.responses import JSONResponse, PlainTextResponse, FileResponse, StreamingResponse
import asyncio
import json
from typing import AsyncIterator, Tuple
from openai import OpenAI
import google.generativeai as genai
import base64
import io
import httpx
import fcntl
from PIL import Image
from uuid import uuid4
from contextlib import contextmanager

from backend.services.log_manager import Logger
from backend.repository.models import Acct, TriggerPage, Domain
from backend.repository.db_controller import db_controller
from sqlalchemy import select, update, delete, insert
from sqlalchemy.exc import IntegrityError
from backend.services.db_user import DBUser
from backend.api.user_api import get_current_user
from backend.services.design_generator import get_design_context
from backend.services import ai_log_manager as ai_log
from backend.services.structured_page import (
    build_structured_ai_instructions,
    enrich_custom_patterns,
    render_structured_page,
    stream_structured_generation_with_retries,
    StructuredOutputValidationError,
    validate_custom_field_updates,
    validate_page_spec,
    validate_structured_html,
)

logger = Logger().get_logger()

# --- 路徑設定 ---

# 容器內的程式根目錄
BASE_DIR = Path(os.getenv("APP_BASE_DIR", "/app"))

# 檔案上傳的目的地 (對應到 loginapp/templates)
UPLOAD_DIR = BASE_DIR / "uploads_for_trigger_app_templates" 

# 應用啟動時，確保資料夾存在
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# --- 2. 驗證函式 (Dependency) ---

def validate_page_value(pageValue: str = Form(...)):
    """
    驗證 page_value，確保它適用於 URL 和檔案名稱。
    只允許小寫字母、數字和底線。
    """
    if not re.match(r"^[a-z0-9_]+$", pageValue):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="網址 ID 只能包含小寫字母、數字和底線。"
        )
    return pageValue


def validate_optional_page_value(pageValue: str = Form("")):
    normalized = (pageValue or "").strip()
    if normalized and not re.fullmatch(r"[a-z0-9_]+", normalized):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="網址 ID 只能包含小寫字母、數字和底線。"
        )
    return normalized or None


async def _page_value_exists(page_value: str) -> bool:
    return bool(
        await db_controller.get_one(TriggerPage, {"page_value": page_value})
        or (UPLOAD_DIR / f"{page_value}.html").exists()
    )


async def _resolve_new_page_value(raw_value: str | None, source: str) -> str:
    if raw_value:
        if await _page_value_exists(raw_value):
            raise HTTPException(status_code=409, detail=f"網址 ID '{raw_value}' 已存在")
        return raw_value

    prefix = {"ai": "ai", "copy": "copy"}.get(source, "page")
    for _ in range(5):
        candidate = f"{prefix}_{uuid4().hex[:12]}"
        if not await _page_value_exists(candidate):
            return candidate
    raise HTTPException(status_code=503, detail="暫時無法產生唯一網址 ID，請稍後再試")


async def _resolve_allowed_domain_id(raw_value):
    """將前端傳來的 allowedDomainId 轉成有效的 domain id；空字串/None 視為未綁定 (None)。

    驗證該 id 存在於 domains 表，否則拋 422。
    """
    if raw_value in (None, "", "null"):
        return None
    try:
        domain_id = int(raw_value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="allowedDomainId 必須為整數")
    exists = await db_controller.get_one(Domain, {"id": domain_id})
    if not exists:
        raise HTTPException(status_code=422, detail=f"找不到 domain id={domain_id}")
    return domain_id


def _parse_page_spec(raw_value: str, *, allow_custom: bool = True) -> dict:
    try:
        parsed = json.loads(raw_value)
    except (TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=422, detail="pageSpec 必須是有效的 JSON")
    return validate_page_spec(parsed, allow_custom=allow_custom)


async def _read_html_upload(file: UploadFile, *, max_bytes: int = 8 * 1024 * 1024) -> str:
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail="HTML 檔案不可超過 8 MiB")
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="HTML 檔案必須使用 UTF-8 編碼")


async def _validate_reference_image(file: UploadFile, *, max_bytes: int = 5 * 1024 * 1024) -> None:
    if file.content_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise HTTPException(status_code=422, detail="參考圖片只支援 PNG、JPEG 或 WebP")
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail="參考圖片不可超過 5 MiB")
    try:
        with Image.open(io.BytesIO(content)) as reference_image:
            reference_image.verify()
    except Exception:
        raise HTTPException(status_code=422, detail="參考圖片內容無效")
    await file.seek(0)


def _can_edit_page(page: TriggerPage, current_user: dict) -> bool:
    return (
        current_user.get("user_type") == "admin"
        or page.owner_uuid == current_user.get("acct_uuid")
    )


def _logo_html_from_data_url(data_url: str) -> str:
    if not data_url:
        return ""
    match = re.fullmatch(
        r"data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=]+)",
        data_url,
    )
    if not match:
        raise HTTPException(status_code=422, detail="Logo 只支援 PNG、JPEG 或 WebP")
    try:
        decoded = base64.b64decode(match.group(2), validate=True)
        if len(decoded) > 5 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Logo 不可超過 5 MiB")
        with Image.open(io.BytesIO(decoded)) as logo_image:
            logo_image.verify()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=422, detail="Logo 圖片內容無效")
    return f'<img src="{data_url}" alt="Brand Logo">'


@contextmanager
def _page_file_lock(page_value: str):
    lock_path = UPLOAD_DIR / f".{page_value}.lock"
    with lock_path.open("a+") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise HTTPException(status_code=409, detail="頁面正在由其他操作更新，請稍後再試")
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

# --- 3. API 端點 ---

def get_router(db_user: DBUser):

    router = APIRouter()

    @router.get(
        "/get",
        summary="獲取所有頁面選項",
        tags=["trigger page"]
    )
    async def get_page_options(request: Request):
        """
        從資料庫讀取頁面選項。
        """
        # 這裡順便做一次初始化檢查 (雖然有點髒，但確保無痛遷移)
        # 更好的做法是在 main.py lifespan 中做
        defaults = ["test", "google", "onedrive", "modern", "dropbox"]
        for val in defaults:
                exists = await db_controller.get_one(TriggerPage, {"page_value": val})
                
                if not exists:
                   await db_controller.create(TriggerPage, {
                       "page_value": val,
                       "page_label": val.capitalize(),
                       "owner_uuid": None,
                       "page_type": "system"
                   })

        # 查詢所有頁面
        rows = await db_controller.get(TriggerPage, order_by=TriggerPage.create_time.desc())

        # 批次查詢擁有者名稱：收集所有非 null 的 owner_uuid
        owner_uuids = list({row.owner_uuid for row in rows if row.owner_uuid is not None})
        owner_name_map = {}
        if owner_uuids:
            account_rows = await db_controller.get(Acct, filters={"acct_uuid": owner_uuids})
            for account in account_rows:
                owner_name_map[account.acct_uuid] = account.acct_full_name or account.acct_id

        # 批次查詢綁定 domain
        domain_ids = list({row.allowed_domain_id for row in rows if row.allowed_domain_id})
        domain_map = {}
        if domain_ids:
            domain_rows = await db_controller.get(Domain, filters={"id": domain_ids})
            for d in domain_rows:
                domain_map[d.id] = d.domain

        # 轉換格式以符合前端需求
        data = [
            {
                "value": row.page_value,
                "label": row.page_label,
                "owner": row.owner_uuid,
                "owner_name": owner_name_map.get(row.owner_uuid) if row.owner_uuid else None,
                "allowed_domain_id": row.allowed_domain_id,
                "allowed_domain": domain_map.get(row.allowed_domain_id) if row.allowed_domain_id else None,
                "structured": row.page_spec is not None,
                "spec_revision": row.spec_revision if row.page_spec is not None else None,
            }
            for row in rows
        ]

        return JSONResponse(content=data)

    def _alias_base_urls() -> list:
        """把 TRIGGER_APP_ETHAN_HOSTS 轉成可直接當連結 base 的完整 URL 清單。
        裸 host 補 https://；已帶 scheme 則原樣保留。"""
        out = []
        for raw in os.getenv("TRIGGER_APP_ETHAN_HOSTS", "").split(","):
            raw = raw.strip()
            if raw:
                out.append(raw if "//" in raw else f"https://{raw}")
        return out

    @router.get(
        "/config",
        summary="獲取前端配置 (如 Trigger App URL)",
        tags=["trigger page"]
    )
    async def get_config():
        """
        傳回前端需要的動態配置
        """
        return {
            "triggerUrl": os.getenv("TRIGGER_APP_URL", ""),
            "ethanHosts": _alias_base_urls(),
        }

    @router.get(
        "/structured/detail",
        summary="取得結構化頁面規格",
        tags=["trigger page"]
    )
    async def get_structured_page_detail(
        pageValue: str = Query(...),
        intent: str = Query("edit", pattern="^(edit|copy)$"),
        current_user: dict = Depends(get_current_user),
    ):
        page = await db_controller.get_one(TriggerPage, {"page_value": pageValue})
        if not page or page.page_spec is None:
            raise HTTPException(status_code=404, detail="找不到結構化頁面")
        if intent == "edit" and not _can_edit_page(page, current_user):
            raise HTTPException(status_code=403, detail="您沒有權限修改此頁面")
        return {
            "pageLabel": page.page_label,
            "pageValue": page.page_value,
            "allowedDomainId": page.allowed_domain_id,
            "pageSpec": page.page_spec,
            "specRevision": page.spec_revision,
        }

    @router.get(
        "/structured/page-value-availability",
        summary="檢查結構化頁面網址 ID 是否可用",
        tags=["trigger page"]
    )
    async def check_structured_page_value(
        pageValue: str = Query(...),
        currentPageValue: str = Query(None),
        current_user: dict = Depends(get_current_user),
    ):
        candidate = (pageValue or "").strip()
        if not re.fullmatch(r"[a-z0-9_]+", candidate):
            raise HTTPException(status_code=422, detail="網址 ID 只能包含小寫字母、數字和底線。")

        if currentPageValue:
            current_page = await db_controller.get_one(TriggerPage, {"page_value": currentPageValue})
            if not current_page or not _can_edit_page(current_page, current_user):
                raise HTTPException(status_code=403, detail="您沒有權限修改此頁面")
        if currentPageValue and candidate == currentPageValue:
            return {"available": True, "pageValue": candidate}

        return {
            "available": not await _page_value_exists(candidate),
            "pageValue": candidate,
        }

    @router.post(
        "/structured/create",
        summary="建立結構化頁面",
        tags=["trigger page"]
    )
    async def create_structured_page(
        pageLabel: str = Form(...),
        pageValue: str | None = Depends(validate_optional_page_value),
        pageSpec: str = Form(...),
        source: str = Form("custom"),
        templateType: str = Form("classic"),
        bgColor: str = Form("#f2f2f2"),
        bgImage: str = Form(""),
        logoData: str = Form(""),
        file: UploadFile = File(None),
        generationId: str = Form(None),
        sourcePageValue: str = Form(None),
        allowedDomainId: str = Form(None),
        current_user: dict = Depends(get_current_user),
    ):
        if source not in {"custom", "ai", "copy"}:
            raise HTTPException(status_code=422, detail="結構化頁面來源不正確")
        pageValue = await _resolve_new_page_value(pageValue, source)
        spec = _parse_page_spec(pageSpec, allow_custom=source != "custom")
        domain_id = await _resolve_allowed_domain_id(allowedDomainId)

        if source == "ai":
            if not generationId or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", generationId):
                raise HTTPException(status_code=422, detail="AI 結構化頁面缺少有效的 generationId")
            if not ai_log.log_path(generationId).is_file():
                raise HTTPException(status_code=422, detail="找不到對應的 AI 生成紀錄")
        elif source == "copy":
            if not sourcePageValue or not re.fullmatch(r"^[a-z0-9_]+$", sourcePageValue):
                raise HTTPException(status_code=422, detail="複製頁面缺少有效的來源網址 ID")
            source_page = await db_controller.get_one(TriggerPage, {"page_value": sourcePageValue})
            if not source_page or source_page.page_spec is None:
                raise HTTPException(status_code=404, detail="找不到結構化來源頁面")
            validate_custom_field_updates(source_page.page_spec, spec)

        if source in {"ai", "copy"}:
            if file is None:
                raise HTTPException(status_code=422, detail="結構化頁面缺少 HTML 檔案")
            try:
                html_content = await _read_html_upload(file)
            finally:
                await file.close()
            spec = enrich_custom_patterns(html_content, spec)
            spec = validate_page_spec(spec)
            validate_structured_html(html_content, spec, expected_revision=1)
        else:
            if file is not None:
                await file.close()
                raise HTTPException(status_code=422, detail="自訂結構化頁面不可上傳任意 HTML")
            html_content = render_structured_page(
                spec,
                revision=1,
                template_type=templateType,
                background_color=bgColor,
                background_image=bgImage,
                logo_html=_logo_html_from_data_url(logoData),
            )
            validate_structured_html(html_content, spec, expected_revision=1)

        save_path = UPLOAD_DIR / f"{pageValue}.html"
        temp_path = UPLOAD_DIR / f".{pageValue}.{uuid4().hex}.tmp"
        if save_path.exists():
            raise HTTPException(status_code=409, detail=f"檔案 '{save_path.name}' 已存在")

        created_file = False
        try:
            temp_path.write_text(html_content, encoding="utf-8")
            try:
                os.link(temp_path, save_path)
            except FileExistsError:
                raise HTTPException(status_code=409, detail=f"檔案 '{save_path.name}' 已存在")
            created_file = True
            await db_controller.create(TriggerPage, {
                "page_value": pageValue,
                "page_label": pageLabel,
                "owner_uuid": current_user.get("acct_uuid"),
                "page_type": {
                    "ai": "structured_ai",
                    "copy": "structured_copy",
                }.get(source, "structured_custom"),
                "allowed_domain_id": domain_id,
                "page_spec": spec,
                "spec_revision": 1,
            })
        except HTTPException:
            if created_file and save_path.exists():
                save_path.unlink()
            raise
        except IntegrityError:
            if created_file and save_path.exists():
                save_path.unlink()
            raise HTTPException(status_code=409, detail=f"網址 ID '{pageValue}' 已存在")
        except Exception as exc:
            if created_file and save_path.exists():
                save_path.unlink()
            raise HTTPException(status_code=500, detail=f"建立結構化頁面失敗: {exc}")
        finally:
            if temp_path.exists():
                temp_path.unlink()

        if generationId:
            ai_log.write_upload_event(generationId, {
                "user_uuid": current_user.get("acct_uuid"),
                "page_label": pageLabel,
                "page_value": pageValue,
                "saved_file": str(save_path.resolve()),
            })
        return {
            "status": "success",
            "message": f"頁面 '{pageLabel}' 已成功建立。",
            "pageValue": pageValue,
            "pageSpec": spec,
            "specRevision": 1,
        }

    @router.post(
        "/structured/update",
        summary="更新結構化頁面",
        tags=["trigger page"]
    )
    async def update_structured_page(
        pageLabel: str = Form(...),
        pageValue: str | None = Depends(validate_optional_page_value),
        oldPageValue: str = Form(...),
        pageSpec: str = Form(...),
        specRevision: int = Form(...),
        file: UploadFile = File(...),
        allowedDomainId: str = Form(None),
        current_user: dict = Depends(get_current_user),
    ):
        try:
            html_content = await _read_html_upload(file)
        finally:
            await file.close()

        with _page_file_lock(oldPageValue):
            page = await db_controller.get_one(TriggerPage, {"page_value": oldPageValue})
            if not page or page.page_spec is None:
                raise HTTPException(status_code=404, detail="找不到結構化頁面")
            if not _can_edit_page(page, current_user):
                raise HTTPException(status_code=403, detail="您沒有權限修改此頁面")
            if page.spec_revision != specRevision:
                raise HTTPException(status_code=409, detail="頁面已由其他操作更新，請重新載入後再試")

            pageValue = pageValue or oldPageValue

            if pageValue != oldPageValue:
                conflict = await db_controller.get_one(TriggerPage, {"page_value": pageValue})
                if conflict:
                    raise HTTPException(status_code=409, detail=f"網址 ID '{pageValue}' 已被使用")

            spec = _parse_page_spec(pageSpec, allow_custom=True)
            validate_custom_field_updates(page.page_spec, spec)
            next_revision = specRevision + 1
            domain_id = await _resolve_allowed_domain_id(allowedDomainId)
            validate_structured_html(html_content, spec, expected_revision=next_revision)

            old_path = UPLOAD_DIR / f"{oldPageValue}.html"
            new_path = UPLOAD_DIR / f"{pageValue}.html"
            if not old_path.exists():
                raise HTTPException(status_code=404, detail="找不到結構化頁面 HTML")
            backup_path = UPLOAD_DIR / f".{oldPageValue}.{uuid4().hex}.bak"
            temp_path = UPLOAD_DIR / f".{pageValue}.{uuid4().hex}.tmp"

            wrote_new_path = False
            try:
                shutil.copy2(old_path, backup_path)
                temp_path.write_text(html_content, encoding="utf-8")
                if old_path == new_path:
                    temp_path.replace(new_path)
                else:
                    try:
                        os.link(temp_path, new_path)
                    except FileExistsError:
                        raise HTTPException(status_code=409, detail=f"檔案 '{new_path.name}' 已存在")
                wrote_new_path = True
                updated = await db_controller.update(
                    TriggerPage,
                    {"id": page.id, "spec_revision": specRevision},
                    {
                        "page_label": pageLabel,
                        "page_value": pageValue,
                        "allowed_domain_id": domain_id,
                        "page_spec": spec,
                        "spec_revision": next_revision,
                    },
                )
                if updated != 1:
                    raise HTTPException(status_code=409, detail="頁面已由其他操作更新，請重新載入後再試")
                if old_path != new_path and old_path.exists():
                    old_path.unlink()
            except Exception:
                if wrote_new_path and new_path.exists():
                    new_path.unlink()
                if backup_path.exists():
                    shutil.copy2(backup_path, old_path)
                raise
            finally:
                if backup_path.exists():
                    backup_path.unlink()
                if temp_path.exists():
                    temp_path.unlink()

        return {
            "status": "success",
            "message": f"頁面 '{pageLabel}' 已成功更新。",
            "pageValue": pageValue,
            "pageSpec": spec,
            "specRevision": next_revision,
        }

    @router.get(
        "/download",
        summary="下載頁面模板檔案",
        tags=["trigger page"]
    )
    async def download_page(
        pageValue: str = Query(..., description="要下載的頁面ID"),
        current_user: dict = Depends(get_current_user)
    ):
        """
        下載指定頁面的 HTML 檔案
        """
        if not re.match(r"^[a-z0-9_]+$", pageValue):
             raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="網址 ID 只能包含小寫字母、數字和底線。"
            )

        filename = f"{pageValue}.html"
        file_path = UPLOAD_DIR / filename

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="找不到指定的頁面檔案")

        return FileResponse(
            path=file_path, 
            filename=filename, 
            media_type='text/html'
        )

    @router.post(
        "/upload", 
        summary="上傳新頁面模板",
        tags=["trigger page"]
    )
    async def upload_new_page(
        # Form(...) 用於接收 multipart/form-data 的文字欄位
        pageLabel: str = Form(..., description="顯示在選項中的名稱 (e.g., '我的新頁面')"),
        pageValue: str = Depends(validate_page_value), # 使用 Depends 來驗證
        file: UploadFile = File(..., description="要上傳的 HTML 模板檔案"),
        generationId: str = Form(None, description="若由 AI 生成，請帶上對應的 generation_id 以串接日誌"),
        allowedDomainId: str = Form(None, description="綁定的 domain id；留空代表不綁定，套用預設"),
        current_user: dict = Depends(get_current_user)
    ):
        """
        上傳並儲存新頁面。
        """
        user_uuid = current_user.get("acct_uuid")
        domain_id = await _resolve_allowed_domain_id(allowedDomainId)

        # 檢查是否已存在 (Global Check)
        exists = await db_controller.get_one(TriggerPage, {"page_value": pageValue})

        if exists:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"網址 ID '{pageValue}' 已存在。"
            )

        # --- 任務 1: 將上傳的檔案儲存到 loginapp 的 templates 資料夾 ---
        new_filename = f"{pageValue}.html"
        save_path = UPLOAD_DIR / new_filename

        # 雖然 DB 檢查過了，但檔案系統也要確保一下 (或直接覆蓋)
        try:
            with save_path.open("wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"儲存檔案失敗: {str(e)}"
            )
        finally:
            await file.close()

        # --- 任務 2: 將資料新增到 DB ---
        try:
            await db_controller.create(TriggerPage, {
                "page_value": pageValue,
                "page_label": pageLabel,
                "owner_uuid": user_uuid,
                "page_type": "custom",
                "allowed_domain_id": domain_id,
            })
        except Exception as e:
            # [復原] 如果 DB 操作失敗，刪除剛剛上傳的檔案
            if save_path.exists():
                save_path.unlink()
            if generationId:
                ai_log.write_upload_event(generationId, {
                    "user_uuid": user_uuid,
                    "page_label": pageLabel,
                    "page_value": pageValue,
                    "error": f"資料庫寫入失敗: {str(e)}",
                }, success=False)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"寫入資料庫失敗: {str(e)}"
            )

        if generationId:
            ai_log.write_upload_event(generationId, {
                "user_uuid": user_uuid,
                "page_label": pageLabel,
                "page_value": pageValue,
                "saved_file": str(save_path.resolve()),
            })

        return {
            "status": "success",
            "message": f"頁面 '{pageLabel}' 已成功上傳。",
            "new_entry": {"value": pageValue, "label": pageLabel, "owner": user_uuid}
        }

    @router.post(
        "/update",
        summary="修改現有頁面模板"
    )
    async def update_page(
        pageLabel: str = Form(..., description="新的Label"),
        pageValue: str = Depends(validate_page_value),
        oldPageValue: str = Form(..., description="要修改的目標 value"),
        file: UploadFile = File(None, description="上傳新的 HTML 檔案來覆蓋"),
        allowedDomainId: str = Form(None, description="綁定的 domain id；留空代表不綁定，套用預設"),
        current_user: dict = Depends(get_current_user)
    ):
        user_uuid = current_user.get("acct_uuid")
        user_type = current_user.get("user_type")
        domain_id = await _resolve_allowed_domain_id(allowedDomainId)
        
        # 權限檢查: 找出舊頁面
        old_page = await db_controller.get_one(TriggerPage, {"page_value": oldPageValue})
        
        if not old_page:
            raise HTTPException(status_code=404, detail="找不到欲修改的頁面")

        if old_page.page_spec is not None:
            raise HTTPException(status_code=409, detail="結構化頁面請使用欄位編輯器修改")
    
        # 權限邏輯
        if old_page.owner_uuid is None:
            raise HTTPException(status_code=403, detail="系統預設頁面無法修改")
            
        if user_type != "admin" and old_page.owner_uuid != user_uuid:
                raise HTTPException(status_code=403, detail="您沒有權限修改此頁面")

        is_value_changing = (pageValue != oldPageValue)

        # 如果改了 pageValue，檢查新 value 是否衝突
        if is_value_changing:
            conflict_check = await db_controller.get_one(TriggerPage, {"page_value": pageValue})
            if conflict_check:
                raise HTTPException(status_code=409, detail=f"網址 ID '{pageValue}' 已被使用")

        # --- 檔案處理 ---
        old_filename = f"{oldPageValue}.html"
        old_file_path = UPLOAD_DIR / old_filename
        
        new_filename = f"{pageValue}.html"
        new_file_path = UPLOAD_DIR / new_filename
        
        try:
            if file:
                # 有上傳新檔 -> 寫入新檔
                with new_file_path.open("wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                
                # 如果改名且舊檔存在，刪除舊檔
                if is_value_changing and old_file_path.exists():
                    old_file_path.unlink()
            else:
                # 沒上傳新檔，只有改名
                if is_value_changing:
                    if old_file_path.exists():
                        old_file_path.rename(new_file_path)
                    else:
                        logger.warning(f"舊檔案 {old_filename} 不存在，跳過重命名")
        
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"檔案處理失敗: {str(e)}")
        finally:
            if file:
                await file.close()

        # --- DB 更新 ---
        try:
            await db_controller.update(TriggerPage, {"id": old_page.id}, {
                "page_label": pageLabel,
                "page_value": pageValue,
                "allowed_domain_id": domain_id,
            })
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"資料庫更新失敗: {str(e)}")

        return {
            "status": "success",
            "message": f"頁面 '{pageLabel}' 已成功更新。"
        }    

    @router.post(
        "/delete",
        summary="刪除現有頁面模板"
    )
    async def delete_page(
        pageValue: str = Form(..., description="要刪除的目標 value"),
        current_user: dict = Depends(get_current_user)
    ):
        user_uuid = current_user.get("acct_uuid")
        user_type = current_user.get("user_type")
        
        # 查詢頁面
        page = await db_controller.get_one(TriggerPage, {"page_value": pageValue})
        
        if not page:
            raise HTTPException(status_code=404, detail="找不到頁面")
        
        # 權限邏輯
        if page.owner_uuid is None:
            raise HTTPException(status_code=403, detail="系統預設頁面無法刪除")
            
        if user_type != "admin" and page.owner_uuid != user_uuid:
            raise HTTPException(status_code=403, detail="您沒有權限刪除此頁面")

        # --- 刪除 DB ---
        try:
            await db_controller.delete(TriggerPage, {"id": page.id})
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"資料庫刪除失敗: {str(e)}")

        # --- 刪除檔案 (不阻擋流程) ---
        filename = f"{pageValue}.html"
        save_path = UPLOAD_DIR / filename
        
        if save_path.exists():
            try:
                save_path.unlink()
            except Exception as e:
                logger.error(f"刪除檔案 {filename} 失敗: {e}")
        
        return {
            "status": "success",
            "message": f"頁面已成功刪除。"
        }

    # (Create Custom) 建立自訂頁面
    @router.post(
        "/create_page",
        summary="建立自訂頁面",
        tags=["trigger page"]
    )
    async def create_custom_page(
        pageLabel: str = Form(..., description="顯示在選項中的名稱 (e.g., '我的新頁面')"),
        pageValue: str = Depends(validate_page_value),
        pageTitle: str = Form(..., description="網頁標題 (HTML Title)"),
        bgColor: str = Form(..., description="背景顏色 (e.g., '#f2f2f2' or 'white')"),
        bgImage: str = Form("", description="背景圖片 URL (可選)"),
        formTitle: str = Form(..., description="表單標題 (e.g., '登入')"),
        inputLabel: str = Form(..., description="輸入框標籤 (e.g., 'Email:')"),
        isEmail: bool = Form(..., description="輸入欄是否為電子郵件"),
        btnText: str = Form(..., description="按鈕文字 (e.g., '登入')"),
        templateType: str = Form("classic", description="版型選擇: 'classic' or 'modern'"),
        svgContent: str = Form("", description="SVG 圖示內容 (僅用於 Modern 版型)"),
        allowedDomainId: str = Form(None, description="綁定的 domain id；留空代表不綁定，套用預設"),
        current_user: dict = Depends(get_current_user)
    ):
        """
        根據使用者輸入的設定，自動生成 HTML 檔案並新增到選項中。
        """
        domain_id = await _resolve_allowed_domain_id(allowedDomainId)
        user_uuid = current_user.get("acct_uuid")

        # 檢查重複
        exists = await db_controller.get_one(TriggerPage, {"page_value": pageValue})
             
        if exists:
            raise HTTPException(status_code=409, detail=f"網址 ID '{pageValue}' 已存在")

        mail_type = "email" if isEmail else "text"

        # --- 1. 準備 HTML 內容 ---
        
        # 經典版型 (Test.html based)
        CLASSIC_PAGE_TEMPLATE = """
            <!DOCTYPE html>
            <html lang="zh-Hant">
            <head>
                <meta charset="UTF-8" />
                <title>{title}</title>
                <style>
                body {{
                    font-family: sans-serif;
                    background-color: {bg_color};
                    background-image: {bg_image_css};
                    background-size: cover;
                    background-position: center;
                    background-repeat: no-repeat;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                }}
                .login-box {{
                    background: white;
                    padding: 2rem;
                    border-radius: 10px;
                    box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1);
                    width: 300px;
                    opacity: 0.95; /* 稍微透明一點以免遮擋背景太死 */
                }}
                input[type="{mail_type}"] {{
                    width: 100%;
                    padding: 10px;
                    margin-top: 10px;
                    margin-bottom: 20px;
                    border: 1px solid #ccc;
                    border-radius: 5px;
                    box-sizing: border-box; /* 確保 padding 不會撐開寬度 */
                }}
                button {{
                    width: 100%;
                    padding: 10px;
                    background-color: #4caf50;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    cursor: pointer;
                }}
                button:hover {{
                    background-color: #45a049;
                }}
                </style>
            </head>
            <body>
                <div class="login-box">
                <h2>{form_title}</h2>
                <form id="login-form">
                    <label for="email">{input_label}</label>
                    <input type="{mail_type}" id="{mail_type}" required />
                    <button type="submit">{btn_text}</button>
                </form>
                </div>

                <script>
                const API_BASE_PATH = "{{{{ api_base_path }}}}";
                </script>
                <script src="{{{{ url_for('static', path='js/recordingLogin.js') }}}}"></script>
            </body>

            </html>
            """

        # 現代版型 (Modern_login.html based)
        MODERN_PAGE_TEMPLATE = """
            <!DOCTYPE html>
            <html lang="zh-Hant">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>{title}</title>
                <!-- Google Fonts -->
                <link rel="preconnect" href="https://fonts.googleapis.com">
                <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
                <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
                <style>
                    :root {{
                        --primary-color: #4f46e5;
                        --primary-hover: #4338ca;
                        --bg-gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        --bg-color: {bg_color};
                        --card-bg: rgba(255, 255, 255, 0.95);
                        --text-color: #1f2937;
                        --text-secondary: #6b7280;
                    }}

                    body {{
                        font-family: 'Inter', sans-serif;
                        background: {bg_css};
                        background-size: cover;
                        background-position: center;
                        background-repeat: no-repeat;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        min-height: 100vh;
                        margin: 0;
                        padding: 20px;
                    }}

                    .login-card {{
                        background: var(--card-bg);
                        padding: 3rem;
                        border-radius: 16px;
                        box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
                        width: 100%;
                        max-width: 400px;
                        text-align: center;
                        backdrop-filter: blur(10px);
                        transition: transform 0.3s ease;
                    }}

                    .login-card:hover {{
                        transform: translateY(-5px);
                    }}

                    .icon-container {{
                        width: 64px;
                        height: 64px;
                        background: rgba(79, 70, 229, 0.1);
                        border-radius: 50%;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        margin: 0 auto 1.5rem;
                    }}

                    .icon-container svg {{
                        width: 32px;
                        height: 32px;
                        color: var(--primary-color);
                    }}

                    h2 {{
                        color: var(--text-color);
                        font-size: 1.875rem;
                        font-weight: 700;
                        margin: 0 0 0.5rem;
                    }}

                    p.subtitle {{
                        color: var(--text-secondary);
                        margin-bottom: 2rem;
                        font-size: 0.875rem;
                    }}

                    .form-group {{
                        margin-bottom: 1.5rem;
                        text-align: left;
                    }}

                    label {{
                        display: block;
                        color: var(--text-color);
                        font-size: 0.875rem;
                        font-weight: 500;
                        margin-bottom: 0.5rem;
                    }}

                    input[type="{mail_type}"] {{
                        width: 100%;
                        padding: 0.75rem 1rem;
                        border: 1px solid #d1d5db;
                        border-radius: 0.5rem;
                        font-size: 1rem;
                        box-sizing: border-box; /* Crucial for padding */
                        transition: border-color 0.2s, box-shadow 0.2s;
                        outline: none;
                    }}

                    input[type="{mail_type}"]:focus {{
                        border-color: var(--primary-color);
                        box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
                    }}

                    button {{
                        width: 100%;
                        padding: 0.875rem;
                        background-color: var(--primary-color);
                        color: white;
                        border: none;
                        border-radius: 0.5rem;
                        font-size: 1rem;
                        font-weight: 600;
                        cursor: pointer;
                        transition: background-color 0.2s, transform 0.1s;
                    }}

                    button:hover {{
                        background-color: var(--primary-hover);
                    }}

                    button:active {{
                        transform: scale(0.98);
                    }}

                    .footer {{
                        margin-top: 1.5rem;
                        font-size: 0.75rem;
                        color: var(--text-secondary);
                    }}
                </style>
            </head>
            <body>
                <div class="login-card">
                    <div class="icon-container">
                        {svg_icon}
                    </div>
                    
                    <h2>{form_title}</h2>
                    <!-- <p class="subtitle">請輸入您的電子郵件以繼續</p> -->

                    <form id="login-form">
                        <div class="form-group">
                            <label for="email">{input_label}</label>
                            <input type="{mail_type}" id="{mail_type}" required />
                        </div>
                        <button type="submit">{btn_text}</button>
                    </form>

                    <div class="footer">
                        © 2024 Secure Portal. All rights reserved.
                    </div>
                </div>

                <!-- Required Tracking Scripts -->
                <script>
                const API_BASE_PATH = "{{{{ api_base_path }}}}";
                </script>
                <script src="{{{{ url_for('static', path='js/recordingLogin.js') }}}}"></script>
            </body>
            </html>
            """
        
        bg_image_css = f"url('{bgImage}')" if bgImage else "none"
        
        DEFAULT_SVG = """<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>"""

        if templateType == 'modern':
            # Modern Template Logic
            # 如果背景圖片存在，使用背景圖片，否則使用背景顏色 (但 modern template 的 CSS 變數需要調整)
            # 為了簡化，如果 bgImage 存在，bg_css = url(...), 否則 bg_css = var(--bg-color)
            if bgImage:
                bg_css = f"url('{bgImage}')"
            else:
                 # 使用漸層或純色? 這裡保留原來的漸層或是使用者指定的 pure color
                 # 如果使用者指定了 bgColor (e.g. #f2f2f2), 我們可以用它覆蓋漸層
                 bg_css = bgColor if bgColor else "linear-gradient(135deg, #667eea 0%, #764ba2 100%)"
            
            # SVG 處理
            final_svg = svgContent if svgContent and svgContent.strip() else DEFAULT_SVG

            html_content = MODERN_PAGE_TEMPLATE.format(
                title=pageTitle,
                bg_color=bgColor, # 其實這個變數只在 fallback 用
                bg_css=bg_css,
                svg_icon=final_svg,
                form_title=formTitle,
                input_label=inputLabel,
                btn_text=btnText,
                mail_type=mail_type
            )
        else:
            # Classic Template Logic
            html_content = CLASSIC_PAGE_TEMPLATE.format(
                title=pageTitle,
                bg_color=bgColor,
                bg_image_css=bg_image_css,
                form_title=formTitle,
                input_label=inputLabel,
                btn_text=btnText,
                mail_type=mail_type
            )

        
        # --- 2. 儲存檔案 ---
        filename = f"{pageValue}.html"
        save_path = UPLOAD_DIR / filename
        
        # 雖然 DB 檢查過 UNIQUE，但檔案系統再檢查一次比較保險
        if save_path.exists():
            raise HTTPException(status_code=409, detail=f"檔案 '{filename}' 已存在")
            
        try:
             with save_path.open("w", encoding="utf-8") as f:
                f.write(html_content)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"建立檔案失敗: {str(e)}")

        # --- 3. 更新 DB ---
        try:
            await db_controller.create(TriggerPage, {
                "page_value": pageValue,
                "page_label": pageLabel,
                "owner_uuid": user_uuid,
                "page_type": "custom",
                "allowed_domain_id": domain_id,
            })
        except Exception as e:
            if save_path.exists():
                save_path.unlink() # Rollback
            raise HTTPException(status_code=500, detail=f"資料庫寫入失敗: {str(e)}")

        return {
            "status": "success",
            "message": f"自訂頁面 '{pageLabel}' 已成功建立。",
            "new_entry": {"value": pageValue, "label": pageLabel, "owner": user_uuid}
        }

    async def call_llm(model: str, system_instructions: str, user_prompt: str, ref_url: str = None, image: UploadFile = None, screenshot_b64: str = None, generation_id: str = None) -> AsyncIterator[Tuple[str, str]]:
        """
        統一呼叫各家 LLM 模型的內部入口函式（async generator）
        支援：gemini, gpt, litellm(地端), gchat(地端)

        yield ("chunk", delta_text): 每收到一段 token 時發出
        yield ("done", full_cleaned_text): 全部收完、清理後發出

        使用 stream=True 避免 Cloudflare 524 timeout（origin 長時間靜止問題）。
        """
        # ==========================================
        # 1. 準備通用的使用者提示詞 (Prompt Suffix)
        # ==========================================
        prompt_suffix = f"使用者的需求：{user_prompt}"
        if ref_url:
            prompt_suffix += f"\n\n[參考網址]\n使用者提供了一個參考網址：{ref_url}\n請參考該網站的設計。"

        # ==========================================
        # 2. 依據模型分流執行
        # ==========================================
        if model == "gemini":
            # ----------------------------------
            # [A] Gemini 專屬邏輯 (Google SDK, async stream)
            # ----------------------------------
            gemini_api_key = os.getenv("GEMINI_APY_KEY")
            if not gemini_api_key:
                raise Exception("未提供 Gemini API Key")
            genai.configure(api_key=gemini_api_key)
            genai_model = genai.GenerativeModel("gemini-2.5-flash")
            full_prompt = f"{system_instructions}\n\n{prompt_suffix}"
            contents = [full_prompt]
            if image:
                file_bytes = await image.read()
                pil_image = Image.open(io.BytesIO(file_bytes))
                contents.append(pil_image)
            if screenshot_b64:
                header, encoded = screenshot_b64.split(",", 1)
                img_data = base64.b64decode(encoded)
                pil_image = Image.open(io.BytesIO(img_data))
                contents.append(pil_image)

            logger.info(f"[{model}] 開始呼叫模型 gemini-2.5-flash (streaming)...")
            start_ts = time.time()
            generated_text = ""
            response = await genai_model.generate_content_async(contents, stream=True)
            async for chunk in response:
                if chunk.text:
                    generated_text += chunk.text
                    yield ("chunk", chunk.text)
            end_ts = time.time()

            if generation_id:
                ai_log.write_section(generation_id, f"[{model}] Model Response (Content)", generated_text)
                ai_log.write_timing(generation_id, f"[{model}] LLM Call", start_ts, end_ts)

        else:
            # ----------------------------------
            # [B] OpenAI 相容模型邏輯 (GPT, LiteLLM, GChat) — AsyncOpenAI + stream=True
            # ----------------------------------

            # (1) 基礎參數初始化
            base_url = None
            api_key = None
            model_name = ""
            verify_cert = True
            headers = {"Content-Type": "application/json"}
            event_hooks = {}
            is_text_only = False

            def force_ua(request: httpx.Request):
                request.headers["User-Agent"] = "curl/8.5.0"

            # (2) 依據不同模型注入專屬設定
            if model == "litellm":
                api_key = os.getenv("LITELLM_API_KEY")
                server_ip = os.getenv("LITELLM_SERVER_IP")
                if not api_key or not server_ip:
                    raise Exception("未設定 LiteLLM 環境變數")
                base_url = f"http://{server_ip}/v1"
                model_name = "gemma-27b"
                is_text_only = True

            elif model.startswith("gchat"):
                cf_access_token = os.getenv("CF_ACCESS_TOKEN")
                if not cf_access_token:
                    raise Exception("未設定 CF_ACCESS_TOKEN 環境變數")

                # gchat sub-model 對照表：(送進 API 的 model_name, 是否支援視覺輸入)
                GCHAT_MODELS = {
                    "gchat_gemma431b": ("Gemma-4-31B", True),      # 舊模型，已停用，僅為相容保留
                    "gchat_gptoss": ("gpt-oss-20b", False),
                    "gchat_gpt55":  ("gpt-5.5",     True),
                    "gchat_gpt54":  ("gpt-5.4",     True),
                    "gchat_gpt54mini": ("gpt-5.4-mini", True),
                    "gchat_gemma12b": ("Gemma-4-12B", True),
                }

                api_key = "dummy_key"
                base_url = "https://chatapi.acsi-lab.dev/v1"
                model_name, supports_vision = GCHAT_MODELS.get(model)
                headers["CF-Access-Token"] = cf_access_token
                headers["User-Agent"] = "curl/8.5.0"
                event_hooks["request"] = [force_ua]
                verify_cert = False
                is_text_only = not supports_vision

            elif model in ("gpt_terra", "gpt_sol"):
                # 獨立於 "litellm" 分支，走專屬的 Gateway 位址設定，
                # 未來若要調整 GPT 這條路的 URL 不會影響到 litellm(gemma-27b) 那條路
                # terra / sol 是同一個 Gateway 底下的兩個不同模型，各自的實際模型名稱可用環境變數覆蓋
                GPT_MODELS = {
                    "gpt_terra": os.getenv("GPT_MODEL_NAME_TERRA", "gpt-5.6-terra"),
                    "gpt_sol": os.getenv("GPT_MODEL_NAME_SOL", "gpt-5.6-sol"),
                }
                api_key = os.getenv("GPT_LITELLM_API_KEY")
                server_ip = os.getenv("GPT_LITELLM_SERVER_IP")
                if not api_key or not server_ip:
                    raise Exception("未設定 GPT LiteLLM 環境變數 (GPT_LITELLM_SERVER_IP, GPT_LITELLM_API_KEY)")
                base_url = f"http://{server_ip}/v1"
                model_name = GPT_MODELS[model]

            else:
                raise Exception(f"不支援的模型類型: {model}")

            # (3) 建立 SYNC HTTP Client（與原始碼相同設定，確保連線穩定）
            http_client = httpx.Client(
                verify=verify_cert,
                headers=headers,
                event_hooks=event_hooks if event_hooks else None,
                timeout=httpx.Timeout(300.0)
            )

            sync_client = OpenAI(api_key=api_key, base_url=base_url, http_client=http_client)

            # (4) 準備 Request 內容 (區分純文字與多模態)
            if is_text_only:
                user_content = prompt_suffix
            else:
                user_content = [{"type": "text", "text": prompt_suffix}]
                if image:
                    file_bytes = await image.read()
                    b64 = base64.b64encode(file_bytes).decode('utf-8')
                    mime_type = image.content_type or "image/jpeg"
                    user_content.append({"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}})

                if screenshot_b64:
                    user_content.append({"type": "image_url", "image_url": {"url": screenshot_b64}})

            messages = [
                {"role": "system", "content": system_instructions},
                {"role": "user", "content": user_content}
            ]

            # (5) 用 thread pool + queue 執行 sync streaming
            # sync stream=True 讓 Cloudflare 看到資料流動（避免 524）
            # thread pool 讓 event loop 不被阻塞
            logger.info(f"[{model}] 開始呼叫模型 {model_name} (sync streaming via thread)...")
            start_ts = time.time()
            generated_text = ""
            reasoning_text = ""
            loop = asyncio.get_running_loop()
            queue: asyncio.Queue = asyncio.Queue()

            def _produce():
                try:
                    with sync_client.chat.completions.create(
                        model=model_name, messages=messages, stream=True
                    ) as resp:
                        for _chunk in resp:
                            _delta = _chunk.choices[0].delta if _chunk.choices else None
                            if _delta and _delta.content:
                                loop.call_soon_threadsafe(queue.put_nowait, ("chunk", _delta.content))
                            if _delta and hasattr(_delta, "reasoning_content") and _delta.reasoning_content:
                                loop.call_soon_threadsafe(queue.put_nowait, ("reasoning", _delta.reasoning_content))
                except Exception as _e:
                    loop.call_soon_threadsafe(queue.put_nowait, ("error", str(_e)))
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, ("done", None))

            loop.run_in_executor(None, _produce)

            while True:
                _kind, _payload = await queue.get()
                if _kind == "chunk":
                    generated_text += _payload
                    yield ("chunk", _payload)
                elif _kind == "reasoning":
                    reasoning_text += _payload
                elif _kind == "error":
                    raise Exception(_payload)
                elif _kind == "done":
                    break
            end_ts = time.time()

            # (6) 收完後寫 log
            if reasoning_text and generation_id:
                ai_log.write_section(generation_id, f"[{model}] Model Reasoning", reasoning_text)
            if generation_id:
                ai_log.write_section(generation_id, f"[{model}] Model Response (Content)", generated_text)
                ai_log.write_timing(generation_id, f"[{model}] LLM Call", start_ts, end_ts)

        # ==========================================
        # 3. 統一清理與回傳最終結果
        # ==========================================
        yield ("done", generated_text.replace("```html", "").replace("```", "").strip())

    @router.post("/generate_with_ai_stream", summary="使用 AI 生成頁面（SSE 串流進度）", tags=["trigger page"])
    async def generate_page_with_ai_stream(
        request: Request,
        prompt: str = Form(..., description="使用者的提示詞"),
        refUrl: str = Form(None, description="參考網址 (可選)"),
        image: UploadFile = File(None, description="參考圖片 (可選)"),
        pageType: str = Form("field", description="網頁類型: 'field' 欄位觸發 | 'download' 下載按鍵觸發"),
        aiModel: str = Form("gemini", description="AI 模型選擇"),
        useDesign: bool = Form(False, description="是否啟用 DESIGN.md 分析"),
        pageSpec: str = Form(None, description="結構化頁面規格 (可選)"),
        pageValue: str | None = Depends(validate_optional_page_value),
        current_user: dict = Depends(get_current_user)
    ):
        if image:
            await _validate_reference_image(image)
        structured_spec = _parse_page_spec(pageSpec, allow_custom=True) if pageSpec else None
        if structured_spec and (refUrl or useDesign):
            raise HTTPException(status_code=422, detail="AI 指定生成不支援參考網址或 DESIGN.md")
        if structured_spec and pageValue and await _page_value_exists(pageValue):
            raise HTTPException(status_code=409, detail=f"網址 ID '{pageValue}' 已存在")
        generation_id = ai_log.new_generation_id()
        ai_log.write_header(generation_id, {
            "user_uuid": current_user.get("acct_uuid"),
            "model": aiModel,
            "page_type": pageType,
            "use_design": useDesign,
            "ref_url": refUrl or "",
            "has_image": bool(image),
        })
        base_system_prompt = (
            build_structured_ai_instructions(structured_spec, prompt)
            if structured_spec
            else get_system_prompt(pageType)
        )
        ai_log.write_section(generation_id, "System Prompt", base_system_prompt)
        ai_log.write_section(generation_id, "User Prompt", prompt)
        if refUrl:
            ai_log.write_section(generation_id, "Reference URL", refUrl)
        llm_caller = getattr(request.app.state, "trigger_page_llm_caller", call_llm)

        async def event_generator():
            def sse_event(event_type: str, data: dict) -> str:
                return f"data: {json.dumps({'type': event_type, 'data': data})}\n\n"

            design_context = {}
            try:
                # 階段 1：設計解析
                if refUrl and useDesign:
                    yield sse_event("progress", {"stage": "extracting", "message": "正在解析目標網站設計風格..."})

                    try:
                        design_context = await get_design_context(refUrl)
                    except Exception as e:
                        logger.error(f"提取設計解析失敗: {e}")
                        ai_log.write_section(generation_id, "Design Context (useDesign) Error", str(e))
                        design_context = {}

                    # [重要] 先寫 log 再 yield SSE，避免前端中斷（AbortController）時
                    # CancelledError 跳出導致 cache hit / extracted 的內容沒被記錄
                    if design_context.get("design_md"):
                        ai_log.write_section(
                            generation_id,
                            "Design Context (useDesign)",
                            f"source: {design_context.get('source')}\n\n{design_context['design_md']}"
                        )

                    source = design_context.get("source")
                    yield sse_event("progress", {
                        "stage": "extracted",
                        "message": "設計解析完成" if source and source != "fallback" else "設計解析失敗，改用預設規範",
                        "source": source or "fallback"
                    })

                # 階段 2：LLM 生成
                yield sse_event("progress", {"stage": "generating", "message": "正在使用 AI 生成網頁程式碼..."})

                system_instructions = base_system_prompt
                if refUrl and design_context.get("design_md"):
                    system_instructions += f"\n\n<design_system>\n{design_context['design_md']}\n</design_system>"
                    system_instructions += "\n\n[嚴格要求] 你必須完全遵守上方 <design_system> 中的設計規範來撰寫HTML/CSS。"

                if structured_spec:
                    char_count = 0
                    last_emitted = 0

                    async def stream_factory(attempt):
                        nonlocal char_count, last_emitted
                        char_count = 0
                        last_emitted = 0
                        if image:
                            await image.seek(0)
                        ai_log.write_section(
                            generation_id,
                            f"Structured Generation Attempt {attempt}",
                            f"attempt: {attempt}/3",
                        )
                        return llm_caller(
                            model=aiModel,
                            system_instructions=system_instructions,
                            user_prompt="請嚴格依照結構契約完成頁面外觀。",
                            ref_url=None,
                            image=image,
                            screenshot_b64=None,
                            generation_id=generation_id,
                        )

                    def validate_generated_html(generated_html):
                        try:
                            completed = enrich_custom_patterns(generated_html, structured_spec)
                            completed = validate_page_spec(completed)
                            validate_structured_html(generated_html, completed, expected_revision=1)
                            return completed
                        except HTTPException as exc:
                            raise StructuredOutputValidationError(str(exc.detail)) from exc

                    html_content = ""
                    completed_spec = None
                    async for retry_kind, retry_payload in stream_structured_generation_with_retries(
                        stream_factory,
                        validate_generated_html,
                        max_attempts=3,
                    ):
                        if retry_kind == "attempt":
                            yield sse_event("progress", {
                                "stage": "generating",
                                "attempt": retry_payload["attempt"],
                                "max_attempts": retry_payload["max_attempts"],
                                "message": f"正在進行生成...(第{retry_payload['attempt']}次嘗試)",
                            })
                        elif retry_kind == "chunk":
                            char_count += len(retry_payload)
                            if char_count - last_emitted >= 200:
                                yield sse_event("progress", {
                                    "stage": "generating",
                                    "message": f"已生成 {char_count} 字元...",
                                })
                                last_emitted = char_count
                        elif retry_kind == "validation_error":
                            ai_log.write_section(
                                generation_id,
                                f"Structured Validation Failed (Attempt {retry_payload['attempt']})",
                                retry_payload["message"],
                            )
                            yield sse_event("progress", {
                                "stage": "retrying" if retry_payload["will_retry"] else "validating",
                                **retry_payload,
                                "message": (
                                    f"第 {retry_payload['attempt']} 次結果未通過結構驗證，正在自動重試..."
                                    if retry_payload["will_retry"]
                                    else f"第 {retry_payload['max_attempts']} 次結果仍未通過結構驗證"
                                ),
                            })
                        elif retry_kind == "done":
                            html_content = retry_payload["html"]
                            completed_spec = retry_payload["page_spec"]
                else:
                    html_content = ""
                    char_count = 0
                    last_emitted = 0
                    async for kind, payload in llm_caller(
                        model=aiModel,
                        system_instructions=system_instructions,
                        user_prompt=prompt,
                        ref_url=refUrl,
                        image=image,
                        screenshot_b64=design_context.get("screenshot_b64") if refUrl else None,
                        generation_id=generation_id,
                    ):
                        if kind == "chunk":
                            char_count += len(payload)
                            if char_count - last_emitted >= 200:
                                yield sse_event("progress", {
                                    "stage": "generating",
                                    "message": f"已生成 {char_count} 字元...",
                                })
                                last_emitted = char_count
                        elif kind == "done":
                            html_content = payload
                    completed_spec = None

                # 階段 3：完成
                complete_data = {
                    "stage": "done",
                    "message": "生成完成！",
                    "html": html_content,
                    "generation_id": generation_id,
                }
                if completed_spec:
                    complete_data["pageSpec"] = completed_spec
                    complete_data["specRevision"] = 1
                yield sse_event("complete", complete_data)

            except Exception as e:
                logger.error(f"生成流程失敗: {e}")
                ai_log.write_section(generation_id, "Errors", str(e))
                yield sse_event("error", {"stage": "error", "message": f"處理失敗: {str(e)}"})
            finally:
                if image:
                    await image.close()

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    return router

def get_system_prompt(page_type: str = "field"):
    """
    依據網頁類型產生對應的 System Prompt。
    page_type: 'field' 欄位觸發 | 'download' 下載按鍵觸發
    """

    # 共用：背景說明與仿真設計
    common_intro = """
        [Context]
        你是一位專業的前端工程師，協助製作網頁前端畫面。

        使用者會給你一個描述 (e.g. "Facebook 登入頁面" 或 "Dropbox 下載頁面")，你需要生成一個單一的 HTML 檔案。

        [重點功能]
        1. 若指定特定知名服務：
        - 必須精確還原該品牌 **真實頁面** 的視覺風格（包含官方配色、排版、按鈕與輸入框樣式）。
        - 參考其佈局結構 (例如：左右分割、置中卡片、背景圖風格)。
        - 若需要 Logo，請使用可靠的開源 CDN (如 FontAwesome)，確保視覺逼真，若無開源 CDN，請使用 inline SVG 繪製。
        2. **必須是響應式設計 (RWD)**：務必在 `<head>` 加入 `<meta name="viewport" content="width=device-width, initial-scale=1.0">`，確保在手機端顯示正常。
    """

    # 根據觸發模式的特殊規則
    if page_type == "download":
        trigger_instructions = """
        [觸發模式：下載按鍵點擊]
        1. **下載按鍵設定**：
        - 頁面上所有會觸發記錄的**主要按鈕/連結**，必須加上屬性 `data-role="download-trigger"`。
        - 例如：`<button type="button" data-role="download-trigger">下載檔案</button>` 或 `<a href="#" data-role="download-trigger">點此下載</a>`
        - 這個屬性會被我們的 JS 自動監聽，**不需要寫任何登入表單 (<form>)**。
        """
    else:
        trigger_instructions = """
        [觸發模式：表單欄位填入]
        1. **表單與輸入欄位設定**：
        - **必須**使用 `<form id="login-form">` 包裝所有的輸入欄位和提交按鈕。
        - 所有的 `<input>` 標籤，如果是用來讓使用者輸入資料的 (如 Email, 帳號, 密碼)，**必須**加上屬性 `data-role="login-input"`。
        - 例如：`<input type="email" name="email" id="email-input" data-role="login-input" required>`
        - 請確保有對應的 `<button type="submit">` 送出按鈕。
        """

    # 共用：絕對必須遵守的技術限制與輸出格式
    common_outro = """
        [必要的技術限制 - 絕對必須遵守]
        1. **追蹤腳本注入**：必須包含以下 Script 區塊，且嚴格放置在 `</body>` 標籤的上一行：
        <script>
            const API_BASE_PATH = "{{ api_base_path }}";
        </script>
        <script src="{{ url_for('static', path='js/recordingLogin.js') }}"></script>
        (注意：請絕對保留 Jinja2 模板語法 {{ ... }}，不可更改或解析它們)

        2. **樣式 (CSS)**：請將所有 CSS 樣式直接寫在 `<style>` 標籤內 (Internal CSS)，不可引入外部自訂 CSS 檔案。

        3. **編碼與標題**：
        - `<head>` 內必須包含 `<meta charset="UTF-8">`。
        - `<head>` 內必須包含標準的 `<title>登入</title>`。

        4. **預留 Logo 容器**：
        - 遇到需要繪製或放置品牌 Logo，請務必將其包裝在`<div id="custom-brand-logo"></div>`的容器中，以利系統後續安全替換與修改。

        5. **預留頁面主標題容器**：
        - 頁面的主要標題，請務必將其包裝在一個具有 ID 的標籤中，例如 `<h1 id="custom-main-title">網頁標題</h1>`。

        [輸出格式要求]
        - 請「只」回傳純 HTML 程式碼。
        - 絕對不要包含任何解釋性文字。
        - 絕對不要使用 Markdown 代碼區塊 (不要輸出 ```html 和 ```)，直接輸出 <!DOCTYPE html> 開頭的程式碼。
    """

    return f"{common_intro}\n{trigger_instructions}\n{common_outro}"

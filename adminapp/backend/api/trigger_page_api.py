'''
處理trigger網頁
'''
import json
import os
import shutil
import re
from pathlib import Path
from fastapi import (
    APIRouter, 
    Depends, 
    Form, 
    UploadFile, 
    File, 
    HTTPException, 
    status
)
from fastapi.responses import JSONResponse

from backend.services.log_manager import Logger


logger = Logger().get_logger()

# --- 路徑設定 ---

# 容器內的程式根目錄
BASE_DIR = Path("/app")

# JSON 設定檔的路徑
DATA_DIR = BASE_DIR / "backend" / "static"
JSON_FILE_PATH = DATA_DIR / "pageOptions.json"

# 檔案上傳的目的地 (對應到 loginapp/templates)
UPLOAD_DIR = BASE_DIR / "uploads_for_trigger_app_templates" 

# 應用啟動時，確保資料夾存在
DATA_DIR.mkdir(parents=True, exist_ok=True)
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
            detail="「網頁值 (value)」只能包含小寫字母、數字和底線。"
        )
    return pageValue

def get_page_data():
    """輔助函式：讀取 JSON 資料"""
    if not JSON_FILE_PATH.exists():
        return []
    try:
        with JSON_FILE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, list):
                return []
            return data
    except json.JSONDecodeError:
        return []

def save_page_data(data: list):
    """輔助函式：寫回 JSON 資料"""
    try:
        with JSON_FILE_PATH.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"寫入 JSON 失敗: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"寫入 JSON 檔案失敗: {str(e)}"
        )

# --- 3. API 端點 ---

def get_router():

    router = APIRouter()

    @router.get(
        "/get",
        summary="獲取所有頁面選項",
        tags=["trigger page"]
    )
    async def get_page_options():
        """
        讀取 pageOptions.json 並將其作為 API 回傳。
        """
        data = get_page_data()
        return JSONResponse(content=data)

    @router.post(
        "/upload", 
        summary="上傳新頁面模板",
        tags=["trigger page"]
    )
    async def upload_new_page(
        # Form(...) 用於接收 multipart/form-data 的文字欄位
        pageLabel: str = Form(..., description="顯示在選項中的名稱 (e.g., '我的新頁面')"),
        pageValue: str = Depends(validate_page_value), # 使用 Depends 來驗證
        file: UploadFile = File(..., description="要上傳的 HTML 模板檔案")
    ):
        """
        此 API 執行兩個任務:
        1. 將上傳的檔案儲存到 loginapp 的 templates 資料夾。
        2. 將新頁面的資訊 (value, label) 新增到 pageOptions.json。
        """
        
        # --- 任務 1: 將上傳的頁面新增到資料夾裡 ---
        
        new_filename = f"{pageValue}.html"
        save_path = UPLOAD_DIR / new_filename

        # 檢查檔案是否已存在
        if save_path.exists():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"檔案 '{new_filename}' 已存在於 templates 資料夾中。"
            )

        try:
            # 儲存上傳的檔案
            with save_path.open("wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"儲存檔案失敗: {str(e)}"
            )
        finally:
            await file.close()

        # --- 任務 2: 將資料新增到 json 檔裡 ---
        
        data = []
        try:
            # 讀取現有的 JSON 檔案 (如果存在)
            if JSON_FILE_PATH.exists():
                with JSON_FILE_PATH.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    if not isinstance(data, list):
                        data = [] # 如果格式不對，重設為空列表
            
            # 再次檢查 value 是否在 JSON 中重複
            if any(item.get("value") == pageValue for item in data):
                # [復原] 如果 JSON 重複，刪除剛剛上傳的檔案
                save_path.unlink() 
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"「網頁值 (value)」 '{pageValue}' 已存在於 pageOptions.json 中。"
                )

            # 新增資料
            new_entry = {"value": pageValue, "label": pageLabel}
            data.append(new_entry)

            # 寫回 JSON 檔案
            with JSON_FILE_PATH.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            # [復原] 如果 JSON 操作失敗，也要刪除剛剛上傳的檔案
            if save_path.exists():
                save_path.unlink()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"更新 JSON 檔案失敗: {str(e)}"
            )

        return {
            "status": "success",
            "message": f"頁面 '{pageLabel}' 已成功上傳。",
            "new_entry": new_entry
        }

    # (Update) 修改頁面模板
    @router.post(
        "/update",
        summary="修改現有頁面模板"
    )
    async def update_page(
        pageLabel: str = Form(..., description="新的Label"),
        pageValue: str = Depends(validate_page_value),
        oldPageValue: str = Form(..., description="要修改的目標 value"),
        file: UploadFile = File(None, description="上傳新的 HTML 檔案來覆蓋")
    ):
        
        data = get_page_data()
        
        # --- 任務 1: 覆蓋檔案 ---
        # 定義新舊檔案路徑
        old_filename = f"{oldPageValue}.html"
        old_file_path = UPLOAD_DIR / old_filename
        
        new_filename = f"{pageValue}.html"
        new_file_path = UPLOAD_DIR / new_filename
        
        is_value_changing = (pageValue != oldPageValue)

        # 檢查：如果要改 value，但新 value 已經在 JSON 中存在 (且不是自己)
        if is_value_changing:
            if any(item.get("value") == pageValue for item in data):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"新的網頁值 '{pageValue}' 已經存在於另一個項目中。"
                )

        try:
            if file:
                # 覆蓋儲存
                with new_file_path.open("wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                
                # 如果 value 也變了，且舊檔案存在，就把舊檔案刪除
                if is_value_changing and old_file_path.exists():
                    old_file_path.unlink()
            else:
                # 情況 2: 使用者沒有上傳新檔案
                # 只有在 value 改變時，才需要重命名
                if is_value_changing:
                    # 檢查：舊檔案是否存在
                    if not old_file_path.exists():
                        logger.warning(f"找不到舊檔案 {old_filename}，但仍會更新 JSON。")
                        # 檔案不存在，但我們還是可以繼續更新 JSON，所以不用 raise error
                    
                    # 檢查：新檔名是否已存在 (避免衝突)
                    elif new_file_path.exists():
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail=f"無法重命名：檔案 '{new_filename}' 已存在。"
                        )
                    
                    # 重命名
                    else:
                        old_file_path.rename(new_file_path)

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"處理檔案時失敗: {str(e)}"
            )
        finally:
            if file:
                await file.close()
            

        # --- 任務 2: 更新 JSON ---
        
        item_found = False
        for item in data:
            if item.get("value") == oldPageValue:
                item["label"] = pageLabel 
                item["value"] = pageValue
                item_found = True
                break
        
        if not item_found:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"找不到 value 為 '{pageValue}' 的項目。"
            )
        
        save_page_data(data) # 寫回 JSON

        return {
            "status": "success",
            "message": f"頁面 '{pageLabel}' 已成功更新。"
        }    

    # (Delete) 刪除頁面模板
    @router.post(
        "/delete",
        summary="刪除現有頁面模板"
    )
    async def delete_page(
        pageValue: str = Form(..., description="要刪除的目標 value")
    ):
        
        # --- 任務 1: 刪除 JSON 條目 ---
        data = get_page_data()
        
        original_length = len(data)
        data = [item for item in data if item.get("value") != pageValue]
        
        if len(data) == original_length:
            logger.warning(f"試圖刪除不存在的 JSON 條目: {pageValue}")
            # 注意：即使 JSON 找不到，我們仍然嘗試刪除檔案

        save_page_data(data) # 寫回 JSON

        # --- 任務 2: 刪除檔案 ---
        filename = f"{pageValue}.html"
        save_path = UPLOAD_DIR / filename
        
        if save_path.exists():
            try:
                save_path.unlink()
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"刪除檔案 '{filename}' 失敗: {str(e)}"
                )
        else:
            logger.warning(f"試圖刪除不存在的檔案: {filename}")
            # 即使檔案不存在，也回傳成功 (因為目的已達到)

        return {
            "status": "success",
            "message": f"頁面 (value: {pageValue}) 已成功刪除。"
        }

    return router

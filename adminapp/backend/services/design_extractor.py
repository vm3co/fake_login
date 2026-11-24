import base64
import json
from urllib.parse import urlparse
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from backend.services.log_manager import Logger

logger = Logger().get_logger()

# 注入頁面，提取 Design Tokens 的 JavaScript
EXTRACT_SCRIPT = """
() => {
    function getStyles(element) {
        if (!element) return null;
        const style = window.getComputedStyle(element);
        return {
            backgroundColor: style.backgroundColor,
            color: style.color,
            fontFamily: style.fontFamily,
            borderRadius: style.borderRadius,
            boxShadow: style.boxShadow,
            padding: style.padding,
            borderWidth: style.borderWidth,
            borderColor: style.borderColor,
            fontWeight: style.fontWeight,
            fontSize: style.fontSize
        };
    }

    const bodyStyle = getStyles(document.body) || {};
    
    // 試圖找到主要按鈕
    const buttonElement = document.querySelector('button, [type="submit"], .btn, [role="button"]') || document.body;
    const btnStyle = getStyles(buttonElement) || {};

    // 試圖找到輸入框
    const inputElement = document.querySelector('input[type="text"], input[type="email"], input[type="password"]') || document.body;
    const inputStyle = getStyles(inputElement) || {};

    // 試圖找到卡片/主要容器
    const cardElement = document.querySelector('form, main, [role="main"], .card, .login-container') || document.body;
    const cardStyle = getStyles(cardElement) || {};

    // 試圖找到標題字體
    const headingElement = document.querySelector('h1, h2, h3') || document.body;
    const headingStyle = getStyles(headingElement) || {};

    return {
        typography: {
            font_family: bodyStyle.fontFamily || "sans-serif",
            heading_font: headingStyle.fontFamily || bodyStyle.fontFamily || "sans-serif"
        },
        colors: {
            background: bodyStyle.backgroundColor || "#ffffff",
            text_primary: bodyStyle.color || "#000000",
            primary_action: btnStyle.backgroundColor || "#000000",
            primary_action_text: btnStyle.color || "#ffffff",
            input_border: inputStyle.borderColor || "#cccccc"
        },
        components: {
            button: {
                border_radius: btnStyle.borderRadius || "0px",
                box_shadow: btnStyle.boxShadow || "none",
                padding: btnStyle.padding || "0px",
                font_weight: btnStyle.fontWeight || "normal",
                font_size: btnStyle.fontSize || "medium"
            },
            input: {
                border_radius: inputStyle.borderRadius || "0px",
                border_width: inputStyle.borderWidth || "0px",
                padding: inputStyle.padding || "0px",
                font_size: inputStyle.fontSize || "medium"
            },
            card: {
                border_radius: cardStyle.borderRadius || "0px",
                box_shadow: cardStyle.boxShadow || "none"
            }
        }
    };
}
"""

async def extract_design_tokens(url: str) -> dict | None:
    """
    啟動 headless Chromium，前往 URL，提取設計 tokens 並截圖。
    回傳字典或 None (失敗)
    """
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    parsed_url = urlparse(url)
    domain = parsed_url.netloc

    logger.info(f"開始提取設計: {url}")

    try:
        async with async_playwright() as p:
            # 啟動 Chromium
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            try:
                # 前往頁面，等待 networkidle 以確保框架渲染完成
                await page.goto(url, wait_until="networkidle", timeout=15000)
                # 額外等待一下，確保動畫等結束
                await page.wait_for_timeout(2000)
            except PlaywrightTimeoutError:
                logger.warning(f"頁面載入超時，嘗試取當前狀態: {url}")
            
            # 注入腳本取得 styles
            tokens = await page.evaluate(EXTRACT_SCRIPT)
            
            # 截取可視區域
            screenshot_bytes = await page.screenshot(full_page=False, type='png')
            screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            
            await browser.close()
            
            return {
                "url": url,
                "domain": domain,
                **tokens,
                "screenshot_base64": f"data:image/png;base64,{screenshot_base64}"
            }
    except Exception as e:
        logger.error(f"提取設計失敗 ({url}): {e}")
        return None

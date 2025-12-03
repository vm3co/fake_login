import os
import httpx
from backend.services.log_manager import Logger

logger = Logger().get_logger()

# 從環境變數讀取 Telegram Bot Token 和 Chat ID
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def escape_markdown_v2(text: str) -> str:
    """
    對 Telegram MarkdownV2 的特殊字元進行跳脫。
    """
    if not isinstance(text, str):
        return ""
    
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return "".join(f'\\{char}' if char in escape_chars else char for char in text)

async def send_telegram_notification(message: str):
    """
    以非同步方式發送 Telegram 通知。
    如果未設定 BOT_TOKEN 或 CHAT_ID，則會記錄警告並直接返回。
    
    :param message: 要發送的訊息內容 (不需要手動跳脫)
    """
    if not BOT_TOKEN or not CHAT_ID:
        logger.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set. Skipping notification.")
        return

    # Telegram Bot API 的端點
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    # 我們使用了 'parse_mode': 'MarkdownV2' 來讓訊息格式更豐富
    # 這裡會自動跳脫特殊字元
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "MarkdownV2"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, data=payload, timeout=10.0)
        
        if response.status_code == 200:
            logger.info("Telegram notification sent successfully.")
        else:
            logger.error(f"Failed to send Telegram notification. Status: {response.status_code}, Response: {response.text}")
            
    except httpx.RequestError as e:
        logger.error(f"An error occurred while sending Telegram notification: {e}")

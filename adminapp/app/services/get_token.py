import httpx
from datetime import datetime
import re

from app.services.log_manager import Logger
import os


logger = Logger().get_logger()

class getToken:
    """
    用於刷新 token 的類別
    """
    def __init__(self):
        self.cookie_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'certs', 'cookie.txt'))  # cookie.txt 的路徑
        verify_name = 'se.acsicook.info.crt'
        self.verify = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'certs', verify_name))

    def get(self) -> str:
        """
        獲取 token 的方法
        :return: 包含 type1、type2、type3 的 cookie 字串
        """
        if not os.path.exists(self.cookie_path):
            logger.error(f"Cookie file not found at {self.cookie_path}")
            return ""
        
        try:
            with open(self.cookie_path, 'r', encoding='utf-8') as f:
                cookie = f.read().strip()
            return cookie
        except Exception as e:
            logger.error(f"Error getting token: {e}")
            return ""

    def get_cookie(self, word: str) -> str:
        '''
        獲取cookie
        :param word: 包含 cookie 的字串
        :return: 包含 type1、type2、type3 的 cookie 字串
        '''
        # 用 regex 擷取 type1、type2、type3 的 cookie 值
        pattern = r'(type[123])=([^;]+)'
        matches = re.findall(pattern, word)
        
        result = ""
        for k, v in matches:
            word = k + "=" + v + "; "
            result += word
            
        return result


    async def refresh(self):
        """ 
        刷新 token 的方法
        """
        logger.info("Refreshing token...")
        # 獲取當前的 cookie
        cookie = self.get()
        if cookie:
            # POST 請求 headers
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
                "Referer": "https://se.acsicook.info/",
                "Origin": "https://se.acsicook.info",
                "Accept": "application/json, text/plain, */*",
                "cookie": cookie
            }

            # API URL
            url = 'https://se.acsicook.info/api/account/refresh_token'

            # 發送 GET 請求
            async with httpx.AsyncClient(verify=self.verify) as client:
                response = await client.post(url, headers=headers, timeout=60, json={})
                set_cookie = response.headers.get('set-cookie')
                result = self.get_cookie(set_cookie) if set_cookie else ""
                if not result:
                    logger.error("Failed to refresh token, no cookie found in response.")
                    return
            # 儲存 headers 到檔案
            with open(self.cookie_path, 'w', encoding='utf-8') as f:
                f.write(result)

            logger.info(f"Token refreshed and saved.")

get_token = getToken()

import httpx
from datetime import datetime
import re

from backend.services.log_manager import Logger
import os


logger = Logger().get_logger()

class getToken:
    """
    用於刷新 token 的類別
    """
    def __init__(self):
        # self.url = "https://se.acsicook.info"
        self.url = os.getenv("SE_URL", "https://se.acsicook.info")
        self.cookie_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'certs', 'cookie.txt'))  # cookie.txt 的路徑
        # verify_name = 'se.acsicook.info.crt'
        verify_name = os.getenv("VERIFY_NAME", "se.acsicook.info.crt")
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
        # logger.info("Refreshing token...")
        # 獲取當前的 cookie
        cookie = self.get()
        if cookie:
            # POST 請求 headers
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
                "Referer": self.url + "/",
                "Origin": self.url,
                "Accept": "application/json, text/plain, */*",
                "cookie": cookie
            }

            # API URL
            url = self.url + '/api/account/refresh_token'

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

            # logger.info(f"Token refreshed and saved.")

    async def get_csrftoken(self) -> tuple[str, str]:
        """
        呼叫 API 以取得 CSRF Token
        回傳 (csrf_token, x_csrf_token)，失敗回傳 (None, None)
        """
        cookie = self.get()
        if cookie:
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
                "Referer": self.url + "/",
                "Origin": self.url,
                "Accept": "application/json, text/plain, */*",
                "cookie": cookie
            }
            url = self.url + '/api/csrftoken/get_csrftoken'
            try:
                async with httpx.AsyncClient(verify=self.verify) as client:
                    response = await client.post(url, headers=headers, timeout=60, json={})
                    response.raise_for_status()
                    
                    data = response.json()
                    x_csrf_token = data.get("data") if data else None
                    csrf_token = response.cookies.get('csrf-token')

                    if csrf_token:
                        return csrf_token, x_csrf_token
                    else:
                        logger.error("API 回應中未包含 'csrf-token' Cookie。")
                        return None, None
            except Exception as e:
                logger.error(f"取得 CSRF Token 時發生錯誤: {e}")
                return None, None
        return None, None

get_token = getToken()

if __name__ == "__main__":
    get_token.refresh()
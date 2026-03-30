import os
import httpx
import json
import time
import math
import logging

from backend.services.get_token import get_token
from backend.services.log_manager import Logger

logger = Logger().get_logger()

class SeTaskService:
    def __init__(self):
        self.url = os.getenv("SE_URL", "https://se.acsicook.info")
        verify_name = os.getenv("VERIFY_NAME", "se.acsicook.info.crt")
        self.verify = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'certs', verify_name))
    
    async def _send_post_async(
        self, 
        url: str, 
        payload: dict, 
        extra_headers: dict = None, 
        is_token_refreshed: bool = False
    ) -> dict | None:
        """非同步發送 POST 請求"""
        cookie = get_token.get()
        if not cookie:
            logger.error("無法取得身份驗證 Cookie")
            return None

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": self.url,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/135.0.0.0 Safari/537.36",
            "Referer": self.url + '/main/sendtask/list?lyt=v',
            "cookie": cookie
        }
        
        if extra_headers:
            headers.update(extra_headers)

        try:
            async with httpx.AsyncClient(verify=self.verify, timeout=60.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                return response.json()
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code in [401, 403] and not is_token_refreshed:
                logger.info("Token expired, refreshing token and retrying...")
                await get_token.refresh()
                return await self._send_post_async(url, payload, extra_headers, is_token_refreshed=True)
            else:
                try:
                    err = e.response.json()
                except Exception:
                    err = e.response.text
                logger.error(f"HTTP exception: {err}")
                return None
        except Exception as e:
            logger.error(f"Unhandled exception: {str(e)}")
            return None

    def _secure_random(self) -> float:
        random_bytes = os.urandom(4)
        random_int = int.from_bytes(random_bytes, 'big')
        return random_int / (0xFFFFFFFF + 1)

    def get_uuid(self) -> str:
        _format = 'xxxxxxxxxxxx4xxxyxxxxxxxxxxxxxxx'
        d = (time.time() * 1000) + (time.perf_counter() * 1000)
        
        uuid_chars = []
        for char in _format:
            if char in ['x', 'y']:
                r = math.floor((d + self._secure_random() * 16) % 16)
                d = math.floor(d / 16)
                val = r if char == 'x' else (r & 0x3 | 0x8)
                uuid_chars.append(format(val, 'x'))
            else:
                uuid_chars.append(char)
                
        return "".join(uuid_chars)

    async def create_testcase(
        self, 
        id: str, 
        unit: str,
        pre_test_enable: bool, 
        mail_template: list,
        test_start: int,
        test_end: int,
        send_end: int,
        participant_count: int,
        participant_data: str = None
    ) -> str | None:
        '''建立專案'''
        uuid = self.get_uuid()
        csrf_token, x_csrf_token = await get_token.get_csrftoken()
        if not csrf_token or not x_csrf_token:
            logger.error("取得 CSRF Token 失敗，無法建立專案")
            return None

        cookie_with_csrf = get_token.get() + f"; csrf-token={csrf_token}"

        x_headers = {
            'X-Csrf-Token': x_csrf_token,
            'cookie': cookie_with_csrf
        }

        url = self.url + '/api/case/create_testcase'
        
        if pre_test_enable:
            pre_test_start_ut, pre_test_end_ut, pre_send_end_ut = test_start, test_end, send_end
            pre_test_person_count = participant_count
            test_start_ut, test_end_ut, send_end_ut, test_person_count = None, None, None, None
            query_type = "0"
        else:
            pre_test_start_ut, pre_test_end_ut, pre_send_end_ut = None, None, None
            pre_test_person_count = None
            test_start_ut, test_end_ut, send_end_ut = test_start, test_end, send_end
            test_person_count = participant_count
            query_type = "1"

        payload = {
            "uuid": uuid,
            "id": id,
            "unit": unit,
            "pre_test_enable": pre_test_enable,
            "mail_server": [{"uuid": "4cfc6247a5a24f9099ce73e5307e8984"}],
            "mail_speed": "1",
            "mail_logic": "99",
            "mail_logging": "1",
            "mail_template": mail_template,
            "mail_delivery": [],
            "mail_delivery_d": [],
            "content": "%3Cp%3E%E7%84%A1%E5%85%A7%E5%AE%B9%3C%2Fp%3E",
            "click_action": 1,
            "pre_test_start_ut": pre_test_start_ut,
            "pre_test_end_ut": pre_test_end_ut,
            "pre_send_end_ut": pre_send_end_ut,
            "pre_test_person_count": pre_test_person_count,
            "test_start_ut": test_start_ut,
            "test_end_ut": test_end_ut,
            "send_end_ut": send_end_ut,
            "test_person_count": test_person_count,
            "adv_mail_delivery": False,
            "adv_mail_delivery_val": []
        }
        
        data = await self._send_post_async(url, payload, extra_headers=x_headers)
        
        if data:
            logger.info(f"建立專案成功, uuid={uuid}")
            # 建立測試人員並儲存
            await self._update_test_participant(
                data=participant_data, 
                uuid=uuid, 
                testcase_payload=payload, 
                query_type=query_type
            )
            return uuid
        return None

    async def _update_test_participant(
        self, 
        data: str = None, 
        uuid: str = None, 
        testcase_payload: dict = {}, 
        query_type: str = "0"
    ) -> None:
        '''上傳測試人資料字串並儲存任務'''
        csrf_token, x_csrf_token = await get_token.get_csrftoken()
        if not csrf_token or not x_csrf_token:
            logger.error("取得 CSRF Token 失敗，無法建立測試人")
            return None

        cookie_with_csrf = get_token.get() + f"; csrf-token={csrf_token}"

        request_headers = {
            'X-Csrf-Token': x_csrf_token,
            'cookie': cookie_with_csrf
        }
        
        url = self.url + '/api/case/update_test_participant'
        payload = {
            "data": data,
            "uuid": uuid,
            "query_type": query_type
        }

        resp_data = await self._send_post_async(url, payload, extra_headers=request_headers)
        if resp_data:
            logger.info(f"測試人建立成功: {resp_data}")
            # 儲存專案
            await self._save_testcase(testcase_payload)

    async def _save_testcase(self, payload: dict) -> dict | None:
        '''儲存任務'''
        url = self.url + '/api/case/update_testcase'
        return await self._send_post_async(url, payload)

    async def create_sendtask(self, testcase_uuid: str, server_url: str = "https://link.acsicook.info/", to_scheduler: bool = False) -> bool:
        '''啟動專案(建立任務)'''
        logger.info(f"建立任務： {testcase_uuid}")
        url = self.url + '/api/case/create_sendtask'
        payload = {
            "testcase_uuid": testcase_uuid,
            "server_url": server_url,
            "to_scheduler": to_scheduler
        }
        data = await self._send_post_async(url, payload)
        if data:
            logger.info(f"建立任務成功 {testcase_uuid}")
            return True
        logger.error(f"建立任務失敗 {testcase_uuid}")
        return False

    async def delete_testcase(self, testcase_uuid: str) -> bool:
        '''刪除專案'''
        logger.info(f"刪除專案： {testcase_uuid}")
        csrf_token, x_csrf_token = await get_token.get_csrftoken()
        if not csrf_token or not x_csrf_token:
            return False

        cookie_with_csrf = get_token.get() + f"; csrf-token={csrf_token}"
        x_headers = {
            'X-Csrf-Token': x_csrf_token,
            'cookie': cookie_with_csrf
        }
        
        url = self.url + '/api/case/delete_testcase'
        payload = {"testcase_uuid": testcase_uuid}
        
        data = await self._send_post_async(url, payload, extra_headers=x_headers)
        if data:
            logger.info(f"刪除專案成功 {testcase_uuid}")
            return True
        logger.error(f"刪除專案失敗 {testcase_uuid}")
        return False

    async def delete_sendtask(self, sendtasks_uuid: str) -> bool:
        '''刪除(停止)任務'''
        logger.info(f"刪除任務： {sendtasks_uuid}")
        url = self.url + '/api/case/delete_sendtask'
        payload = {"sendtask_uuid": sendtasks_uuid}
        
        data = await self._send_post_async(url, payload)
        if data:
            logger.info(f"刪除任務成功 {sendtasks_uuid}")
            return True
        logger.error(f"刪除任務失敗 {sendtasks_uuid}")
        return False

se_task_service = SeTaskService()

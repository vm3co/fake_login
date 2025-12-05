# -*- coding: utf-8 -*-
"""
Created on Thu May  8 14:32:44 2025

@author: 2501053

用api到se2系統抓取資料
"""
import os
import time
import requests
import json
import pandas as pd
import asyncio
import httpx
from rsa import verify

from backend.services.log_manager import Logger
from backend.services.get_token import get_token


logger = Logger().get_logger()

API_ENDPOINTS = {
    "get_sendtasks": "/api/case/get_sendtasks",
    "get_sendtask": "/api/case/get_sendtask",
    "get_sendlog": "/api/case/get_sendlog",
    "get_mtmpl_list": "/api/editor/get_mtmpl_subject_list",
    "get_acct": "/api/account/get_acct",
    "get_accts": "/api/account/get_accts",
    "export_csv": "/api/casexport/export_csv",
}

class getSe2data:
    def __init__(self):
        # 將 URL 和憑證路徑的讀取保留在初始化中
        self.url = os.getenv("SE_URL", "https://se.acsicook.info")
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": self.url,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
            "Referer": self.url + '/main/sendtask/list?lyt=v',
        }
        verify_name = os.getenv("VERIFY_NAME", "se.acsicook.info.crt")
        self.verify = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'certs', verify_name))

    def _get_headers(self) -> dict:
        """獲取包含最新 cookie 的 headers"""
        headers = self.headers.copy()
        headers["cookie"] = get_token.get()
        return headers

    async def _send_post(self, url: str, payload_template: dict, isTokenRefreshed=False) -> dict | None:
        '''發送 POST 請求'''
        async with httpx.AsyncClient(timeout=60.0, verify=self.verify) as client:
            try:
                response = await client.post(url, headers=self._get_headers(), json=payload_template)
                response.raise_for_status() # 如果 HTTP 回應的狀態碼不是 2xx（例如 400、401、500 等），就自動拋出一個錯誤
                data = response.json()
                return data
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    logger.warning(f"Resource not found (404): {url}")
                    return {"error": {"code": 404, "message": "Not Found"}}
                logger.error(f"HTTP error occurred: {exc}")
            except Exception as e:
                if not isTokenRefreshed:
                    # 嘗試重新從txt獲取 token 並重試
                    logger.info("Token expired, re-getting token and retrying...")
                    return await self._send_post(url, payload_template, isTokenRefreshed=True)
                logger.error(f"Unhandled exception: {e}")
            return None

    async def _handle_pagination(self, url: str, payload_template: dict) -> list:
        '''處理多頁面請求'''
        all_data = []
        page = 1        
        while True:
            await asyncio.sleep(0.1)  # 加一點延遲避免被擋
            payload = payload_template.copy()
            payload["page_sn"] = page
            # logger.info(f"Requesting page {page}...")
            # 發送 POST 請求
            data = await self._send_post(url, payload)
            if data is None:
                logger.warning("API return None, stopping further requests.")
                break
            page_data = data.get("data", [])
            if not page_data:
                break

            all_data.extend(page_data)
            
            if len(page_data) < payload["record_page"]:
                break

            page += 1
        # logger.info(f"Total items fetched: {len(all_data)}")
        return all_data

    async def _fetch_with_fallback(self, fetch_function, *args, **kwargs):
        """
        使用 'test' 類型嘗試獲取資料，如果失敗則用 'pretest' 重試。
        :param fetch_function: 要執行的獲取函式 (例如 _handle_pagination 或 _send_post)
        :param args: 傳遞給 fetch_function 的位置參數
        :param kwargs: 傳遞給 fetch_function 的關鍵字參數，其中 payload_template 應包含 sendlog_type
        """
        payload_template = kwargs.get('payload_template', {})
        payload_template['sendlog_type'] = 'test'
        
        all_data = await fetch_function(*args, **kwargs)
        if not all_data:
            payload_template['sendlog_type'] = 'pretest'
            all_data = await fetch_function(*args, **kwargs)
        return all_data

    async def get_sendtasks(self, end_time=None, start_time=None) -> pd.DataFrame | None:
        '''
        抓取執行中專案清單(帶入參數可以指定專案建立時間)(撇除前測任務)
        
        :return: DataFrame 包含 sendtask 資料
        '''
        # 要發送 POST 的目標網址
        logger.info("Fetching sendtasks...")
        url = self.url + API_ENDPOINTS["get_sendtasks"]
        payload_template = {
            "end_time": end_time,
            "filter_time_range": 99,
            "order_field": "CreateTime",
            "order_method": "desc",
            "page_sn": 1,
            "record_page": 20,
            "sendtask_keyword": "",
            "sendtask_prestart": "no",
            "start_time": start_time,
            "time_field": "CreateTime"
        }
        all_data = await self._handle_pagination(url, payload_template)
        if all_data:
            # 將資料轉換為 DataFrame        
            sendtasks_df = pd.DataFrame(all_data)
            return sendtasks_df
        return None   

    async def get_sendtask(self, uuid: str) -> dict | None:
        """
        抓取單一專案的完整詳細資訊 (包含 data 和 metadata)。
        :param uuid: 專案的 UUID
        :return: 包含 data 和 metadata 的完整字典，或在失敗時返回 None。
        """
        # 要發送 POST 的目標網址
        url = self.url + API_ENDPOINTS["get_sendtask"]
        payload_template = {
            "sendtask_uuid": uuid
        }
        data = await self._fetch_with_fallback(self._send_post, url=url, payload_template=payload_template)
        return data

    async def get_sendlog(self, uuid: str) -> pd.DataFrame | None:
        '''抓取專案參與人員清單'''
        # 要發送 POST 的目標網址
        # logger.info(f"Fetching sendlog for sendtask {uuid}...")
        url = self.url + API_ENDPOINTS["get_sendlog"]
        payload_template = {
                            "sendtask_uuid": uuid,
                            "record_page": 200,
                            "search_keyword": "",
                            "behavior_filter": 0,
                            "etime": None,
                            "order_method": "asc",
                            "page_sn": 1,
                            "search_order_by": "B",
                            "search_send_result": "ALL",
                            "stime": None
                        }
        all_data = await self._fetch_with_fallback(self._handle_pagination, url=url, payload_template=payload_template)
        return None if not all_data else pd.DataFrame(all_data)

    async def get_mtmpl_subject_list(self) -> pd.DataFrame | None:
        '''抓取郵件樣板'''
        # 要發送 POST 的目標網址
        logger.info("Fetching mtemplate subject list...")
        url = self.url + API_ENDPOINTS["get_mtmpl_list"]
        payload = {
            "just_query": 1
        }        
        data = await self._send_post(url, payload)
        return None if not data else pd.DataFrame(data['data'])

    async def get_acct_orgs(self, acct_uuid: str) -> pd.DataFrame | None:
        '''抓取個別帳號擁有的組織'''
        # 要發送 POST 的目標網址
        logger.info(f"Fetching organizations for account {acct_uuid}...")
        url = self.url + API_ENDPOINTS["get_acct"]
        payload = {"acct_uuid": acct_uuid}
        data = await self._send_post(url, payload)
        return None if not data else pd.DataFrame(data["data"]["orgs"])

    async def get_accts(self) -> pd.DataFrame | None:
        '''抓取帳號'''
        # 要發送 POST 的目標網址
        logger.info("Fetching accounts...")
        url = self.url + API_ENDPOINTS["get_accts"]
        # payload
        payload_template = {
            "acct_name":  "",
            "acct_stats": "enable",
            "end_time": None,
            "filter_time_range": 0,
            "order_field": "CreateTime",
            "order_method": "desc",
            "page_sn": 1,
            "record_page": 50,
            "start_time": None,
            "time_field": "UpdateTime",  
        }        
        all_data = await self._handle_pagination(url, payload_template)
        # 資料整理
        if all_data:
            for index, data in enumerate(all_data):
                acct_uuid = data["acct_uuid"]
                orgs_df = await self.get_acct_orgs(acct_uuid)
                all_data[index]["orgs"] = list(orgs_df["uuid"])
                
            return pd.DataFrame(all_data)
            
        return None

    async def export_xlsx(self, sendtask_content: list[str], isTokenRefreshed=False):
        '''將 sendtask 的參與人員清單匯出為 XLSX 檔案'''
        sendtask_uuid = sendtask_content[0]
        sendlog_type = "pretest" if sendtask_content[1] else "test"
        logger.info(f"Exporting sendlog for sendtask {sendtask_uuid} to CSV...")
        url = self.url + API_ENDPOINTS["export_csv"]
        payload = {
                    "sendtask_uuid": sendtask_uuid,
                    "record_page": 200,
                    "search_keyword": "",
                    "behavior_filter": 0,
                    "etime": None,
                    "order_method": "asc",
                    "page_sn": 1,
                    "search_order_by": "B",
                    "search_send_result": "ALL",
                    "sendlog_type": sendlog_type,
                    "stime": None
                }
        async with httpx.AsyncClient(timeout=300.0, verify=self.verify) as client:
            try:
                response = await client.post(url, headers=self._get_headers(), json=payload)
                response.raise_for_status()
                return response.content
            except httpx.RequestError as exc:
                logger.error(f"HTTP error occurred: {exc}")
            except Exception as e:
                if not isTokenRefreshed:
                    logger.info("Token expired, re-getting token and retrying...")
                    return await self.export_xlsx(sendtask_content, isTokenRefreshed=True)
                logger.error(f"Unhandled exception: {e}")
        return None              


# 初始化 getSe2data 實例
get_se2_data = getSe2data()

if __name__ == "__main__":
    # 測試抓取 sendtasks
    import asyncio
    # df = asyncio.run(get_se2_data.get_sendtasks())
    # print(df)

    data = get_se2_data.get_sendtask_metadata(uuid="5f6a6fa554f149578728ccf0109a42c9")
    print(data)

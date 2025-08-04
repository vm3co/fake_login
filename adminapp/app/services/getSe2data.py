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

from app.services.log_manager import Logger
from app.services.get_token import get_token


logger = Logger().get_logger()

class getSe2data:
    def __init__(self):
        cookie = get_token.get()
        self.url = "https://se.acsicook.info"
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": self.url,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
            "Referer": self.url + '/main/sendtask/list?lyt=v',
            "cookie": cookie
        }

        # 憑證
        # verify_name = 'front.se2.com.crt'
        verify_name = 'se.acsicook.info.crt'
        self.verify = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'certs', verify_name))

    async def send_post(self, url: str, payload: dict, isTokenRefreshed=False) -> dict | None:
        '''發送 POST 請求'''
        async with httpx.AsyncClient(timeout=60.0, verify=self.verify) as client:
            try:
                response = await client.post(url, headers=self.headers, json=payload)
                response.raise_for_status() # 如果 HTTP 回應的狀態碼不是 2xx（例如 400、401、500 等），就自動拋出一個錯誤
                data = response.json()
                return data
            except httpx.RequestError as exc:
                logger.error(f"HTTP error occurred: {exc}")
            except Exception as e:
                if not isTokenRefreshed:
                    # 嘗試重新從txt獲取 token 並重試
                    logger.info("Token expired, re-getting token and retrying...")
                    self.headers["cookie"] = get_token.get()
                    return await self.send_post(url, payload, isTokenRefreshed=True)
                logger.error(f"Unhandled exception: {e}")
            return None

    async def multiple_pages(self, payload_template: dict, url: str) -> list:
        '''處理多頁面請求'''
        all_data = []
        page = 1        
        while True:
            await asyncio.sleep(0.1)  # 加一點延遲避免被擋
            payload = payload_template.copy()
            payload["page_sn"] = page
            # logger.info(f"Requesting page {page}...")
            # 發送 POST 請求
            data = await self.send_post(url, payload)
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
        logger.info(f"Total items fetched: {len(all_data)}")
        return all_data

    async def get_sendtasks(self, end_time=None, start_time=None, filter_time_range=0) -> pd.DataFrame | None:
        '''
        抓取執行中專案清單(帶入參數可以指定專案建立時間)(撇除前測任務)
        
        :return: DataFrame 包含 sendtask 資料
        '''
        # 要發送 POST 的目標網址
        logger.info("Fetching sendtasks...")
        url = self.url + '/api/case/get_sendtasks'
        payload_template = {
            "end_time": end_time,
            "filter_time_range": filter_time_range,
            "order_field": "CreateTime",
            "order_method": "desc",
            "page_sn": 1,
            "record_page": 20,
            "sendtask_keyword": "",
            "sendtask_prestart": "no",
            "start_time": start_time,
            "time_field": "CreateTime"
        }
        all_data = await self.multiple_pages(payload_template, url)
        if all_data:
            # 將資料轉換為 DataFrame        
            sendtasks_df = pd.DataFrame(all_data)
            return sendtasks_df
        return None        


    async def get_sendtask_metadata(self, uuid: str) -> dict | None:
        '''
        抓取單一專案詳細資訊：是否被暫停、是否有延長任務時間、總人數
        :param uuid: 專案的 UUID
        '''
        # 要發送 POST 的目標網址
        # logger.info(f"Checking if sendtask {uuid} is paused...")
        url = self.url + '/api/case/get_sendtask'
        payload = {
            "sendlog_type":"test",  # 預設為 test
            "sendtask_uuid": uuid
        }
        data = await self.send_post(url, payload)
        if data is None:
            payload["sendlog_type"] = "pretest"  # 如果沒有資料，改為 pretest
            data = await self.send_post(url, payload)
        
        return None if not data else data.get("metadata", None)

    async def get_sendlog(self, uuid: str) -> pd.DataFrame | None:
        '''抓取專案參與人員清單'''
        # 要發送 POST 的目標網址
        logger.info(f"Fetching sendlog for sendtask {uuid}...")
        url = self.url + '/api/case/get_sendlog'
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
                            "sendlog_type": "test",
                            "stime": None
                        }
        all_data = await self.multiple_pages(payload_template, url)
        if not all_data:
            payload_template["sendlog_type"] = "pretest"
            all_data = await self.multiple_pages(payload_template, url)
            
        return None if not all_data else pd.DataFrame(all_data)

    async def get_mtmpl_subject_list(self) -> pd.DataFrame | None:
        '''抓取郵件樣板'''
        # 要發送 POST 的目標網址
        logger.info("Fetching mtemplate subject list...")
        url = self.url + '/api/editor/get_mtmpl_subject_list'
        payload = {
            "just_query": 1
        }        
        data = await self.send_post(url, payload)

        return None if not data else pd.DataFrame(data['data'])

    async def get_acct_orgs(self, acct_uuid: str) -> pd.DataFrame | None:
        '''抓取個別帳號擁有的組織'''
        # 要發送 POST 的目標網址
        logger.info(f"Fetching organizations for account {acct_uuid}...")
        url = self.url + '/api/account/get_acct'
        payload = {"acct_uuid": acct_uuid}
        data = await self.send_post(url, payload)

        return None if not data else pd.DataFrame(data["data"]["orgs"])

    async def get_accts(self) -> pd.DataFrame | None:
        '''抓取帳號'''
        # 要發送 POST 的目標網址
        logger.info("Fetching accounts...")
        url = self.url + '/api/account/get_accts'
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
        all_data = await self.multiple_pages(payload_template, url)
        # 資料整理
        if all_data:
            for index, data in enumerate(all_data):
                acct_uuid = data["acct_uuid"]
                orgs_df = await self.get_acct_orgs(acct_uuid)
                all_data[index]["orgs"] = list(orgs_df["uuid"])
                
            return pd.DataFrame(all_data)
            
        return None


# 初始化 getSe2data 實例
get_se2_data = getSe2data()

if __name__ == "__main__":
    # 測試抓取 sendtasks
    import asyncio
    df = asyncio.run(get_se2_data.get_sendtasks())
    print(df)

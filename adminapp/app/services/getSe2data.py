# -*- coding: utf-8 -*-
"""
Created on Thu May  8 14:32:44 2025

@author: 2501053

用api到se2系統抓取資料
"""
import os
import requests
import json
import pandas as pd
import asyncio
import httpx

from app.services.log_manager import Logger


logger = Logger().get_logger()

class getSe2data:
    def __init__(self):
        cookie = 'type2=eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiItaXkqUGhlTHhSQXlwKlBmNndNTnJLWlBWayZFWEk2b01IVzNaSGpXYChoKkZBbncmR19AQj5WZEMtQkc-PU1OQ3JRdDxYIiwidHlwZSI6ImFjY2VzcyIsImp0aSI6IjZmOGY1YmQ2LWM3MzUtNGQ1My05MDZlLTQyMmM3OTIyMjliZiIsImV4cCI6MTc0OTExMzIyMiwibmJmIjoxNzQ5MTAyNDIyLCJpYXQiOjE3NDkxMDI0MjJ9.JC6bpmUQerbM6yLMIxkQqorzyqyBsAkjQ78vRo7125c79lujBhthIieXRKj544ZOgyxJBp4fB3MiihhuBRtucA; type1=eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiItaXkqUGhlTHhSQXlwKlBmNndNTnJLWlBWayZFWEk2b01IVzNaSGpXYChoKkZBbncmR19AQj5WZEMtQkc-PU1OQ3JRdDxYIiwidHlwZSI6InJlZnJlc2giLCJqdGkiOiIyNWExY2ViNC0yMmI1LTRiNTQtYmZmZS1iNWIwN2FhMzIxNmMiLCJleHAiOjE3NDkxMTMyMjIsIm5iZiI6MTc0OTEwMjQyMiwiaWF0IjoxNzQ5MTAyNDIyfQ._gcOphEMae7Pn2PsIHHljxvZNHHQO0iYwy7VGaSIA38Xssik6zf4sET_hNdIDenCBR0e7LAqhTu0gWrX0D9-RA; type3="eyJuYW1lIjogIk1pa2UiLCAidHlwZS.I6ICJBZG1pbiIsICJyYW5kb21faWQiOiAiODliYTUyODljYTJkNDE4ZWIwNz.FjOTk0MTE0YzE3NzIifQ=="; lang=zh-TW'
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

    async def send_post(self, url: str, payload: dict) -> dict | None:
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
                logger.error(f"Unhandled exception: {e}")
            return None


    # async def fetch_new_cookie(self):
    #     url = self.url + "/api/account/refresh_token"
    #     # 這裡請根據實際需求帶入必要的 cookie 或 header
    #     cookies = {
    #         # "type1": "...",
    #         # "type2": "...",
    #         # 依需求填入
    #     }
    #     async with httpx.AsyncClient() as client:
    #         response = await client.get(url, cookies=cookies)
    #         # 取得 Set-Cookie
    #         set_cookie = response.headers.get("set-cookie")
    #         if set_cookie:
    #             # 你可以根據實際需求組合 cookie 字串
    #             # 例如只取 type1/type2/type3
    #             cookies_str = "; ".join([c.split(";")[0] for c in set_cookie.split(",")])
    #             return cookies_str
    #         return None

    async def multiple_pages(self, payload_template: dict, url: str) -> list:
        '''處理多頁面請求'''
        all_data = []
        page = 1        
        while True:
            await asyncio.sleep(0.1)  # 加一點延遲避免被擋
            payload = payload_template.copy()
            payload["page_sn"] = page
            print(f"Requesting page {page}...")
            # 發送 POST 請求
            data = await self.send_post(url, payload)
            if data is None:
                print("API return None, stopping further requests.")
                break
            page_data = data.get("data", [])
            if not page_data:
                print("No more data.")
                break

            all_data.extend(page_data)
            
            if len(page_data) < payload["record_page"]:
                break

            page += 1
        print(f"Total items fetched: {len(all_data)}")
        return all_data

    async def get_sendtasks(self) -> pd.DataFrame | None:
        '''抓取執行中專案清單'''
        # 要發送 POST 的目標網址
        url = self.url + '/api/case/get_sendtasks'
        payload_template = {
            "end_time": None,
            "filter_time_range": 0,
            "order_field": "CreateTime",
            "order_method": "desc",
            "page_sn": 1,
            "record_page": 20,
            "sendtask_keyword": "",
            "sendtask_prestart": "all",
            "start_time": None,
            "time_field": "CreateTime"
        }
        all_data = await self.multiple_pages(payload_template, url)
        if all_data:
            return pd.DataFrame(all_data)
        return None

    async def get_sendlog(self, uuid: str) -> pd.DataFrame | None:
        '''抓取專案參與人員清單'''
        # 要發送 POST 的目標網址
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
        if all_data:
            return pd.DataFrame(all_data)
        return None

    async def get_mtmpl_subject_list(self) -> pd.DataFrame | None:
        '''抓取郵件樣板'''
        # 要發送 POST 的目標網址
        url = self.url + '/api/editor/get_mtmpl_subject_list'
        payload = {
            "just_query": 1
        }        
        data = await self.send_post(url, payload)
        if data:
            return pd.DataFrame(data['data'])
        return None

    async def get_acct_orgs(self, acct_uuid: str):
        '''抓取個別帳號擁有的組織'''
        # 要發送 POST 的目標網址
        url = self.url + '/api/account/get_acct'
        payload = {"acct_uuid": acct_uuid}
        data = await self.send_post(url, payload)
        if data:
            return data["data"]["orgs"]
        return None

    async def get_accts(self) -> pd.DataFrame | None:
        '''抓取帳號'''
        # 要發送 POST 的目標網址
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
                orgs_dict = await self.get_acct_orgs(acct_uuid)
                orgs_list = []
                for orgs in orgs_dict:
                    orgs_list.append(orgs["uuid"])
                all_data[index]["orgs"] = orgs_list
                
            return pd.DataFrame(all_data)
            
        return None


# 初始化 getSe2data 實例
get_se2_data = getSe2data()

if __name__ == "__main__":
    # 測試抓取 sendtasks
    import asyncio
    df = asyncio.run(get_se2_data.get_sendtasks())
    print(df)

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
import time
import httpx

from app.services.log_manager import Logger


logger = Logger().get_logger()

class getSe2data:
    def __init__(self):
        cookie = "type2=eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ4QGFRVDFMKEdUK0QrUE5RVEpWUFZuRkdwI044SGs8Py1Xe1EoZkZyMGY-VjFHe2hHN1BSPUZ2JWFQVnZpfmlXSXZ6S3dTJjViKiIsInR5cGUiOiJhY2Nlc3MiLCJqdGkiOiJkMGU0ZGEyYS1mNDVmLTQxYWQtOTI2MC03OTFjYjc5M2Y2MjciLCJleHAiOjE3NDc4MjAxMjgsIm5iZiI6MTc0NzgwOTMyOCwiaWF0IjoxNzQ3ODA5MzI4fQ.ZOzH7dC99Zzg34FUsxRCKbnRgntsHVGoohH_7g2e_P5iEJD_L7ZQQpsDppVLUfKA-avQ9NZxyNA3xtomz9BHSg; type1=eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ4QGFRVDFMKEdUK0QrUE5RVEpWUFZuRkdwI044SGs8Py1Xe1EoZkZyMGY-VjFHe2hHN1BSPUZ2JWFQVnZpfmlXSXZ6S3dTJjViKiIsInR5cGUiOiJyZWZyZXNoIiwianRpIjoiMTYwY2E2OTEtY2NmZS00OTU1LTg2YjEtN2IyMTM5YTcxNjIxIiwiZXhwIjoxNzQ3ODIwMTI4LCJuYmYiOjE3NDc4MDkzMjgsImlhdCI6MTc0NzgwOTMyOH0.YJnNSKmfYDBWv2TQgSKIb21Y3fnJPQTERxLV2wuInEZycBlKsRVdHhCj6e3weWyHemQeOvLS7RB_nDxdnJQBUA; type3=eyJuYW1lIjogIkFDU0lfVEVTVCIsIC.J0eXBlIjogIkFkbWluIiwgInJhbmRvbV9pZCI6ICJmZTI1MmMyZjJmMzA0Zj.djOTBkMzg5ZDFmZGJhZTg2ZSJ9; lang=zh-TW"

        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": "https://frontend.se2.com",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
            "Cookie": cookie,
        }

        # 憑證
        self.verify = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'certs', 'front.se2.com.crt'))

    async def send_post(self, url: str, headers: dict, payload: dict):
        async with httpx.AsyncClient(timeout=60.0, verify=self.verify) as client:
            try:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status() # 如果 HTTP 回應的狀態碼不是 2xx（例如 400、401、500 等），就自動拋出一個錯誤

                data = response.json()
                return data
            except httpx.RequestError as exc:
                logger.error(f"HTTP error occurred: {exc}")
            except Exception as e:
                logger.error(f"Unhandled exception: {e}")
            return None

    async def get_sendtasks(self):
        # 要發送 POST 的目標網址
        url = 'https://frontend.se2.com/api/case/get_sendtasks'
        headers = self.headers
        headers["Referer"] = "https://frontend.se2.com/main/sendtask/list?ly=t=v"
        # payload
        payload = {
            "end_time": None,
            "filter_time_range": 0,
            "order_field": "CreateTime",
            "order_method": "desc",
            "page_sn": 1,
            "record_page": 5,
            "sendtask_keyword": "",
            "sendtask_prestart": "all",
            "start_time": None,
            "time_field": "CreateTime"
        }        
        # 發送 POST 請求
        data = await self.send_post(url, headers, payload)
        # 資料整理
        if data:
            df = pd.DataFrame(data['data'])
            return df
        else:
            return None


    async def get_sendlog(self, uuid: str):
        # 要發送 POST 的目標網址
        url = 'https://frontend.se2.com/api/case/get_sendlog'
        headers = self.headers
        headers["Referer"] = "https://frontend.se2.com/main/testcase/list?lyt=v"
        # payload
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
        all_data = []
        page = 1
        while True:
            payload = payload_template.copy()
            payload["page_sn"] = page
            print(f"Requesting page {page}...")
            # 發送 POST 請求
            data = await self.send_post(url, headers, payload)
            page_data = data.get("data", [])
            if not page_data:
                print("No more data.")
                break

            all_data.extend(page_data)
            
            if len(page_data) < payload["record_page"]:
                break

            page += 1
            time.sleep(0.1)  # 加一點延遲避免被擋

        print(f"Total items fetched: {len(all_data)}")
        # 資料整理
        if data:
            return pd.DataFrame(all_data)
        return None
    
        
get_se2_data = getSe2data()

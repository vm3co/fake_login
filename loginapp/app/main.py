from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from datetime import datetime
from dotenv import load_dotenv
import csv
import os

# 引入分離的路由模組
from app.routers.qrcode_router import router as qrcode_router
from app.routers.login_router import router as login_router


app = FastAPI()

# 掛載靜態文件目錄
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# 註冊路由
app.include_router(qrcode_router)
app.include_router(login_router)

def main():
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)

if __name__ == "__main__":
    main()
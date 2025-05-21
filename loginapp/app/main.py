import os
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from app.core.db_controller import db
# 引入分離的路由模組
from app.routers.login_router import router as login_router
from app.api.record_api import router as record_api
from app.api.qrcode_api import router as qrcode_api


# 引入資料庫
@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.db_init()
    yield
    await db.db_close()

app = FastAPI(lifespan=lifespan)
# app = FastAPI()

# 掛載靜態文件目錄
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# 註冊路由
app.include_router(login_router)
app.include_router(record_api, prefix="/api")
app.include_router(qrcode_api, prefix="/qrcode")

def main():
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)

if __name__ == "__main__":
    main()
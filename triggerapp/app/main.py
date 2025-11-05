import os
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from contextlib import asynccontextmanager
from pathlib import Path

from app.repository.db_controller import db
# 引入分離的路由模組
from app.routers.trigger_router import router as trigger_router
from app.api.record_api import router as record_api
from app.api.qrcode_api import router as qrcode_api


# BASE_DIR = Path(__file__).resolve().parent

# 引入資料庫
@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.db_init()
    yield
    await db.db_close()

app = FastAPI(lifespan=lifespan, root_path="/trigger")
# app = FastAPI(lifespan=lifespan)
# app = FastAPI()

# 掛載靜態文件目錄
app.mount(
    "/static", 
    # StaticFiles(directory=BASE_DIR / "static"), 
    StaticFiles(directory="app/static"), 
    name="static"  # 'name' 參數用於 Jinja2 的 url_for 函數
)

# 註冊路由
app.include_router(trigger_router)
app.include_router(record_api, prefix="/api")
app.include_router(qrcode_api, prefix="/qrcode")

def main():
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)

if __name__ == "__main__":
    main()
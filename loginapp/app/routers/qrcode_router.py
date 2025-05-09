from fastapi import FastAPI, Request, Form, Depends, APIRouter
from fastapi.responses import HTMLResponse
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from urllib.parse import urljoin
from urllib.parse import urlencode
from app.services.qrcode import qrcode

# app = FastAPI()
router = APIRouter()

'''組合qrcode網址'''
def creat_qrcode_url(uuid):
    # 寫死主網址
    HOST_URL = "https://se2.link.cc/a/l/"
    QUERY_STRINGS = "reurl"
    reurl = "http://localhost:8090/login/"

    query_string = urlencode({QUERY_STRINGS: urljoin(reurl, uuid)})
    url = urljoin(HOST_URL, uuid) + "?" + query_string

    return url

# def creat_qrcode_url(logintype, uuid):
#     # 寫死主網址
#     HOST_URL = "https://se2.link.cc/a/l/"
#     QUERY_STRINGS = "reurl"
#     REURL_URL = "http://localhost:8090/login/"

#     reurl = urljoin(REURL_URL, logintype)
#     query_string = urlencode({QUERY_STRINGS: urljoin(reurl, uuid)})
#     url = urljoin(HOST_URL, uuid) + "?" + query_string

#     return url

# 設定模板目錄
templates = Jinja2Templates(directory="app/templates")

@router.get("/qrcode")
async def read_root(request: Request):
    return templates.TemplateResponse("qrcode.html", {"request": request, "title": "FastAPI 渲染 HTML"})

@router.post("/qrcode")
async def submit_form(request: Request, url: str = Form(...)):
    img_url = qrcode.output(url)
    return templates.TemplateResponse("qrcode.html", {
        "request": request,
        "img": img_url
    })

@router.get("/qrcode/uuid")
async def project_qrcode_image(uuid: str = None):
    url = creat_qrcode_url(uuid)
    img_io = qrcode.output(url)

    return StreamingResponse(img_io, media_type="image/png")

# @router.get("/qrcode/{logintype}/uuid")
# async def project_qrcode_image(logintype: str, uuid: str = None):
#     url = creat_qrcode_url(logintype, uuid)
#     img_io = qrcode.output(url)

#     return StreamingResponse(img_io, media_type="image/png")

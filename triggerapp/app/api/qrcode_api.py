import os

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from urllib.parse import urljoin
# from urllib.parse import urlencode
from app.services.qrcode import qrcode


router = APIRouter()

'''組合qrcode網址'''
def creat_qrcode_url(base_url: str, logintype: str, uuid: str):
    # base_url 範例: "https://selink.20231202.xyz" (正式) 或 "http://localhost/trigger" (本地)
    # 我們希望組合出像 "https://.../qr/20231202/some-uuid" 的網址
    # 注意: urljoin 的行為與 path 有關，建議 base_url 結尾補上 / 
    if not base_url.endswith("/"):
        base_url += "/"
    
    input_page_url = urljoin(base_url, "qr/")
    reurl = urljoin(input_page_url, logintype) + "/"
    # query_string = urlencode({QUERY_STRINGS: urljoin(reurl, uuid)})
    # url = urljoin(HOST_URL, uuid) + "?" + query_string
    # return url
    return urljoin(reurl, uuid)

# @router.get("/from-url")
# async def qrcode_from_url(request: Request, url: str, uuid: str = None):
#     """
#     從指定的 URL 直接生成 QR code 圖片。
#     - **url**: 要編碼成 QR code 的完整網址。
#     """
#     base_url = f"{request.url.scheme}://{request.url.netloc}"
#     url = creat_qrcode_url(base_url, "from-url", uuid)
#     img_io = qrcode.output(url)

#     return StreamingResponse(img_io, media_type="image/png")

@router.get("/{logintype}/uuid")
async def project_qrcode_image(logintype: str, request: Request, uuid: str, url: str = None):
    # 優先從環境變數讀取外部網址，若無則 fallback 到 request 分析 (for local dev default)
    base_url = os.getenv("TRIGGER_APP_URL")
    if not base_url:
        base_url = f"{request.url.scheme}://{request.url.netloc}"
    qrcode_url = creat_qrcode_url(base_url, logintype, uuid)
    if url:
        qrcode_url = qrcode_url + "?url=" + url
    img_io = qrcode.output(qrcode_url)

    return StreamingResponse(img_io, media_type="image/png")


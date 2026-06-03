import os

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from urllib.parse import urljoin
# from urllib.parse import urlencode
from app.services.qrcode import qrcode
from app.repository.db_controller import db_controller
from app.repository.models import TriggerPage, Domain
from app.services.log_manager import Logger


router = APIRouter()
logger = Logger().get_logger()


async def _resolve_page_base_url(page_name: str, request: Request) -> str:
    """優先回傳 page 綁定 domain 的 URL；無綁定則回 TRIGGER_APP_URL 或 request host。"""
    try:
        page = await db_controller.get_one(TriggerPage, {"page_value": page_name})
        if page and page.allowed_domain_id:
            domain = await db_controller.get_one(Domain, {"id": page.allowed_domain_id})
            if domain and domain.domain:
                proto = request.url.scheme or "https"
                return f"{proto}://{domain.domain}"
    except Exception as e:
        logger.error(f"解析 page 綁定 domain 失敗 ({page_name}): {e}")

    fallback = os.getenv("TRIGGER_APP_URL")
    if fallback:
        return fallback
    return f"{request.url.scheme}://{request.url.netloc}"

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
async def project_qrcode_image(logintype: str, request: Request, uuid: str, url: str = None, redirect_url: str = None):
    # 優先取 page 綁定 domain；無則 fallback TRIGGER_APP_URL / request host
    base_url = await _resolve_page_base_url(logintype, request)
    qrcode_url = creat_qrcode_url(base_url, logintype, uuid)
    
    query_params = []
    if url:
        query_params.append(f"url={url}")
    if redirect_url:
        query_params.append(f"redirect_url={redirect_url}")
        
    if query_params:
        qrcode_url += "?" + "&".join(query_params)
        
    img_io = qrcode.output(qrcode_url)

    return StreamingResponse(img_io, media_type="image/png")


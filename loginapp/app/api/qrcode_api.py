from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from urllib.parse import urljoin
from urllib.parse import urlencode
from app.services.qrcode import qrcode


router = APIRouter()

'''組合qrcode網址'''
def creat_qrcode_url(logintype, uuid):
    # 寫死主網址
    HOST_URL = "https://se2.link.cc/a/l/"
    QUERY_STRINGS = "reurl"
    REURL_URL = "http://localhost:8090/login/"

    reurl = urljoin(REURL_URL, logintype) + "/"
    query_string = urlencode({QUERY_STRINGS: urljoin(reurl, uuid)})
    url = urljoin(HOST_URL, uuid) + "?" + query_string

    return url

@router.get("/{logintype}/uuid")
async def project_qrcode_image(logintype: str, uuid: str = None):
    url = creat_qrcode_url(logintype, uuid)
    img_io = qrcode.output(url)

    return StreamingResponse(img_io, media_type="image/png")
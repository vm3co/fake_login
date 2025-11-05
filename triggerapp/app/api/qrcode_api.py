import os

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from urllib.parse import urljoin
# from urllib.parse import urlencode
from app.services.qrcode import qrcode


router = APIRouter()

'''組合qrcode網址'''
def creat_qrcode_url(logintype, uuid):
    # HOST_URL = "https://se2.link.cc/a/l/"
    # QUERY_STRINGS = "reurl"
    REURL_URL = os.getenv("APP_BASE_URL", "http://localhost/input") + "/"

    reurl = urljoin(REURL_URL, logintype) + "/"
    # query_string = urlencode({QUERY_STRINGS: urljoin(reurl, uuid)})
    # url = urljoin(HOST_URL, uuid) + "?" + query_string
    # return url
    return urljoin(reurl, uuid)

@router.get("/{logintype}/uuid")
async def project_qrcode_image(logintype: str, uuid: str = None):
    url = creat_qrcode_url(logintype, uuid)
    img_io = qrcode.output(url)

    return StreamingResponse(img_io, media_type="image/png")
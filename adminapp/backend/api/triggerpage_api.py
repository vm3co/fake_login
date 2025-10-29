'''
處理trigger網頁
'''
import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Depends, Request, UploadFile
from isort import file
from pydantic import BaseModel
import json

from backend.services.log_manager import Logger


logger = Logger().get_logger()


def get_router():
    """
    """
    router = APIRouter()

    class UploadRequest(BaseModel):
        value: str
        label: str
        page: UploadFile

    @router.post("/triggerpage/upload")
    async def triggerpage_upload(data: UploadRequest):
        """
        """
        pass
    return router

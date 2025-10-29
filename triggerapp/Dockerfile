# 使用官方 Python 映像檔
FROM python:3.12-slim

# 設定工作目錄
WORKDIR /app

# 複製所有檔案進容器
COPY . /app

# 安裝相依套件
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 開放 port 8080
EXPOSE 8080

# 執行 FastAPI app（用 run.py 或直接指定 app.main）
CMD ["python", "run.py"]

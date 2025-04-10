# 使用輕量版 Python
FROM python:3.12-slim

# 設定工作目錄
WORKDIR /app

# 複製專案檔案
COPY . /app

# 安裝必要函式庫
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 開放對外連接的 port
EXPOSE 8080

# 啟動 FastAPI，從 run.py 執行
CMD ["python", "run.py"]

# 使用輕量版 Python
FROM python:3.12-slim

# 設定工作目錄 (Using /app is a common convention)
WORKDIR /app

# 複製 requirements.txt 並安裝依賴
# 利用 Docker Layer Caching：只有當 requirements.txt 變動時才會重新安裝
COPY requirements.txt .

# 安裝相依套件
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 複製應用程式原始碼
COPY . /app

# 開放對外連接的 port
EXPOSE 8080

# 啟動 FastAPI，從 run.py 執行
CMD ["python", "run.py"]

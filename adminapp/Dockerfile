# 使用輕量版 Python
FROM python:3.12-slim

# 設定工作目錄 (Using /app is a common convention)
WORKDIR /app

# 複製 requirements.txt 並安裝依賴
# This leverages Docker's layer caching. Dependencies are only re-installed
# if requirements.txt changes.
COPY requirements.txt .

# 安裝必要函式庫
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 複製應用程式原始碼
COPY . .

# 開放對外連接的 port
EXPOSE 8080

# 啟動 FastAPI，從 run.py 執行
CMD ["python", "run.py"]

# 1. 使用官方輕量版 Python
FROM python:3.12-slim

# 2. 設定環境變數 (重要優化)
# PYTHONDONTWRITEBYTECODE=1: 防止 Python 產生 .pyc 檔，保持容器乾淨
# PYTHONUNBUFFERED=1: 確保 Log 會立刻輸出到 Docker Log，不會被暫存，這對除錯非常重要
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 3. 設定工作目錄
WORKDIR /app

# 4. 安裝相依套件 (利用 Cache 機制)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 5. 複製應用程式原始碼
# 由於 WORKDIR 已經是 /app，這裡用 "." 即可，寫法更簡潔
COPY . .

# 6. 安全性優化：建立並切換到非 root 使用者 (選用，但強烈建議)
# 預設 Docker 用 root 跑，若被駭客攻破可能會影響 Host 系統
# 建立一個名為 'appuser' 的使用者
RUN adduser --disabled-password --no-create-home appuser \
    && chown -R appuser:appuser /app
USER appuser

# 7. 開放 port
EXPOSE 8080

# 8. 啟動指令
CMD ["python", "run.py"]
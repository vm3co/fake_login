# 1. 使用官方輕量版 Python
FROM python:3.12-slim

# 2. 設定環境變數 (重要優化)
# PYTHONDONTWRITEBYTECODE=1: 防止 Python 產生 .pyc 檔，保持容器乾淨
# PYTHONUNBUFFERED=1: 確保 Log 會立刻輸出到 Docker Log，不會被暫存，這對除錯非常重要
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# 3. 設定工作目錄
WORKDIR /app

# 4. 安裝 Playwright 系統依賴
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxrandr2 libgbm1 libpango-1.0-0 libcairo2 \
    libasound2 libxshmfence1 fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# 5. 安裝相依套件 (利用 Cache 機制)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && playwright install chromium --with-deps \
    && chmod -R 755 /ms-playwright

# 5. 複製應用程式原始碼
# 由於 WORKDIR 已經是 /app，這裡用 "." 即可，寫法更簡潔
COPY . .

# 6. 安全性優化：建立並切換到非 root 使用者 (選用，但強烈建議)
# 預設 Docker 用 root 跑，若被駭客攻破可能會影響 Host 系統
# 建立一個名為 'appuser' 的使用者
RUN adduser --disabled-password --no-create-home appuser \
    && chown -R appuser:appuser /app
# 由於 Playwright 需要寫入一些 browser metadata，我們確保 appuser 對 ~/.cache 也有權限
RUN mkdir -p /home/appuser/.cache && chown -R appuser:appuser /home/appuser/.cache
USER appuser

# 7. 開放 port
EXPOSE 8080

# 8. 啟動指令
CMD ["python", "run.py"]
# **社交工程 Dashboard 系統架構優化方案 (Redis + PostgreSQL + Docker)**

## **1. 專案概述**

本文件描述如何在現有的 PostgreSQL 系統前，加入 Redis 作為快取層 (Caching Layer) 與寫入緩衝層 (Write Buffer)，以解決主系統資料同步、過期資料封存，以及高併發下的偽裝網頁觸發紀錄問題。

## **2. 資料庫 Schema 變更 (PostgreSQL)**

為了配合 Redis 架構並簡化維護，需對現有 Database 進行以下調整。

### **2.1 新增 send_log_details (取代動態 Table)**

**目的**：統一管理所有受測者的詳細觸發紀錄，避免動態建立 Table 造成的維運困難。

```
CREATE TABLE IF NOT EXISTS send_log_details (  
    id BIGSERIAL PRIMARY KEY,  
    uuid TEXT NOT NULL,                -- 受測者唯一識別碼 (對應主系統的 uuid)  
    sendtask_uuid VARCHAR(36) NOT NULL,-- 關聯回任務主表  
      
    -- 主系統同步過來的基本資料  
    target_email TEXT,  
    template_uuid TEXT,  
    plan_time BIGINT,  
    send_time BIGINT,  
    send_res TEXT,  
      
    -- 主系統同步過來的觸發紀錄  
    access_time BIGINT[],  
    access_src TEXT[],  
    access_dev TEXT[],  
    click_time BIGINT[],  
    click_src TEXT[],  
    click_dev TEXT[],  
    file_time BIGINT[],  
    file_src TEXT[],  
    file_dev TEXT[],

    -- Dashboard 系統獨有的觸發紀錄 (偽裝網頁)  
    second_access_time BIGINT[],  
    second_access_src TEXT[],  
    second_access_dev TEXT[],  
    second_input_time BIGINT[],  
    second_input_src TEXT[],  
    second_input_dev TEXT[],  
    second_input_info TEXT[],  -- 建議存 JSON 字串或 TEXT Array

    -- 索引優化  
    CONSTRAINT fk_sendtask FOREIGN KEY(sendtask_uuid) REFERENCES sendtasks(sendtask_uuid) ON DELETE CASCADE  
);

-- 建立索引以加速查詢  
CREATE INDEX idx_details_sendtask_uuid ON send_log_details(sendtask_uuid);  
CREATE INDEX idx_details_uuid ON send_log_details(uuid);
```

### **2.2 修改 sendtasks**

**目的**：新增欄位以支援資料封存策略。

ALTER TABLE sendtasks ADD COLUMN IF NOT EXISTS is_archived BOOLEAN DEFAULT FALSE;  
-- 用於標記該任務是否已超過 14 天且不再向主系統同步

## **3. Redis 架構設計**

Redis 將扮演兩個角色：

1. **熱資料快取 (Hot Data Cache)**：儲存 14 天內的任務詳細資料，供前端快速讀取。  
2. **寫入緩衝 (Write Buffer)**：暫存偽裝網頁的觸發事件，避免直接衝擊 DB。

### **3.1 Key Naming Convention (命名規範)**

| Key 模式 | 類型 | TTL | 說明 |
| :---- | :---- | :---- | :---- |
| task:{uuid}:details | Hash 或 String(JSON) | 15天 / 1小時 | 儲存該任務下所有受測者的詳細清單。如果是熱資料(近期)設15天；如果是查詢舊資料(冷資料)設1小時。 |
| buffer:trigger_events | List / Stream | 無 | 佇列 (Queue)，儲存尚未寫入 PostgreSQL 的觸發事件。 |
| task:{uuid}:meta | Hash | 15天 | 任務的 metadata (如開始時間、狀態)，減少查詢 sendtasks 表。 |

### **3.2 資料結構範例**

**task:{sendtask_uuid}:details (JSON String)**

```
{  
  "user_uuid_1": {  
    "target_email": "test@example.com",  
    "click_time": [1715000000],  
    "second_access_time": [1715000050],  
    "second_input_info": ["password123"]  
  },  
  "user_uuid_2": { ... }  
}
```
buffer:trigger_events **(List Item)**
```
{  
  "event_type": "second_access",  
  "uuid": "user_uuid_1",  
  "timestamp": 1715000100,  
  "src_ip": "1.1.1.1",  
  "device": "iPhone",  
  "input_data": null  
}
```
## **4. 系統運作流程邏輯**

### **4.1 流程 A: 主系統資料同步 (Sync Worker)**

週期：依'adminapp/backend/main.py'裡面所寫的更新時段進行執行

1. **讀取任務列表**：從 DB 撈取 is_archived = False 的任務。  
2. **呼叫 API**：執行 getSe2data.py 取得最新資料。  
3. **資料整併**：  
   * 比對 DB 現有資料與 API 資料。  
   * **注意**：API 資料會覆蓋 access_time, click_time (主系統資料)，但必須**保留** DB 中既有的 second_access_time (Dashboard 獨有資料)。  
4. **寫入 PostgreSQL**：更新 send_log_details。  
5. **更新 Redis**：將整合後的最新資料 SET 回 task:{uuid}:details，並重設 TTL 為 15 天。

### **4.2 流程 B: 偽裝網頁觸發 (Trigger Logic)**

*當受害者進入偽裝網頁或輸入資料時*

1. **接收請求**：Web Server (FastAPI/Flask/Django) 收到 Request。  
2. **寫入 Redis Buffer** (極速)：  
   * 將事件封裝成 JSON。  
   * RPUSH buffer:trigger_events JSON_DATA。  
3. **即時更新 Cache (Optional)**：  
   * 為了讓 Dashboard 管理員能「秒級」看到有人上鉤，可同時更新 task:{uuid}:details 中的該使用者紀錄。  
4. **回傳 Response**：回傳網頁給受害者，不需等待 DB 寫入。

### **4.3 流程 C: Buffer 落地 (Persistence Worker)**

*背景程式，持續運行*

1. **監聽 Queue**：迴圈執行 BLPOP buffer:trigger_events。  
2. **批次寫入**：累積一定數量 (如 50 筆) 或一定時間 (如 5 秒) 後。  
3. **更新 PostgreSQL**：  
   * 執行 UPDATE send_log_details SET second_access_time = array_append(second_access_time, :new_time) WHERE uuid = :uuid。

### **4.4 流程 D: 讀取資料 (Dashboard API)**

1. **前端請求**：查詢某任務的詳細資料。  
2. **Redis 查詢**：檢查 task:{uuid}:details 是否存在。  
   * **Hit**: 直接回傳 JSON (極速)。  
   * **Miss (冷資料回填)**：從 PostgreSQL send_log_details 撈取資料 -> 回傳給前端 -> **同時寫入 Redis 但 TTL 設較短 (如 1 小時)**。

### **4.5 流程 E: 資料封存 (Archiving Job)**

*每日執行一次*

1. 查詢 sendtasks 中 test_end_ut 超過 14 天 且 is_archived = False 的任務。  
2. 將 is_archived 更新為 True。  
3. 刪除 Redis 中對應的 Key task:{uuid}:details (釋放記憶體)。  
4. 此後 Dashboard 查詢該任務時，會自動走「流程 D」的 Miss 路徑，實現冷熱分離。

## **5. Docker 部署配置**

以下配置將 Redis 加入您的 Docker Compose 環境中。

### **5.1 docker-compose.yaml (正式環境配置)**

在 services 區塊中新增了 redis，並為 trigger-app 和 admin-app 加入了依賴與環境變數。

```
services:  
  # =========================================  
  # 資料庫服務 (PostgreSQL)  
  # =========================================  
  postgres-db:  
    image: postgres:16  
    container_name: fake-login-postgres-db  
    environment:  
      POSTGRES_USER: myuser  
      POSTGRES_PASSWORD: mypassword  
      POSTGRES_DB: mydatabase  
    volumes:  
      - pgdata:/var/lib/postgresql/data  
      - ./pg_backup:/backup  
    healthcheck:  
      test: [ "CMD", "pg_isready", "-U", "myuser", "-d", "mydatabase" ]  
      interval: 5s  
      timeout: 5s  
      retries: 5

  # =========================================  
  # 快取服務 (Redis) [新增]  
  # =========================================  
  redis:  
    image: redis:alpine  
    container_name: fake-login-redis  
    # 開啟 AOF 持久化，避免 Redis 重啟後資料全丟  
    command: redis-server --appendonly yes  
    volumes:  
      - redis_data:/data  
    healthcheck:  
      test: [ "CMD", "redis-cli", "ping" ]  
      interval: 5s  
      timeout: 3s  
      retries: 5

  # =========================================  
  # 觸發系統 (Trigger App)  
  # =========================================  
  trigger-app:  
    build:  
      context: ./triggerapp  
    container_name: fake-login-trigger-app  
    environment:  
      - LOG_FILE=${LOG_PATH}  
      - TRIGGER_APP_URL=${TRIGGER_APP_URL}  
      # 加入 Redis 連線資訊  
      - REDIS_HOST=redis  
      - REDIS_PORT=6379  
    volumes:  
      - templates_data:/app/templates  
    depends_on:  
      postgres-db:  
        condition: service_healthy  
      redis:  
        condition: service_healthy # 等待 Redis 啟動  
    env_file:  
      - .env

  # =========================================  
  # 管理後台 (Admin App)  
  # =========================================  
  admin-app:  
    build:  
      context: ./adminapp  
      dockerfile: Dockerfile  
    container_name: fake-login-admin-app  
    volumes:  
      - templates_data:/app/uploads_for_trigger_app_templates  
    depends_on:  
      postgres-db:  
        condition: service_healthy  
      redis:  
        condition: service_healthy # 等待 Redis 啟動  
    env_file:  
      - .env  
    environment:  
      - TRIGGER_APP_URL=${TRIGGER_APP_URL}  
      - GEMINI_APY_KEY=${GEMINI_APY_KEY}  
      - OPENAI_API_KEY=${OPENAI_API_KEY}  
      - LITELLM_API_KEY=${LITELLM_API_KEY}  
      - LITELLM_SERVER_IP=${LITELLM_SERVER_IP}  
      # 加入 Redis 連線資訊  
      - REDIS_HOST=redis  
      - REDIS_PORT=6379

  # =========================================  
  # Nginx 反向代理  
  # =========================================  
  nginx:  
    build:  
      context: .  
      dockerfile: Dockerfile.nginx  
    container_name: fake-login-nginx  
    ports:  
      - "80:80"  
      - "443:443"  
    depends_on:  
      - admin-app  
      - trigger-app  
    volumes:  
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro  
      - ./nginx/proxy_params_common:/etc/nginx/proxy_params_common:ro

volumes:  
  pgdata:  
  redis_data: # [新增] Redis 資料卷  
  templates_data:
```
### **5.2 docker-compose.override.yml (開發環境配置)**

在開發環境中，將 Redis 的 Port 映射出來，方便您使用 Redis Desktop Manager 等工具進行除錯。
```
services:  
  # =========================================  
  # 開發環境：資料庫  
  # =========================================  
  postgres-db:  
    ports:  
      - "15432:5432" 

  # =========================================  
  # 開發環境：快取服務 (Redis) [新增]  
  # =========================================  
  redis:  
    ports:  
      - "6379:6379" # 開放 Port 供本機開發工具連線

  # =========================================  
  # 開發環境：觸發系統  
  # =========================================  
  trigger-app:  
    volumes:  
      - ./triggerapp:/app  
    environment:  
      - DEBUG=true

  # =========================================  
  # 開發環境：管理後台  
  # =========================================  
  admin-app:  
    volumes:  
      - ./adminapp:/app  
      - ./triggerapp/app/templates:/app/uploads_for_trigger_app_templates  
    environment:  
      - DEBUG=true

  # =========================================  
  # 開發環境：Nginx  
  # =========================================  
  nginx:  
    environment:  
      - NGINX_ENVSUBST_OUTPUT_DIR=/etc/nginx
```
## **6. 資料生命週期與儲存策略 (Data Lifecycle Strategy)**

本章節說明為何不將所有資料存入 Redis，以及冷熱資料的處理原則。

### **6.1 核心原則：Redis 是「緩衝」與「快取」，Postgres 是「倉庫」**

* **不建議**將所有歷史資料永久存於 Redis，這會導致高昂的記憶體成本與較慢的系統啟動速度。  
* Redis 的核心價值在於處理**高併發寫入 (Write Buffer)** 與 **熱點資料查詢 (Hot Cache)**。

### **6.2 Python 實作邏輯 (包含冷熱分離)**
```
import redis  
import json  
import os  
from db_module import get_details_from_postgres

# 使用環境變數設定 Redis 連線，預設為 localhost (供開發使用)  
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')  
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))  
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)

def get_task_details(sendtask_uuid, is_archived_task=False):  
    cache_key = f"task:{sendtask_uuid}:details"  
      
    # 1. 嘗試讀快取 (Hot Path)  
    cached_data = r.get(cache_key)  
    if cached_data:  
        return json.loads(cached_data)  
          
    # 2. 讀資料庫 (Cache Miss / Cold Path)  
    # 這裡從 PostgreSQL 的 send_log_details 撈取  
    details = get_details_from_postgres(sendtask_uuid)  
      
    # 3. 判斷 TTL (Time To Live)  
    if is_archived_task:  
        # 如果是查詢已封存的舊任務，只在 Redis 暫存 1 小時 (3600秒)  
        # 這是 "Lazy Loading"，避免偶爾的一次查詢佔用記憶體太久  
        ttl = 3600   
    else:  
        # 如果是進行中的任務，存 15 天 (覆蓋整個任務週期)  
        ttl = 1296000   
          
    # 4. 寫入 Redis  
    if details:  
        details_json = json.dumps(details, default=str)  
        r.setex(cache_key, ttl, details_json)  
      
    return details
```
## **7. 總結**

此架構將**讀取壓力轉嫁給 Redis**，將**寫入壓力透過 Buffer 緩解**，並透過**單一大表**解決了維護與擴充性的問題。

* **最近 14 天資料**：常駐 Redis，速度極快。  
* **歷史資料**：存在 PostgreSQL，需要時才載入 Redis (Lazy Load)，節省記憶體成本。

這樣的設計既保留了關聯式資料庫的穩定性，又具備了 NoSQL 的高併發效能。
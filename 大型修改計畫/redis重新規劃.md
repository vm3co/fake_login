# 社交工程 Dashboard 系統架構優化方案 v2 (邏輯修正版)

## 1. 專案概述

本文件為 `System_Architecture_Plan.md` 的邏輯修正與優化版本。主要針對 Redis 與 PostgreSQL 之間的資料流向與生命週期管理進行了更精確的定義，以確保資料一致性並優化記憶體使用。

**核心目標**：

* **讀取 (Read)**：優先讀 Redis，失敗才讀 DB (Cache-Aside / Lazy Loading)。
* **寫入 (Write)**：以 DB 為真理來源 (Source of Truth)，寫入 DB 後**強制覆蓋** Redis，不進行昂貴的資料比對。
* **生命週期 (TTL)**：採用簡化後的階層式 TTL，依靠 Sync Worker 的持續刷新來維持熱度，優化記憶體控管。

---

## 2. 系統運作流程邏輯 (核心修正)

### 2.1 流程 A: 讀取資料 (Dashboard API - Read Path)
*觸發時機：使用者開啟 Dashboard 網頁查看任務詳細資料時*

1.  **前端請求**：API 收到請求 `GET /api/task/{uuid}/details`。
2.  **Redis 查詢 (Cache Check)**：
    * 檢查 Key: `task:{uuid}:details`。
    * **Hit (有資料)**：直接回傳 JSON。 **(預期 95% 的請求走這條路)**
    * **Miss (無資料)**：
        1.  從 PostgreSQL `send_log_details` 撈取該任務完整資料。
        2.  回傳給前端。
        3.  **[非同步] 回填 Redis**：將資料轉為 JSON，寫入 Redis，並根據任務狀態設定 TTL (詳見第 3 節)。

### 2.2 流程 B: 定期同步與更新 (Sync Worker - Write Path)
*觸發時機：每 30 分鐘排程 或 管理員手動點擊「更新任務」*

1.  **外部資料獲取**：呼叫 `getSe2data.py` 向主系統 (SE2) 取得最新任務數據。
2.  **寫入 PostgreSQL (Source of Truth)**：
    * 將新資料更新至 `send_log_details` 表。
    * **關鍵邏輯**：使用 `ON CONFLICT UPDATE` 或先讀後寫，確保 **保留** Dashboard 獨有的 `second_access` (偽裝網頁觸發) 資料，僅更新主系統欄位 (如 `click_time`, `access_time`)。
3.  **強制更新 Redis (Force Update)**：
    * **不進行比對**：不要浪費資源去讀舊的 Redis 資料來比對。
    * **直接覆蓋**：將剛寫入 DB 的完整資料轉為 JSON，直接 `SET` 到 Redis `task:{uuid}:details`。
    * **刷新 TTL**：重新設定過期時間 (重置為 1 天)。只要 Sync Worker 持續運作，資料就不會過期。

### 2.3 流程 C: 偽裝網頁即時觸發 (Trigger Path)
*觸發時機：受害者點擊釣魚連結或輸入資料*

1.  **寫入 Buffer**：將事件 (Event) 寫入 Redis List `buffer:trigger_events` (極速寫入，不擋 Request)。
2.  **[選用] 即時更新 Cache**：
    * 為了讓 Dashboard 呈現「即時動畫」效果，可嘗試更新 Redis 中的 `task:{uuid}:details`。
    * *實作提示*：若實作困難，可省略此步，等待流程 D 的 Background Worker 處理完後，下次讀取就會更新。
3.  **Buffer 落地 (Persistence)**：
    * 背景程式 (`Celery` 或 `While Loop`) 每幾秒從 `buffer:trigger_events` 取出資料。
    * 寫入 PostgreSQL `send_log_details`。
    * **寫入後再次強制更新 Redis Cache** (確保 Cache 裡的資料包含最新的觸發紀錄)。

---

## 3. Redis TTL (存活時間) 階層策略

為了避免 Redis 記憶體被塞滿，我們簡化 TTL 策略。由於 Sync Worker 會定期 (如每 30 分鐘) 執行並刷新 TTL，因此將熱資料設為 1 天是非常安全且節省資源的做法。

| 任務狀態 | 定義 | TTL 設定 | 說明 |
| :--- | :--- | :--- | :--- |
| **進行中 (Active)** | 任務狀態為「進行中」(`is_archived=False`) | **1 天 (86,400 秒)** | 只要 Sync Worker 正常運作，TTL 會不斷被重置，資料將常駐 Redis。若 Worker 失效，1 天後自動釋放記憶體。 |
| **冷資料 (Cold)** | 任務狀態為「已封存」(`is_archived=True`) | **1 小時 (3,600 秒)** | 偶爾查閱歷史資料。查一次後暫存一小時供比對，之後自動釋放記憶體。 |

### Python 實作邏輯範例 (計算 TTL)

```python
import time

def calculate_ttl(is_archived):
    if is_archived:
        return 3600  # 冷資料：1 小時
    else:
        return 86400  # 進行中：1 天 (依賴 Sync Worker 刷新)
```
## 4. 資料庫 Schema 變更 (PostgreSQL)

同前一版本，這裡再次確認關鍵的 Schema 設計。

### 4.1 `send_log_details` 表

```sql
CREATE TABLE IF NOT EXISTS send_log_details (
    id BIGSERIAL PRIMARY KEY,
    uuid TEXT NOT NULL,                
    sendtask_uuid VARCHAR(36) NOT NULL,
    
    -- 主系統同步過來的觸發紀錄
    access_time BIGINT[],
    click_time BIGINT[],
    file_time BIGINT[],
    
    -- Dashboard 獨有的觸發紀錄 (必須在同步時小心保留)
    second_access_time BIGINT[],
    second_input_time BIGINT[],
    second_input_info TEXT[], 

    CONSTRAINT fk_sendtask FOREIGN KEY(sendtask_uuid) REFERENCES sendtasks(sendtask_uuid) ON DELETE CASCADE
);

CREATE INDEX idx_details_sendtask_uuid ON send_log_details(sendtask_uuid);

```

### 4.2 `sendtasks` 表

```sql
ALTER TABLE sendtasks ADD COLUMN IF NOT EXISTS is_archived BOOLEAN DEFAULT FALSE;
```

## 5. Docker 部署配置 (Redis)

請確保 `docker-compose.yaml` 中包含 Redis 服務，且 Application 能正確連線。

```yaml
redis:
    image: redis:alpine
    container_name: fake-login-redis
    command: redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy allkeys-lru
    # 加入 maxmemory 設定，防止 Redis 吃光伺服器記憶體
    # allkeys-lru: 記憶體滿了自動刪除最久沒被使用的 Key
    volumes:
      - redis_data:/data
    healthcheck:
      test: [ "CMD", "redis-cli", "ping" ]
      interval: 5s
      timeout: 3s
      retries: 5
```

## 6. 給開發團隊 (Antigravity) 的執行指引

1. 優先實作 Schema 變更：先建立 `send_log_details` 大表。
2. 調整 Sync Worker：
    * 修改 `db_user.refresh_sendlog_stats` 邏輯。
    * 確保「寫入 DB -> 強制更新 Redis」這段原子操作 (Atomic-like) 的順序。
3. 調整 API 讀取邏輯：
    * 在 API 端點加入 `try_get_from_redis` -> `fallback_to_db` -> `write_back_to_redis` 的邏輯。
4. 實作 TTL 策略：在寫入 Redis 時，依照上述第 3 節的邏輯動態設定 `ex` (expire) 參數。
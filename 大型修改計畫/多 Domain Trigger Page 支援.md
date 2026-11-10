# 多 Domain Trigger Page 支援

## Context

目前 `TRIGGER_APP_URL` 來自 `.env` 單一變數，所有觸發頁面都共用同一個 domain。實務上需要針對**不同客戶／品牌**讓觸發頁掛在不同 domain（白標需求）。

關鍵需求：
1. 後台維護一份**全域可選的 domain 清單**
2. 建立 trigger page 時，於 **page 層級**綁定一個 domain
3. 同一台 server 服務多 domain，但**A 公司不能透過 A 的 domain 存取 B 公司綁定的 page**（軟隔離）
4. 不論透過哪個 domain 觸發，所有事件仍照原流程寫入 Redis buffer → admin-app

## 推薦架構

- **Nginx**：catch-all server block（或多個 `server_name`）統一導到 `trigger-app`；憑證以 wildcard 或 multi-SAN 處理（部署層手動設定，超出本次程式碼範圍）
- **trigger-app**：在 `/page/{page_name}/{project_id}` 與 `/qr/...` 進入時，比對 `Host` header vs DB 中該 page 綁定的 domain，不符合直接 404（不洩漏存在性）
- **admin-app**：新增 `domains` 表 + `trigger_pages.allowed_domain_id` 外鍵；URL 構造改用該 page 的 domain
- **資料庫**：兩處新欄位 + 一張新表，事件紀錄結構**完全不動**

## 變更明細

### 1. 資料庫 schema（`adminapp/backend/repository/models.py`）

新增 `Domain` model：
```python
class Domain(Base):
    __tablename__ = "domains"
    id = Column(Integer, primary_key=True, index=True)
    domain = Column(String(255), unique=True, nullable=False)  # e.g. "trigger-a.example.com"
    label = Column(Text)                                       # 顯示名稱
    is_active = Column(Boolean, default=True)
    create_time = Column(TIMESTAMP, server_default=func.now())
```

修改 [adminapp/backend/repository/models.py:177](adminapp/backend/repository/models.py#L177) `TriggerPage`：
```python
allowed_domain_id = Column(Integer, ForeignKey("domains.id"), nullable=True, index=True)
# nullable：null = 沿用 TRIGGER_APP_URL（向後相容）
```

需提供 alembic migration（或一次性 SQL）建立新表、新欄位。

### 2. Admin Backend

**新檔 `adminapp/backend/api/domain_api.py`**：標準 CRUD
- `GET /api/domain/list` → 給前端下拉選單
- `POST /api/domain/create`、`PUT /api/domain/{id}`、`DELETE /api/domain/{id}`（管理員權限）

**修改 [adminapp/backend/api/trigger_page_api.py](adminapp/backend/api/trigger_page_api.py)**：
- `/upload`、`/create_page`、`/generate_with_ai_stream` 接收 `allowed_domain_id` 並寫入
- `/list` 回傳每個 page 的 domain 資訊（JOIN domains 取 domain 字串）
- `/config` ([trigger_page_api.py:154](adminapp/backend/api/trigger_page_api.py#L154)) 保留現狀作為**預設 fallback**

### 3. Admin Frontend（[adminapp/frontend/src/app/views/qrcode/CreateUrl.jsx](adminapp/frontend/src/app/views/qrcode/CreateUrl.jsx)）

- 建立／編輯 page 時新增 **Domain 下拉選單**（呼叫 `/api/domain/list`）
- 預覽 URL 邏輯（[CreateUrl.jsx:104-142](adminapp/frontend/src/app/views/qrcode/CreateUrl.jsx#L104-L142)、180-181 行）改為：
  - 若 page 有綁定 domain → `https://{boundDomain}/page/{pageValue}/{project_id}`
  - 否則 → fallback 到原本 `triggerUrl`
- 列表頁顯示每個 page 綁定的 domain，方便管理

### 4. Trigger-app 軟隔離（核心安全層）

**修改 [triggerapp/app/routers/trigger_router.py:126-132](triggerapp/app/routers/trigger_router.py#L126-L132)** `_shared_project_detail`：

進入 handler 時：
1. 由 `page_name` 查 admin-app 共用的資料庫（trigger-app 已可訪問該 DB；若否，加 `TriggerPage` model 到 trigger-app side 或開一支內部 API）
2. 取出 `allowed_domain`
3. 比對 `request.headers.get("host")`（去 port）
4. 不符合 → `raise HTTPException(404)`（與「檔案不存在」同回應，避免列舉）
5. `allowed_domain` 為 null → 保留原行為

**修改 [triggerapp/app/api/qrcode_api.py:42](triggerapp/app/api/qrcode_api.py#L42)**：產生 QR 圖時優先用 page 綁定 domain。

事件記錄（visit / qr_visit / input → Redis buffer）**完全不需改動**——事件以 `page_name + project_id + uuid` 識別來源，不依賴 domain。

### 5. Nginx / 基礎建設

- nginx 設定 catch-all `server_name _;` 或列出所有受管 domain，全部 `proxy_pass` 到 trigger-app，保留 `Host` header（`proxy_set_header Host $host;` — 目前若已如此設定就不用動）
- SSL 憑證：建議 wildcard 或 cert-manager / certbot 多 domain 簽發（部署層作業，不在程式碼變更內）
- `docker-compose.yaml` 不需大改；`TRIGGER_APP_URL` 仍保留為「未綁定 domain 時的預設值」

## 安全考量

- 軟隔離靠 Host header 檢查；若客戶能改 hosts 偽造 Host 也只能打到自己機器，無法繞過真實 DNS → 對外攻擊面為零
- 404 而非 403：不揭露 page 是否存在，避免跨客戶列舉
- domain CRUD 限管理員權限（沿用既有 `get_current_user` + 角色檢查模式）

## 驗證方式

1. `docker-compose up`，跑 migration 建表
2. 後台新增兩個 domain（例如 `a.test.xyz`、`b.test.xyz`，本機 `/etc/hosts` 指向 trigger-app）
3. 建兩個 trigger page，各自綁不同 domain
4. 用 `curl -H "Host: a.test.xyz" http://localhost/page/page_a/proj1` → 200
5. 用 `curl -H "Host: b.test.xyz" http://localhost/page/page_a/proj1` → 404（隔離生效）
6. 在 admin-app 查 send_log_details，確認 `access_time` 等欄位有正確寫入（事件記錄不受影響）
7. 前端建立流程：選 domain → 預覽 URL → QR Code 顯示正確 domain

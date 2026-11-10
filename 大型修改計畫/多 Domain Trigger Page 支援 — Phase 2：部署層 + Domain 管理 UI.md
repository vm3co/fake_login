# 多 Domain Trigger Page 支援 — Phase 2：部署層 + Domain 管理 UI

## Context

Phase 1 已完成：`Domain` 表、`trigger_pages.allowed_domain_id`、軟隔離、`/api/domain/*` CRUD、CreateUrl.jsx 下拉選單與 URL 預覽切換、QR 圖嵌入 URL 解析。實作位於：
- [adminapp/backend/repository/models.py](adminapp/backend/repository/models.py)
- [adminapp/backend/api/domain_api.py](adminapp/backend/api/domain_api.py)
- [adminapp/backend/api/trigger_page_api.py](adminapp/backend/api/trigger_page_api.py)
- [adminapp/frontend/src/app/views/qrcode/CreateUrl.jsx](adminapp/frontend/src/app/views/qrcode/CreateUrl.jsx)
- [triggerapp/app/routers/trigger_router.py](triggerapp/app/routers/trigger_router.py)
- [triggerapp/app/api/qrcode_api.py](triggerapp/app/api/qrcode_api.py)

Phase 2 補完兩件事：
1. **部署層 (nginx)**：讓 admin 在 UI 加 domain 後，**不需動 nginx.conf**，客戶 DNS 指過來即生效
2. **Domain 管理 UI**：在後台「平台設定」下新增一頁，platform_admin 可表格式維護 domain 清單，欄位包含網域、來源公司、註記

## 設計決策

| 項目 | 決策 |
|------|------|
| Nginx 路由 | 新增 catch-all `server` block，未匹配的 hostname 全部 `proxy_pass` 到 trigger-app |
| SSL | **本期暫不處理**（未來各客戶 domain 可能走 Cloudflare 也可能走自有憑證，等具體情境再決定） |
| Domain 額外欄位 | `source_company` (Text)、`notes` (Text)，皆 nullable |
| 管理頁面權限 | `platform_admin` only（與「使用者」、「公告」同級） |
| 管理頁面位置 | 後台導覽「平台設定 → Domain 管理」 |

## 變更明細

### 1. Nginx catch-all (`nginx/nginx.conf`)

在 admin / trigger / localhost 三個 server block 之後，**追加**一個 catch-all：

```nginx
# =========================================================
#  環境 D: 動態多 Domain Catch-all (給 Trigger App 的白標 domain)
#  任何沒匹配到上面 server_name 的 hostname 都走這裡 → trigger-app
#  搭配 trigger-app 端 Host header 軟隔離，避免跨客戶存取
# =========================================================
server {
    listen 80;
    server_name _;            # catch-all

    location / {
        proxy_pass http://trigger_app_backend;
        include proxy_params_common;
    }
}
```

注意事項：
- 既有的 `listen 80 default_server`（環境 C / localhost）需保留 `default_server`，catch-all 不能再帶 `default_server`，否則重複會報錯
- 因為環境 A（admin）和 B（trigger 正式）的 `server_name` 是寫死的，會優先匹配；catch-all 只接到未在清單上的 hostname
- 不需 reload — admin-app 加 domain 純粹是 DB 寫入，下次 trigger-app 查 DB 即生效

### 2. 後端 Domain 欄位擴充

**[adminapp/backend/repository/models.py](adminapp/backend/repository/models.py)** `Domain`：
```python
source_company = Column(Text, nullable=True)
notes = Column(Text, nullable=True)
```

**[adminapp/backend/repository/database.py](adminapp/backend/repository/database.py)** `init_db` 加 idempotent migration：
```python
await conn.execute(text("ALTER TABLE domains ADD COLUMN IF NOT EXISTS source_company TEXT"))
await conn.execute(text("ALTER TABLE domains ADD COLUMN IF NOT EXISTS notes TEXT"))
```

**[adminapp/backend/api/domain_api.py](adminapp/backend/api/domain_api.py)** 調整：
- 權限：把 `_require_admin` 改為**只接受** `platform_admin`（移除 `admin`）
- `GET /list`：回傳 `source_company` 與 `notes`；也應加上 `_require_admin`（目前是任何登入者都看得到，本期改 platform_admin only）
- `POST /create`、`POST /update`：接收並寫入 `source_company`、`notes`

### 3. 前端 Domain 管理頁

**新檔 `adminapp/frontend/src/app/views/admin/DomainListPage.jsx`**：

UI 結構（仿 [UserListPage.jsx](adminapp/frontend/src/app/views/admin/UserListPage.jsx) 與 [AnnouncementPage.jsx](adminapp/frontend/src/app/views/admin/AnnouncementPage.jsx) 既有風格）：
- 標題列：「Domain 管理」+ 右側「新增 Domain」按鈕
- 表格欄位：網域 / 來源公司 / 註記 / 啟用狀態 / 建立時間 / 操作（編輯、刪除）
- 新增/編輯 Dialog：domain、label、source_company、notes、is_active switch
- 刪除確認 Dialog：使用既有 `delete` 端點，若被 page 引用會收到 409 訊息並顯示給使用者
- 用 `axios` (專案內既有模式) 呼叫 `/api/domain/list|create|update|delete`

**修改 [adminapp/frontend/src/app/routes.jsx](adminapp/frontend/src/app/routes.jsx)**：
```jsx
const DomainListPage = Loadable(lazy(() => import("app/views/admin/DomainListPage")));
// children 內加：
{ path: "/admin/domains", element: <DomainListPage />, auth: authRoles.admin },
```

**修改 [adminapp/frontend/src/app/navigations.js](adminapp/frontend/src/app/navigations.js)** 在「平台設定」children 加：
```js
{ name: "Domain 管理", iconText: "DM", icon: "language", path: "/admin/domains" },
```

### 4. CreateUrl.jsx 沿用，**不需動**

[CreateUrl.jsx](adminapp/frontend/src/app/views/qrcode/CreateUrl.jsx) 的下拉選單已從 `/api/domain/list` 抓資料；只要新欄位回傳即可顯示（目前下拉只用 `domain` 字串，新增 `source_company` 不影響）。若想在下拉項目顯示來源公司可改 `MenuItem` 文字，視需求決定。

## 安全考量

- Catch-all 只把流量轉到 trigger-app，**不會碰 admin-app**，admin 仍由其專屬 `server_name` 保護
- Trigger-app 端的 Host header 軟隔離（Phase 1 已實作）是真正的存取控制；catch-all 只負責把封包送到正確 upstream
- Domain 管理頁面限 `platform_admin`，跟使用者管理同等級

## 待辦（不在此期）

- **SSL 憑證**：等實際拿到客戶 domain 後再決定（Cloudflare proxy / Let's Encrypt / wildcard）
- **Domain 到期提醒**：本期欄位不含 `expires_at`，未來如需可再擴充

## 驗證方式

1. `docker compose up --build`，admin-app 啟動時跑 migration 加入 `source_company`、`notes` 欄位
2. 登入 `platform_admin`，左側「平台設定」應出現「Domain 管理」
3. 在新頁面新增 domain `a.test.xyz`，填來源公司「A 公司」、註記任意文字
4. 本機 `/etc/hosts` 加：
   ```
   127.0.0.1 a.test.xyz
   ```
5. 在 `/qrcode` 建立或編輯一個 page，綁定 `a.test.xyz`
6. `curl -H "Host: a.test.xyz" http://localhost/page/<pageValue>/test` → 200（catch-all + Host check 通過）
7. `curl -H "Host: random.test.xyz" http://localhost/page/<pageValue>/test` → 404（隔離生效）
8. `curl http://localhost/dashboard` 用 localhost 訪問 → 仍走原 admin / trigger 路由，未受 catch-all 影響
9. Domain 管理頁刪除「正在被 page 使用」的 domain → 看到 409 錯誤提示

# 社交工程演練與管理系統 (Social Engineering & Dashboard)

這是一個用於社交工程演練的模擬系統，包含受測者觸發端 (Trigger App) 與管理者儀表板 (Admin App)。系統採用微服務架構，透過 Docker Compose 進行部署，並使用 Nginx 作為反向代理。

## 核心功能

- **Trigger App (受測者端)**：
  - 模擬登入頁面，記錄受測者的 IP 與輸入資料 (如 Email)。
  - 支援 QRCode 生成與追蹤。
  - 記錄使用者行為流程：開啟信件 -> 掃描 QRCode -> 點擊連結 -> 提交資料。

- **Admin App (管理端)**：
  - 提供視覺化儀表板 (Dashboard)。
  - 顯示任務列表與詳細統計數據 (寄送數、開啟數、點擊數、提交數等)。
  - 支援資料匯出 (CSV)。

## 技術架構

本專案使用以下技術堆疊：

- **Frontend (Admin)**: React (Vite), Material UI (MUI), ECharts
- **Backend (Admin & Trigger)**: Python FastAPI
- **Database**: PostgreSQL 16
- **Infrastructure**: Docker, Docker Compose, Nginx

## 專案結構

```
.
├── adminapp/       # 管理者後台 (包含 Frontend 與 Backend)
│   ├── frontend/   # React 前端原始碼
│   └── ...         # Python Backend 原始碼
├── triggerapp/     # 受測者觸發端 (Python FastAPI)
├── nginx/          # Nginx 設定檔
├── data/           # 資料庫資料 (Docker Volume)
├── pg_backup/      # 資料庫備份
├── docker-compose.yaml # Docker 編排檔
└── start.bat / start.sh # 啟動腳本
```

## 快速開始

### 任務版本同步與備援區（尚未正式上線）

- Dashboard 提供今日任務、全部任務與獨立備援三個視圖；客戶現行任務管理不混入備援。
- 相同來源 UUID 的建立時間變更，會先保存固定舊版快照，再匯入乾淨新版；同版本更新保留本地事件。每份歷史使用獨立 backup_id，不能用來源 UUID 代替。
- 備援列表、唯讀明細、統計、樣板 metadata 與完整 Excel 都依該份快照讀取，不回退讀取同 UUID 現行資料。授權依備援當時的組織，不因現行任務換組織而改變。
- 「備援後重新匯入」須確認並明確選取任務；不依 email 去重、不自動修復全庫。人工同版本重匯若沿用明細 UUID，晚到事件仍可能對應現行資料，不提供郵件世代辨識保證。
- 備援是同一 PostgreSQL 內的歷史資料，不是獨立災難備份；沒有因此新增定期備份或自動刪除政策。
- 正式切換前必須完成一次受控完整備份及獨立還原驗證，安排停寫／事件 queue 邊界及回復點。不可直接用下方啟動／重啟腳本當作版本升級程序，尤其不得選刪除 volume 的選項。

操作要求見 [TSB-017](大型修改計畫/任務同步版本化與獨立備援區/17_TSB-017_上線與回復作業.md)。僅合成資料的準備演練可從專案目錄執行：

```sh
bash adminapp/backend/scripts/tsb017_drill.sh
```

需要 Docker 與本機已有的 `fake_login-admin-app:latest`、`postgres:16-bookworm` 映像。工具使用已提交 HEAD 的程式，拒絕占用既有同名容器／網路，建立專用 tmpfs 資料庫，不讀 `.env`、不啟動 admin-app，也不操作 Compose。輸出位於限制權限的暫存目錄，僅含合成資料。這不替代正式資料庫的備份／還原驗證。

### 前置需求

- [Docker](https://www.docker.com/)
- [Docker Compose](https://docs.docker.com/compose/)

### 啟動服務

請依據您的作業系統執行對應的啟動腳本：

**Windows:**
```cmd
start.bat
```

**Linux / Mac:**
```bash
./start.sh
```

### 存取服務

啟動後，您可以透過瀏覽器存取以下服務 (預設使用 Port 80)：

- **管理後台 (Admin Dashboard)**: [http://localhost/](http://localhost/)
- **受測者觸發頁面 (Trigger App)**: [http://localhost/trigger/](http://localhost/trigger/)
  - *注意：Trigger App 通常需要配合特定的 UUID 參數使用，例如信件中的連結。*

## 開發說明

### 環境變數 (.env)
專案根目錄下的 `.env` 檔案包含資料庫連線資訊與其他設定，請確保該檔案存在並設定正確。

### 重新啟動
若修改了程式碼或設定，可使用以下腳本重新啟動服務：

**Windows:**
```cmd
restart.bat
```

**Linux / Mac:**
```bash
./restart.sh
```

## 路由規則 (Nginx)

Nginx 負責將請求分派至不同的服務：

- `/` -> **Admin Frontend** (靜態檔案)
- `/api/` -> **Admin Backend** (API 請求)
- `/trigger/` -> **Trigger App**

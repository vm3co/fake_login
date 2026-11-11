# TSB-010：備援查閱、匯出與刪除 API

| 項目 | 內容 |
| --- | --- |
| 狀態 | 完成（2026-11-11；隔離驗收，未部署） |
| 優先／工作量 | P1／L |
| 前置 | TSB-004 |
| 下游 | TSB-011、TSB-013、TSB-014 |
| 部署限制 | 全部資料端點驗證權限後才提供正式備援管理 |

共同需求見 [總表](00_總表與執行計畫.md)。

## 目標

以 `backup_id` 精確查閱／匯出／刪除歷史版本，不與同 UUID 新版混淆。重建檢查工作另由 TSB-011 負責，本票先定義觀測欄位和篩選契約。

## API 契約草案

| 端點 | 用途 |
| --- | --- |
| `GET /api/task_backups` | 有權備援列表、搜尋、分頁、排序、重建／最近檢查狀態篩選 |
| `GET /api/task_backups/{backup_id}` | 完整任務 metadata、固定統計與樣板 metadata snapshot |
| `POST /api/task_backups/{backup_id}/details` | 明細分頁、搜尋、日期、狀態、IP 排除等既有能力 |
| `GET /api/task_backups/{backup_id}/export.xlsx` | 從該份備援產生本地 Excel，不請求主系統 |
| `DELETE /api/task_backups/{backup_id}` | 經授權永久刪除這一份備援 |

實作時可依既有 API 慣例調整方法或命名，但須先更新本票並交付固定契約，不能讓前端自行猜。

## 權限規則

- 登入依既有 `get_current_user`，scope 依可信登入資料，不採用使用者自傳 org。
- `admin_role=True` 全範圍；一般 user 需與備援保存的 owner org 有交集；空 org／customer 拒絕。
- 列表、統計、明細、匯出、刪除都用相同的 `require_backup_access`／scope 查詢，不只在前端隱藏。
- 不用同 UUID 現行新版的 org 授權舊備援；新舊版本 org 不同時也不能跨讀。
- 不在找不到備援時 fallback 到現行資料；原始 UUID 不能代替 `backup_id`。
- 刪除只 cascade 該 backup_id 的標頭／明細，不動現行任務、其他備援或客戶 UUID 關聯。

## 工作項目

1. 新增備援 router，註冊於 API 路徑，避免落入 SPA static fallback。
2. 列表回傳原始 UUID、來源建立時間、備援時間／原因、筆數、組織權限下的可用動作與遠端觀測狀態；不把大量明細塞入列表。
3. 將必要的明細查詢／篩選／Excel 處理抽成接受資料來源的局部共用函式；不複製整個 `data_api.py`，也不重寫全站匯出。
4. 備援只讀其固定統計與樣板 snapshot，提供統計基準時間；不以今天重算歷史 today 數字，不用現行 `Mtmpl` 補成歷史真相。
5. 保留原始事件陣列，UI 可投影最後一次與次數；匯出內容及筆數對應所選 backup_id，檔名含版本／備援識別避免同名覆蓋。
6. 成功 0 筆明細是成功的空資料，不回通用查詢錯誤；不存在／未授權採既有一致的錯誤策略。
7. 不提供修改快照或清除單筆觸發端點；合法刪除有明確結果，便於列表刷新。

## 修改位置

- 預計新增 `adminapp/backend/api/task_backup_api.py`。
- [main.py](../../adminapp/backend/main.py)：router 註冊。
- [data_api.py](../../adminapp/backend/api/data_api.py)：`_query_sendlog_details` 與 Excel 共用處理。
- [excel_utils.py](../../adminapp/backend/services/excel_utils.py)：可重用的既有匯出工具。
- [test_sendtask_scope_api.py](../../adminapp/backend/tests/api/test_sendtask_scope_api.py)：權限測試慣例參考；可新增專用備援 API 測試。

## 驗收條件

- [x] 同 UUID 的現行與多份備援，所有查詢／匯出都精確命中指定 backup_id。
- [x] 每條 API 都測 admin、同 org user、跨 org、空 org、customer 及未登入。
- [x] 新版 org 改變不授權讀舊備援；跨 org 不洩漏列表筆數／明細。
- [x] 同 org user 可刪備援，不被現行任務僅 admin 刪除規則誤擋。
- [x] 刪備援 X 不影響現行、新版或備援 Y。
- [x] 樣板刪除／變更後，備援顯示與匯出仍使用快照；遠端斷線時仍可本地匯出。
- [x] 重用函式後原有現行明細／Excel 測試不回歸。

## 聚焦驗證與交付

API 測試包含身份矩陣、分頁與空資料，Excel 測試解析實際輸出而不只檢查 HTTP 200。交付請求／回應範例、篩選列舉與錯誤語意給 TSB-011、013、014。

## 執行紀錄

### 固定 API 與授權契約

- 五個端點依上表實作，router 在 SPA mount 前註冊。共用 `task_backup_access.backup_scope/scoped_backups/require_backup_access`；customer 一律403，空或不可信 user org 為403，未登入沿既有401。admin_role=True 全範圍，一般 user 只查 owner_gids 有交集的備援。無權與不存在的單份備援均404，不採前端 org、不查現行或 Redis、不以 source_task_uuid 代替 backup_id。
- 列表參數：page>=1、page_size=1..200（預設20）、search（名稱或來源UUID）、sort=asc/desc、sort_by=backed_up_at/source_create_ut/sendtask_id/last_remote_checked_at、recreated 布林、remote_status=unchecked/present/missing/error、reason=remote_missing/remote_recreated/manual_reload、backed_up_from/backed_up_to（YYYY-MM-DD，台北日期）。日期終日以次日零時排他處理。
- 列表回 `{status:"success",data:[...],total_count,page,page_size}`；先套 org 再算總數，穩定排序附 backup_id。每列含 backup_id、source_task_uuid、source_create_ut、source_local_generation_id、sendtask_id、owner_gids、backed_up_at、reason、snapshot_schema_version、stats_snapshot_at、明細筆數 detail_count、遠端觀測欄位及 actions.read/export/delete。列表不含大快照或事件明細；列表以 repeatable-read 保持計數／資料一致。
- 單份 GET 回 `{status:"success",data:{...標頭,task_snapshot,stats_snapshot,mail_template_snapshot}}`。缺統計或 stats_snapshot_at 保留 null，不用今天重算歷史統計；缺樣板 metadata 保留 null，不讀現行 Mtmpl 補值。
- 明細 POST body 可省略欄位，預設 page=1、rowsPerPage=20、acctControl=[true,true,true,true,true]、resultType=all、sort=desc、sortBy=plan_time、paginate=true。rowsPerPage 上限200；只允許分頁，不接受 paginate=false。未知欄位拒絕422，不能用 body 的 sendtask_uuid 改來源。
- 明細支援 searchText、dateFrom/dateTo（台北寄送日期）、resultType=all/send/notyet/failed/notTriggered/triggered、五項 acctControl、showAccessed/showClicked/showFiled、filterIp（逗點分隔精確或星號IP）、sortBy=uuid/target_email/person_info/plan_time/send_time/send_res。不合法日期、倒置日期、排序與分頁拒絕422。
- 明細回 `{status:"success",data:[{...原始欄位,display:{...最後事件及次數}}],total_count,page,page_size}`。原始事件陣列永遠完整；filterIp 只作用於 display 的對齊事件投影，不修改備援、不刪除受測者、不改資料列 total_count。沿既有寄送／觸發條件語意，不在本票重設計觸發判斷。合法0筆或頁面超出範圍仍 success，total_count 保留實際符合數。
- GET export.xlsx 固定匯出整份備援，不套明細分頁／畫面篩選；檔名 `task-backup-{backup_id}.xlsx`。六個工作表 info/task/stats/templates/details/overflow，事件陣列與JSON用JSON文字保留，固定統計直接來自快照。超過30000字元的欄位拆到 overflow，包含來源表／列／欄／片段順序，避免Excel靜默截斷；字串強制文字型別，不執行公式。無郵件HTML快照時不補抓主系統。
- DELETE 必須 `?confirm_delete=true`（精確小寫字串），缺少確認回400；先授權再檢查確認。成功回 `{status:"success",deleted_backup_id,backups_changed:true}`。交易鎖住標頭後只刪指定 TaskBackup，由FK cascade刪該份明細，不動現行任務、其他備援、CustomerTask／CustomerAcct或008防重紀錄。重複刪已不存在備援回404。
- 單份讀取／匯出／刪除在交易內鎖標頭，避免匯出時被刪成半份快照；Excel在取得完整固定資料後於threadpool產生，不占用交易等待檔案生成。尚未實作011的主系統檢查工作，列表只公開既有觀測與篩選欄位。

### 共用處理與相容性

- 新增 `sendlog_query.py`，查詢接受 model/source_condition，事件投影以深拷貝處理；現行 data_api._query_sendlog_details 改代理，保留原陣列壓最後一筆與次數回應。備援使用同函式但指定 TaskBackupDetail.backup_id，另保留原始事件。
- `excel_utils.backup_workbook` 接受已取得的備援資料，不用整表名稱或現行cache，也不複製現行JESS遠端查詢流程。原有現行明細／Excel輸出測試已回歸。
- data_api 原有其他未提交使用者變更保留；本票只提交查詢函式抽取，不納入樣板權重等功能草稿。不提供修改快照／清除單筆觸發端點。

### 驗證與限制

- 環境：internal `tsb010-test-net`、全新PostgreSQL16 `tsb010-postgres`、專用tsb_schema_test、tmpfs資料磁碟；一次性admin image唯讀掛程式、Logger用tmpfs，未啟動lifespan、未操作現行DB或正式服務。備援功能無主系統／Redis依賴。
- 聚焦 `python -m pytest backend/tests/api/test_task_backup_api.py backend/tests/services/test_sendlog_query.py backend/tests/api/test_sendtask_scope_api.py backend/tests/api/test_sendlog_link_export.py -q --tb=short -p no:cacheprovider`：83 passed。每條API均涵蓋admin／同org／跨org／空org／customer／未登入；真PG驗多版本、刪除隔離、台北日期、分頁、空資料與IP投影。實際解析xlsx驗完整明細、固定統計、刪除後樣板快照、長事件分段及公式安全。
- 完整回歸為009的19個測試檔，再加本票 `test_task_backup_api.py`、`test_sendlog_query.py` 與原有 `test_sendlog_link_export.py`，相同pytest旗標：435 passed、0 skipped、0 deselected，8項既有依賴／pandas警告。編輯器本票診斷無錯誤。
- 首次Excel測試錯假設第一列樣板必有資料，實際第一列為已知缺失快照；改依template_uuid驗證缺失與已保存metadata，未用現行資料補值。修正後同組通過。
- 本票尚未提供前端備援列表／唯讀明細（013／014）、遠端檢查（011）或正式部署。匯出為記憶體完整xlsx，超大型備援的容量／工作時間需在016依實際資料驗收；不宣稱無限容量。正式開放仍需其餘票與017備份／還原及一致切換門檻；未啟動服務、不push。
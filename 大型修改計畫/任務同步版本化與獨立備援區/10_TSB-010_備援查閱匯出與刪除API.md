# TSB-010：備援查閱、匯出與刪除 API

| 項目 | 內容 |
| --- | --- |
| 狀態 | 待開始 |
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

- [ ] 同 UUID 的現行與多份備援，所有查詢／匯出都精確命中指定 backup_id。
- [ ] 每條 API 都測 admin、同 org user、跨 org、空 org、customer 及未登入。
- [ ] 新版 org 改變不授權讀舊備援；跨 org 不洩漏列表筆數／明細。
- [ ] 同 org user 可刪備援，不被現行任務僅 admin 刪除規則誤擋。
- [ ] 刪備援 X 不影響現行、新版或備援 Y。
- [ ] 樣板刪除／變更後，備援顯示與匯出仍使用快照；遠端斷線時仍可本地匯出。
- [ ] 重用函式後原有現行明細／Excel 測試不回歸。

## 聚焦驗證與交付

API 測試包含身份矩陣、分頁與空資料，Excel 測試解析實際輸出而不只檢查 HTTP 200。交付請求／回應範例、篩選列舉與錯誤語意給 TSB-011、013、014。

## 執行紀錄

- 實際變更：待填。
- 測試指令與結果：待填。
- 未完成／阻礙／下游注意事項：待填。
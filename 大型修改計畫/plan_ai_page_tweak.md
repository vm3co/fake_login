# AI 生成網頁後微調功能 (Title & Logo) 實施計畫

## 核心思路：預留佔位符 + 前端安全替換 + 圖片壓縮預覽

針對「AI 生成網頁後，讓使用者修改 Title 與上傳圖標」的需求，為提升效率且不額外消耗 AI Token，最佳做法是：**在前端收到 AI 生成的 HTML 字串後，利用瀏覽器的 DOM 解析能力（DOMParser）直接修改 HTML 內容，再將修改後的檔案上傳到後端儲存。**
為了兼顧結構穩定性、安全性與效能，本計畫已針對 DOM 序列化、LLM 幻覺容錯、Base64 體積過大等潛在問題進行強化。

1. **約定結構與強制編碼**：後端 Prompt 明確要求 `<meta charset="UTF-8">` 與特定 Logo 容器。
2. **即時預覽與微調介面**：前端開啟「微調與儲存對話框 (Tweak Dialog)」，**內建 iframe 即時預覽**修改結果，避免盲改。
3. **圖片壓縮與安全掛載**：上傳圖片先經 Canvas 壓縮再轉 Base64，並透過標準 DOM API (`createElement`, `setAttribute`) 注入，防止 XSS 及檔案暴肥。
4. **Doctype 與編碼還原**：序列化時手動補回 `<!DOCTYPE html>`，並以 `charset=utf-8` 封裝 File。

---

## 詳細實施步驟

### 階段一：後端調整 (修改 `trigger_page_api.py`)
1. **修改 `get_system_prompt` 函式**：
   在系統提示詞中加入明確的結構約束，讓 AI 準備好易於替換的 DOM 節點。
   * 要求必須包含 `<meta charset="UTF-8">` 以避免前端序列化後產生亂碼 (Mojibake)。
   * 要求必須有標準的 `<title>登入</title>`。
   * 要求在表單或畫面的頂部放置一個 Logo 容器：
     `"如果你需要繪製品牌 Logo 或預留圖片位置，請務必將其包裝在一個具有 ID 的容器中，例如 <div id="custom-brand-logo"></div>，以利系統後續替換。"`

### 階段二：前端 UI 流程調整 (修改 `CreateUrl.jsx`)
1. **新增 State 變數**：
   新增用於微調的狀態，例如 `tweakTitle` (字串)、`tweakLogo` (File 物件)，以及保留 AI 原始生成的 HTML 字串 `aiRawHtml`。
   新增 `previewHtml` 用於綁定 Dialog 中的 iframe 即時預覽。
2. **攔截 AI 生成完成事件**：
   在 `handleGenerateWithAi` 中，當收到 `data.type === 'complete'` 時，先將 HTML 存入 `aiRawHtml`，接著不直接開啟 `openUploadDialog`，而是開啟專屬的**「AI 網頁微調與儲存對話框 (Tweak Dialog)」**。
3. **建立「AI 網頁微調與儲存」對話框**：
   設計一個新的 Dialog 元件，包含：
   * **頁面基礎資訊**：名稱 (pageLabel)、網址 ID (pageValue)、網域綁定。
   * **內容微調**：
     * 網頁標題 (Title) 輸入框。
     * 自訂圖標 (Logo) 的上傳按鈕：**加入 MIME 限制 `accept="image/png, image/jpeg, image/webp, image/svg+xml"`**。
   * **即時預覽區 (Preview)**：
     * 放置一個 `<iframe srcDoc={previewHtml}>`，讓使用者每次修改 Title 或 Logo 後，即時看到替換後的畫面。

### 階段三：前端替換邏輯與儲存 (修改 `CreateUrl.jsx`)
設定一個 `generateFinalHtml()` 函式，在使用者編輯時更新預覽，並在點擊儲存時產生最終結果：
1. **圖片壓縮與轉 Base64**：
   若有上傳圖檔，透過 `Image` 與 `canvas` 將圖片縮放 (例如限制 Max Width/Height = 300px)，再轉換為 Base64 格式，避免最終 HTML 檔案過大。
2. **DOM 解析與安全替換**：
   使用 `new DOMParser().parseFromString(aiRawHtml, "text/html")` 將 HTML 轉為 DOM 物件。
   * **替換 Title**：`dom.title = tweakTitle`。
   * **替換 Logo (具備 Fallback 機制)**：
     嘗試尋找 `dom.getElementById('custom-brand-logo')`。
     **若找不到 (LLM 幻覺)**：退而求其次尋找 `dom.getElementById('login-form')` 或 `dom.querySelector('form')`，將 Logo 插入在其最上方。
     **安全注入**：`const img = dom.createElement('img'); img.setAttribute('src', base64Image);`，然後掛載到節點內，絕對不使用 `innerHTML` 拼接。
3. **序列化、補全與儲存**：
   取得 `dom.documentElement.outerHTML` 後，**必須在開頭補上 `<!DOCTYPE html>\n`**，防止瀏覽器進入 Quirks Mode (怪異模式) 導致 CSS 跑版。
   利用 `new File([finalHtmlString], filename, { type: 'text/html;charset=utf-8' })` 打裝，確保以 UTF-8 送出避免亂碼。
   最後呼叫 `/api/trigger_page/upload` API。

---

## 預期效益
* **省成本且極高效率**：前端替換毫秒級完成，包含預覽與壓縮皆不需後端運算或重新呼叫 LLM。
* **架構乾淨**：單一 HTML 檔案包裝所有內容 (含 Base64 圖片)，無破圖風險，且資料庫不需新增多餘的圖片欄位。
* **高穩健性**：兼顧了 Doctype、編碼 (Mojibake)、安全注入與 LLM 無法完全遵守結構的 fallback 容錯。
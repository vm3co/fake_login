# LiteLLM Gateway 使用說明

給要串接本 gateway 的開發者。內容以 2026-08-06 對 `192.168.0.111` 的實測為準。
多數範例已實際執行過；**未經驗證的部分會明確標示**，請留意這些標註。

本 gateway 同時提供**本地 Ollama 模型**與 **ChatGPT 訂閱模型**，兩者用同一組
base URL 與 API key，切換模型只需改 `model` 欄位。

---

## 目錄

1. [30 秒上手](#1-30-秒上手)
2. [連線與認證](#2-連線與認證)
3. [可用模型](#3-可用模型)
4. [可用端點](#4-可用端點)
5. [呼叫範例](#5-呼叫範例)
6. [使用前必讀](#6-使用前必讀)
7. [Codex CLI 對接](#7-codex-cli-對接)
8. [限流與錯誤處理](#8-限流與錯誤處理)
9. [模型選型建議](#9-模型選型建議)
10. [疑難排解](#10-疑難排解)

---

## 1. 30 秒上手

```bash
pip install openai
export LITELLM_API_KEY="<你的 virtual key>"
```

```python
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["LITELLM_API_KEY"],
    base_url="http://192.168.0.111/v1",
)

# 注意 stream=True —— ChatGPT 模型不加會失敗，詳見第 6 節
stream = client.chat.completions.create(
    model="gpt-5.6-terra",
    messages=[{"role": "user", "content": "你好"}],
    stream=True,
)

for chunk in stream:
    if chunk.choices and chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

把 `model` 換成 `gemma4-12b` 就是走本地模型，其餘程式碼完全相同。

---

## 2. 連線與認證

| 項目 | 值 |
|---|---|
| Base URL | `http://192.168.0.111/v1` |
| 認證方式 | HTTP header `Authorization: Bearer <key>` |
| API 相容性 | OpenAI API（同時支援 Anthropic Messages 格式，見第 4 節）|

Base URL 的 80 埠是 nginx，反向代理到 LiteLLM 的 4000 埠。

**本 gateway 僅供內網使用**，不對外開放。從公司網路以外的環境連不上。

API key 是 LiteLLM 的 **virtual key**（`sk-` 開頭），由 gateway 管理者發放，
不是 OpenAI 官方的 API key，也不能拿去打 `api.openai.com`。

本文所有範例都從環境變數讀取 key，**請勿把 key 寫死在程式碼或提交進版控**。

因為介面與 OpenAI 相容，任何支援自訂 `base_url` 的工具都能接：
官方 OpenAI SDK（Python / Node）、LangChain、LlamaIndex、Continue、Cline 等。

---

## 3. 可用模型

`model` 欄位要填的是下表的 **group 名稱**。

> 表中的 **rpm 上限是全 gateway 共用的**，不是每把 key 各自的配額。
> 別人正在大量呼叫時你也會被擋下 —— `gpt-5.6-sol` 的 rpm 只有 5，請特別留意。

### 本地 Ollama 模型

| group | 用途 | 圖片輸入 | rpm 上限 | timeout |
|---|---|---|---|---|
| `gemma4-12b` | 通用主力。日常對話、翻譯、一般推理 | 不支援 | 60 | 600s |
| `gemma4-e4b` | 輕量極快，適合低延遲的簡短回應 | 不支援 | 90 | 210s |
| `translategemma` | 翻譯專用，非通用對話模型 | 不支援 | 60 | 900s |

本地模型不耗訂閱額度，推論在內網完成。首次呼叫或模型換出後會有載入延遲
（實測 `gemma4-12b` 冷啟動可達 26 秒，熱機後約 1–2 秒）。

### ChatGPT 訂閱模型

| group | 用途 | 圖片輸入 | rpm 上限 | timeout |
|---|---|---|---|---|
| `gpt-5.6-terra` | **日常主力**，balanced for everyday work | 支援 | 10 | 600s |
| `gpt-5.6-sol` | 旗艦，複雜編碼與跨檔案重構，最耗額度 | 支援 | 5 | 900s |
| `gpt-5.6-luna` | 高頻小任務、批次處理，快且省 | 支援 | 20 | 180s |
| `gpt-5.5` | 前代旗艦，行為對照與回退用 | 支援 | 5 | 900s |

這四個共用同一個 ChatGPT 訂閱帳號的額度。

**延遲**：實測約 1–7 秒，但測試條件是「回覆兩個字元」的極短 prompt，
僅代表連線與首個 token 的成本。實際長回應會顯著更久。

**Context window**：`GET /v1/models` 回報這四個 group 的
`max_input_tokens` 為 1,050,000、`max_output_tokens` 為 128,000。
本地模型未回報此欄位，實際上限依 Ollama 端的模型設定而定。

**圖片輸入**：僅 `gpt-5.6-luna` 經實測驗證（見 [5.5](#55-圖片輸入)）。
其餘三個依 OpenAI 官方文件標示為支援，本文件未逐一測試。

> **模型清單會變動，而且變得很快。** ChatGPT 可用的 slug 由 OpenAI 政策決定：
> `gpt-5.2` 與 `gpt-5.3-codex` 已停用，`gpt-5.4` 也將於 2026-08-31 退場。
> 這幾個都已不在本 gateway 的清單中，列於此處只是說明汰換速度 ——
> **請不要把 model 名稱寫死**，或至少確保它容易修改。
> 不確定當下可用什麼，就打 `GET /v1/models`。
> 背景說明見 [research/2026-08-05-chatgpt-pro-litellm-models.md](research/2026-08-05-chatgpt-pro-litellm-models.md)。

---

## 4. 可用端點

以下皆為實測結果（2026-08-06）。

| 端點 | 方法 | 可用性 | 說明 |
|---|---|---|---|
| `/v1/models` | GET | 可用 | 列出你的 key 能用的所有 model group |
| `/v1/chat/completions` | POST | 可用 | **主要路徑**，OpenAI Chat Completions 格式 |
| `/v1/responses` | POST | 可用 | OpenAI Responses 格式，一律回 SSE |
| `/v1/messages` | POST | 可用 | **Anthropic Messages 格式**，需 `stream: true` |
| `/health/liveliness` | GET | 可用 | 存活檢查，監控用 |
| `/health/readiness` | GET | 可用 | 就緒檢查，監控用 |
| `/model/info` | GET | 不可用 | 回 403；需要 master key，一般 virtual key 無權限 |

一般接入用 `/v1/chat/completions` 即可，它對本地與 ChatGPT 兩類模型都適用，
生態系支援也最廣。

---

## 5. 呼叫範例

以下範例都假設已建立 client：

```python
import os
from openai import OpenAI

BASE_URL = os.getenv("LITELLM_BASE_URL", "http://192.168.0.111/v1")
API_KEY = os.environ["LITELLM_API_KEY"]

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
```

### 5.1 Chat Completions（推薦）

```python
def ask(client, model, prompt):
    """對任一模型發問並串流輸出，本地與 ChatGPT 模型皆適用。"""
    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
    )
    result = ""
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            piece = chunk.choices[0].delta.content
            print(piece, end="", flush=True)
            result += piece
    return result
```

系統角色與多輪對話與 OpenAI 完全相同：

```python
messages = [
    {"role": "system", "content": "你是資深 Python 工程師，回答精簡。"},
    {"role": "user", "content": "如何用 Python 實作快速排序？"},
]
```

多輪對話由客戶端自行維護 `messages` 陣列，把每輪的回應以
`{"role": "assistant", "content": ...}` 附加回去即可。

### 5.2 非串流呼叫（限本地模型）

> **ChatGPT 模型不能用非串流**，會在等待數十秒後回 500。
> 原因與錯誤訊息見 [6.1](#61-chatgpt-模型必須-streamtrue)。

本地模型則兩種模式皆可：

```python
response = client.chat.completions.create(
    model="gemma4-e4b",
    messages=[{"role": "user", "content": "Say OK"}],
)
print(response.choices[0].message.content)
```

即便如此，仍建議一律使用串流 —— 這樣同一份程式碼才能在兩類模型間自由切換。

### 5.3 Responses API

```python
stream = client.responses.create(
    model="gpt-5.6-luna",
    # input 必須是 list，傳字串會被上游拒絕
    input=[{"role": "user", "content": [{"type": "input_text", "text": "Say OK"}]}],
    stream=True,
)

text = ""
for event in stream:
    if getattr(event, "type", "") == "response.output_text.delta":
        text += event.delta
print(text)
```

除非你需要 Responses 才有的功能，否則建議用 Chat Completions —— 限制較少。

### 5.4 Anthropic Messages 格式

若你的工具是為 Anthropic API 寫的，可以直接打 `/v1/messages`：

```python
import httpx

response = httpx.post(
    f"{BASE_URL}/messages",
    headers={"Authorization": f"Bearer {API_KEY}",
             "Content-Type": "application/json"},
    json={
        "model": "gpt-5.6-luna",
        "max_tokens": 256,
        "messages": [{"role": "user", "content": "Say OK"}],
        "stream": True,          # ChatGPT 模型必須加
    },
    timeout=120,
)
```

回傳為 Anthropic 的 SSE 事件格式（`message_start`、`content_block_delta` …）。

同樣地，ChatGPT 模型走這個端點時**非串流會回 500**，本地模型則兩種皆可。

> 理論上這代表 Claude Code 等 Anthropic 生態工具可以透過
> `ANTHROPIC_BASE_URL` 指向本 gateway，但**端到端流程未經驗證**，
> 已知 LiteLLM 經此 adapter 轉送時會多帶 `user`、`context_management`
> 等 Codex 後端不接受的參數（[litellm#21193](https://github.com/BerriAI/litellm/issues/21193)）。

### 5.5 圖片輸入

**僅 ChatGPT 模型支援圖片輸入**，本地模型不支援。把圖片轉 base64 內嵌：

```python
import base64

with open("photo.jpg", "rb") as f:
    b64 = base64.b64encode(f.read()).decode()

messages = [{
    "role": "user",
    "content": [
        {"type": "text", "text": "這張圖片裡有什麼？"},
        {"type": "image_url",
         "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
    ],
}]
```

### 5.6 curl

```bash
# 列出可用模型
curl -s http://192.168.0.111/v1/models \
  -H "Authorization: Bearer $LITELLM_API_KEY"

# 串流對話
curl -N http://192.168.0.111/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
        "model": "gpt-5.6-terra",
        "messages": [{"role": "user", "content": "你好"}],
        "stream": true
      }'
```

---

## 6. 使用前必讀

兩個會讓程式壞掉的限制，以及一個你該知道的設計決策。

### 6.1 ChatGPT 模型必須 `stream=True`

LiteLLM 對 `chatgpt/` provider **一律以 SSE 回應**，即使請求沒有要求串流。
於是非串流呼叫會拿到它自己無法解析的內容：

```
500 litellm.APIConnectionError:
ChatgptException - Unknown items in responses API response: []
```

失敗前會先卡住數十秒（單次觀測約 20 秒），很容易被誤判成逾時。

**本地 Ollama 模型不受影響**，串流與非串流都正常。
但為了讓程式碼在兩類模型間可以互換，建議**一律使用串流**。

### 6.2 `/v1/responses` 的 `input` 必須是 list

傳字串會被 ChatGPT 後端直接擋下：

```
400 {"detail":"Input must be a list"}
```

正確寫法見 [5.3](#53-responses-api)。Chat Completions 無此問題。

### 6.3 沒有 fallback，失敗就是失敗

本 gateway **刻意不設定 fallback**：額度用盡或模型故障時，錯誤直接回傳，
不會靜默改用其他模型。這是為了讓你清楚知道自己碰到了限制，
而不是在不知情的狀況下拿到降級的回應、或消耗掉其他模型的額度。

換句話說，**要不要退而求其次由你的程式決定**，gateway 不替你做主。
若你的應用需要高可用，請自行在客戶端實作「主模型失敗就改用備援模型」的邏輯。

重試行為與錯誤對照見[第 8 節](#8-限流與錯誤處理)。

---

## 7. Codex CLI 對接

Codex CLI 可以把本 gateway 當成自訂 provider 使用。編輯 `~/.codex/config.toml`：

```toml
[model_providers.internal]
name = "Internal Gateway"
base_url = "http://192.168.0.111/v1"
wire_api = "responses"              # Codex CLI 對本 provider 使用的協定，見下方說明
request_max_retries = 1
stream_max_retries = 1
stream_idle_timeout_ms = 300000

[profiles.daily]
model_provider = "internal"
model = "gpt-5.6-terra"             # 填 group 名稱，不是 chatgpt/ 後面那段

[profiles.heavy]
model_provider = "internal"
model = "gpt-5.6-sol"
```

用 `codex --profile daily` 指定，或在檔案最上方設 `profile = "daily"` 當預設。

若 gateway 前面有存取控制（例如 Cloudflare Access），用 `env_http_headers`
把 token 帶進去：

```toml
env_http_headers = { "CF-Access-Token" = "CF_ACCESS_TOKEN" }
```

> **未實測。** 上述設定依 Codex CLI 的 provider 機制撰寫，
> 但本文件未對 Codex CLI 做端到端驗證。`wire_api = "responses"`
> 對應的 `/v1/responses` 端點本身已驗證可用（見 [5.3](#53-responses-api)）。

### 為什麼這裡是 `responses`，第 4 節卻說 Chat Completions 也能用？

兩者不衝突，因為講的是不同層：

- **上游**（`https://chatgpt.com/backend-api/codex`）只接受 Responses API。
- **LiteLLM** 會把 Chat Completions 請求橋接成 Responses 再送出，
  所以透過本 gateway，兩種格式都能用（見[第 4 節](#4-可用端點)）。
- **Codex CLI** 這個設定指的是它自己要用哪種協定跟 gateway 溝通。
  設 `responses` 是最直接的路徑，少一層轉換。

### 關於 Codex 專用模型

`gpt-5.3-codex` 已被 OpenAI 對 ChatGPT 帳號停用，呼叫會得到
`The 'gpt-5.3-codex' model is not supported when using Codex with a ChatGPT account.`

目前唯一還存活的 codex 品牌模型是 `gpt-5.3-codex-spark`（text-only 預覽版，
不支援圖片），但本 gateway 未設定該 group。日常編碼直接用
`gpt-5.6-terra`，複雜任務用 `gpt-5.6-sol` 即可 —— GPT-5.6 系列的編碼能力
已超過上一代 codex 專用模型。

---

## 8. 限流與錯誤處理

### 速率限制

每個 group 有各自的 rpm 上限（見[第 3 節](#3-可用模型)），由 gateway 端計算，
超過會收到 `429`。

**這個上限是所有使用者共用的**，不是每把 key 各自的配額 ——
別人正在大量呼叫時，你也會被擋下。ChatGPT 那四個 group 的 rpm 刻意設得低
（5–20），因為它們共用同一個訂閱帳號的額度。

### 429 有兩種成因

收到 `429` 時先分辨是哪一種，處理方式完全不同：

| 來源 | 意義 | 處理方式 |
|---|---|---|
| gateway 的 rpm 上限 | 短時間內請求太密集 | 退避幾秒後重試，或改用 rpm 較高的 group |
| ChatGPT 訂閱額度將用盡 | 上游回的，整個帳號層級的問題 | 退避無效。等額度重置，或改用本地模型 |

訂閱額度的重置時間依 ChatGPT 方案而定 ——
請直接到 ChatGPT 端查看剩餘額度與重置時間，gateway 這邊看不到。

判斷方式：若只有 ChatGPT 模型全數 429、本地模型正常，且退避後重試仍然失敗，
多半是訂閱額度而非 rpm。

### 重試行為

各 group 設有 `max_retries`（ChatGPT 模型 1–2 次，本地模型 3 次），
這是**對同一個模型重送**，用來吸收暫時性的網路抖動 ——
它不會改送其他模型（原因見 [6.3](#63-沒有-fallback失敗就是失敗)）。

若失敗原因是額度用盡或 rpm 超限，重試只會延後錯誤出現的時間。
客戶端自行實作指數退避時，請把 429 與 5xx 分開處理。

### 常見錯誤對照

| 現象 | 原因 | 處理方式 |
|---|---|---|
| `400 Invalid model name passed in model=X` | group 不存在或已被移除 | 打 `/v1/models` 確認名稱 |
| `500 Unknown items in responses API response: []`（等待數十秒後）| ChatGPT 模型用了非串流 | 加上 `stream=True`，見 [6.1](#61-chatgpt-模型必須-streamtrue) |
| `400 {"detail":"Input must be a list"}` | `/v1/responses` 的 `input` 傳了字串 | 改成 list，見 [5.3](#53-responses-api) |
| `400 ... model is not supported when using Codex with a ChatGPT account` | 該 slug 已被 OpenAI 停用 | 查[官方 models 頁](https://learn.chatgpt.com/docs/models)換 slug |
| `429` | gateway 的 rpm 超限，或 ChatGPT 訂閱額度將用盡 | 兩者處理方式不同，見上方〈429 有兩種成因〉 |
| `403` 且內容是 Cloudflare 挑戰頁 | 已知的 LiteLLM 問題 [#27175](https://github.com/BerriAI/litellm/issues/27175) | 回報給 gateway 管理者 |
| 本地模型首次呼叫很慢 | Ollama 冷啟動載入模型 | 正常現象，重試即可 |

錯誤回應的完整格式（以模型名稱打錯為例）：

```json
{"error":{"message":"/chat/completions: Invalid model name passed in model=gpt-5.3-codex. Call `/v1/models` to view available models for your key.","type":"None","param":null,"code":"400"}}
```

判斷錯誤原因時請讀 `error.message` 全文 —— LiteLLM 會把上游的原始訊息
（例如 `ChatgptException - {...}`）包在裡面。

---

## 9. 模型選型建議

| 情境 | 建議 group | 理由 |
|---|---|---|
| 日常編碼、一般問答 | `gpt-5.6-terra` | 品質與速度平衡，官方定位的日常主力 |
| 複雜重構、難解 bug、跨檔案大改 | `gpt-5.6-sol` | 最強編碼能力，但 rpm 只有 5 且最耗額度 |
| 高頻小任務、批次處理 | `gpt-5.6-luna` | 快且省，rpm 20 是 ChatGPT 群組中最寬鬆的 |
| 不希望送到 OpenAI 的資料 | `gemma4-12b` | 推論在內網完成，不經過 OpenAI |
| 大量、低延遲的簡短回應 | `gemma4-e4b` | rpm 90，本地最快 |
| 翻譯 | `translategemma` | 翻譯特化 |
| 圖片分析 | `gpt-5.6-terra` | 本地模型不支援圖片輸入 |
| 行為對照 / 回退 | `gpt-5.5` | 懷疑 5.6 行為異常時拿來比對 |

原則：**能用本地就用本地**（不耗額度、推論不外流），需要品質再上 ChatGPT；
ChatGPT 群組內預設 `gpt-5.6-terra`，卡住才換 `gpt-5.6-sol`。

---

## 10. 疑難排解

### 先確認 gateway 活著

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://192.168.0.111/health/liveliness
# 預期 200
```

### 確認你的 key 能用哪些模型

```bash
curl -s http://192.168.0.111/v1/models \
  -H "Authorization: Bearer $LITELLM_API_KEY"
```

`/v1/models` 反映的是 gateway **當下實際載入的設定**。
若它與 `config.yaml` 對不上，通常是改了設定但尚未重啟容器。

### 用附帶的測試腳本快速定位

[test_llm_api.py](../test_llm_api.py) 會對所有模型各發一次最小請求並列表：

```bash
python test_llm_api.py            # 全部模型
python test_llm_api.py local      # 只測本地
python test_llm_api.py chatgpt    # 只測 ChatGPT
python test_llm_api.py demos      # 完整情境測試
```

用它可以快速判斷是「單一模型掛掉」還是「整條通路掛掉」：
若本地全過而 ChatGPT 全掛，問題多半在訂閱憑證或額度；反之則是 Ollama。

### 仍然無法排除

聯絡 gateway 管理者時，請附上：完整錯誤訊息（含 `error.message` 全文）、
使用的 model group 名稱、是否有加 `stream=True`、以及發生時間。

---

## 相關文件

- [config.yaml](../config.yaml) —— gateway 的模型設定，`model_name` 即本文的 group 名稱
- [test_llm_api.py](../test_llm_api.py) —— 連通性測試與情境範例
- [research/2026-08-05-chatgpt-pro-litellm-models.md](research/2026-08-05-chatgpt-pro-litellm-models.md) —— ChatGPT 可用模型的調查紀錄與出處
- [LiteLLM 官方文件](https://docs.litellm.ai/) —— 注意其 `chatgpt/` provider 頁面的模型清單已過期
- [OpenAI Codex models](https://learn.chatgpt.com/docs/models) —— ChatGPT 登入可用 slug 的權威來源

# AI Email & Scheduling Agent

這是一個具備自主決策能力的 AI Agent，專為高階經理人設計。它能夠自動分類郵件、評估優先級，並透過 MCP (Model Context Protocol) Server 自動管理行事曆。

## 系統需求與環境設定

*   Python 3.10+
*   有效且具備 function calling 能力的 LLM API Key (如 Google AI Studio `gemini-2.5-flash` 或 OpenAI `gpt-4o`)

### 1. 安裝依賴套件

請在專案根目錄下執行以下指令：

```bash
pip install -r requirements.txt
```

### 2. 環境變數設定

在專案根目錄下建立 `.env` 檔案（可參考 `.env.example`），並填入你的 API 設定：

```env
API_KEY=your_api_key_here
API_URL=https://generativelanguage.googleapis.com/v1beta/openai/ (選填，若使用 Google AI Studio)
MODEL=gemini-2.5-flash (選填，預設為 gemini-2.5-flash)
```

## 系統架構與設計理念

本系統分為兩個核心部分：

1.  **MCP Server (`mcp_server.py`)**：
    *   基於 `fastmcp` 實作。
    *   負責與 `data/calendar.json` (行事曆) 互動。
    *   提供五個標準化工具：
        *   `get_calendar_events`: 取得所有行程。
        *   `check_holiday`: 檢查是否為假日或補班日。
        *   `add_calendar_event`: 新增行程。
        *   `delete_calendar_event`: 刪除行程。
        *   `update_calendar_event`: 修改既有行程。
2.  **AI Agent (`agent.py`)**：
    *   使用 LLM API 進行自然語言理解與推理。
    *   透過 `mcp` 客戶端以 `stdio` 模式動態掛載並呼叫 MCP Server 的工具。
    *   具備多輪對話推理與工具串接能力。

### 決策流程與時序推理

Agent 在處理郵件時，遵循以下決策邏輯：
1.  **意圖與優先級分析**：判斷是否為會議邀約、緊急郵件、詢價或垃圾信。
2.  **時序與常識推理**：
    *   將基準時間設定為 `2026-01-19`。
    *   利用 `check_holiday` 工具與外部常識（預先在 System Prompt 定義）：如週末判斷、2026/02/16 為除夕等。
3.  **行程衝突處理**：
    *   當收到邀約時，主動呼叫 `get_calendar_events`。
    *   若遇衝突，比較優先級（System Prompt 規範優先保留高優先級），並提議替代時間。
    *   若是更改會議（如 EM013），Agent 會調用 `update_calendar_event` 或先調用 `delete_calendar_event` 再調用 `add_calendar_event`。
4.  **安全與護欄 (Guardrails)**：
    *   透過 System Prompt 嚴格限制：對於詢價或合約，絕對不進行實質性報價或承諾，並一律回覆「需待主管確認」或轉交相關負責人。

## 執行程式

在配置好環境與 API Key 後，執行：

```bash
python agent.py
```

### 預期執行結果
程式會逐一處理 `data/emails.json` 中的郵件。
終端機會輸出每封信的處理過程與工具調用日誌（包含工具的輸入與輸出）。
最終的處理結果與生成的回覆會儲存在 `data/report.json` 中。
同時，執行日誌會記錄在 `data/execution_log.md`。
而 `data/calendar.json` 也會根據同意的會議進行更新。

---

## 🛠️ 專案執行問答 (Q&A)

### 1. 如何啟動程式 & MCP Server？
*   **環境準備**：
    1.  安裝相依套件：執行 `pip install -r requirements.txt`。
    2.  設定環境變數：在 `.env` 檔案中填入 `API_KEY`（支援 Google AI Studio 或 OpenAI）。
*   **啟動方式**：直接執行 `python agent.py`。
*   **技術原理**：
    *   `agent.py` 為主程式，啟動後會透過 Python 的 `subprocess` 以 `stdio` 模式掛載並啟動 `mcp_server.py`。
    *   Agent 透過 `mcp` 套件建立 `ClientSession`，動態探索並調用 MCP Server 提供的 5 個工具（如 `get_calendar_events`、`check_holiday` 等），實現「大腦」與「外部工具」的無縫接軌。

### 2. Agent 處理 13 封郵件及面對日期陷阱（國定假日）的決策流程
*   **處理流程**：Agent 會逐一讀取 `data/emails.json` 中的 13 封郵件，每封郵件都會經歷「分析意圖 -> 調用工具檢查狀態 -> 執行動作 -> 生成回覆」的循環。
*   **面對日期陷阱（國定假日）的決策**：
    *   **範例 EM011**：收到 2026/02/16 (一) 的對帳邀約。
    *   **決議行為**：Agent 會先調用 `check_holiday("2026-02-16")`。由於 2026 年的除夕正好是 2/16，工具會回傳「放假日 (除夕)」。
    *   **最終邏輯**：Agent 識別到該日為農曆新年假期，會主動在回覆中婉拒，並說明當天是除夕假期，提議調整至年後的正常工作日。
    *   **範例 EM012**：收到 1/25 (日) 的維護會議邀約。Agent 透過工具發現是「週末休息日」，同樣會拒絕並提議改期，展現其具備時序意識的決策力。

### 3. 如何處理「除夕與週末」的推理判斷邏輯？
*   **非模型硬編碼**：不依賴 LLM 內建可能過時的節慶記憶，而是將判斷權交給專門的工具。
*   **工具實作**：MCP Server 中的 `check_holiday` 工具整合了 `chinese_calendar` 函式庫。
*   **判斷邏輯**：
    *   **精準識別**：該庫能準確判斷農曆節氣（如除夕、春節）及台灣特有的補班機制。
    *   **多重狀態回傳**：工具會區分「放假日」、「工作日」與「週末補班日」。
    *   **推理閉環**：當 Agent 收到「放假日」的訊號時，系統 Prompt 會觸發「拒絕並改期」的指令；若收到「週末補班日」，則 Agent 會知道雖然是週六/日，但依然可以安排工作會議。

### 4. 如何設計 Prompt 或 Workflows 來避免模型幻覺？
*   **強迫檢索 (Grounding)**：在 System Prompt 中強制規定：「在處理任何邀約前，**必須**呼叫 `get_calendar_events` 瞭解現有行程，並呼叫 `check_holiday` 檢查日期。」這消除了模型憑空猜測日程的可能性。
*   **ReAct 思考鏈**：Workflow 採用「思考-行動-觀察 (Thought-Action-Observation)」循環。Agent 必須先看到工具回傳的真實數據（如：1/20 已有論壇行程），才能做出下一個決定。
*   **結構化輸出**：強制要求最終回覆必須為特定的 JSON 格式。這縮小了模型的生成範圍，使其專注於事實分類與信件擬稿，減少發散式的幻覺。
*   **進階防禦策略 (未來擴充建議)**：
    *   **Human-in-the-loop (HITL)**：針對「寫入行事曆」或「正式回覆詢價」等高敏感動作，在執行 `add_calendar_event` 前增加人工審核環節，確保 Agent 的決策符合主管真實意圖。
    *   **Guardrails 框架整合**：引入如 `guardrails.ai` 或 `Pydantic-AI` 等框架，對 LLM 的輸出進行嚴格的 Schema 驗證與內容過濾，在輸出層即擋下不合規的承諾或幻覺內容。
    *   **雙重檢驗流程**：設計一個專門的「審計 Agent (Critic Agent)」來審閱執行日誌，檢查分類是否正確、回覆是否得體。


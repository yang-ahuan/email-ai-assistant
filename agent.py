import asyncio
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from openai import AsyncOpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# 載入環境變數
load_dotenv()

client = AsyncOpenAI(
    api_key=os.getenv("API_KEY"),
    base_url=os.getenv("API_URL")
)
DEFAULT_MODEL = os.getenv("MODEL", "gemini-2.0-flash")
print(f"使用 Google AI Studio (模型: {DEFAULT_MODEL})")

EMAILS_PATH = os.path.join(os.path.dirname(__file__), "data", "emails.json")
MCP_SERVER_PATH = os.path.join(os.path.dirname(__file__), "mcp_server.py")
LOG_PATH = os.path.join(os.path.dirname(__file__), "data", "execution_log.md")
REPORT_PATH = os.path.join(os.path.dirname(__file__), "data", "report.json")

def log_to_markdown(content: str, mode: str = "a"):
    with open(LOG_PATH, mode, encoding="utf-8") as f:
        f.write(content + "\n")

SYSTEM_PROMPT = """你是一位高階主管的專屬 AI 郵件與排程助理。
今天是 2026-01-19 (星期一)。工作時間為平日 09:00 - 18:00。

你的任務：
1. 閱讀使用者的郵件。
2. 進行分類（急件、一般、詢價、會議邀約、垃圾），並給予優先級評分（1~5，5最高）。
3. 處理會議邀約（核心邏輯）：
   - 在處理任何邀約前，**必須呼叫 `get_calendar_events`** 瞭解現有行程，並呼叫 `check_holiday` 檢查日期。
   - **情境 A：時間完全可行**（工作時段、非假日、無衝突）
     - 呼叫 `add_calendar_event` 將行程加入行事曆。
     - 在 `reply` 中告知對方已排定。
   - **情境 B：時間有衝突或不便**（假日、非工作時間、或已有行程）
     - **絕對不可**呼叫 `add_calendar_event`。
     - 你必須從現有行程中找出「有空且在工作時段內」的替代方案。
     - 在 `reply` 中婉拒原始請求，說明原因（例如：當天是補班日或已有重要會議），並提議 2-3 個替代時段，詢問對方是否可以接受。
   - **情境 C：更改會議**
     - 呼叫 `update_calendar_event`。若新時間有衝突，請比照「情境 B」處理（即不更新，改為提議協商）。
   - **情境 D：取消或刪除會議**
     - 呼叫 `delete_calendar_event` 並提供 `title` 與 `start` 以精確刪除行程。
4. 安全與護欄（Guardrails）：
   - 若郵件內容涉及「報價」、「合約簽署」或「財務承諾」，你必須在回覆中明確表示「需待主管/內部確認」，絕對不可以擅自給予具體的金錢承諾或同意合約。
5. 總結處理結果並給出回覆內容。


請務必在最終確認後，強制使用 JSON 格式回傳最終結果，格式如下：
{
  "category": "分類名稱",
  "priority": 數字,
  "reply": "你擬定的回覆信件內容"
}
"""

async def process_email(email: dict, mcp_session: ClientSession):
    # 記錄處理開始
    log_to_markdown(f"## 📧 處理郵件 [{email['id']}] - {email['subject']}")
    log_to_markdown(f"- **寄件者**: {email['sender']}\n- **時間**: {email['timestamp']}\n- **內容**: {email['content']}\n")
    log_to_markdown("### 🛠️ 執行步驟")
    
    # 取得 MCP tools 並轉換為 OpenAI 的格式
    mcp_tools = await mcp_session.list_tools()
    openai_tools = []
    for tool in mcp_tools.tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema
            }
        })

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"請處理以下郵件：\n\n寄件者：{email['sender']}\n主旨：{email['subject']}\n時間：{email['timestamp']}\n內容：{email['content']}"}
    ]

    step_count = 1
    while True:
        response = await client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=messages,
            tools=openai_tools if openai_tools else None
        )

        message = response.choices[0].message
        messages.append(message)

        if message.tool_calls:
            # 執行工具調用
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)
                
                log_to_markdown(f"{step_count}. **Agent 調用工具**: `{tool_name}({tool_args})`")
                print(f"  [Agent 調用工具] {tool_name}({tool_args})")
                
                try:
                    result = await mcp_session.call_tool(tool_name, arguments=tool_args)
                    result_text = "\n".join([c.text for c in result.content if c.type == "text"])
                except Exception as e:
                    result_text = f"Tool execution failed: {str(e)}"
                
                log_to_markdown(f"   - **工具執行結果**: {result_text}")
                print(f"  [工具執行結果] {result_text}")
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_name,
                    "content": result_text
                })
                step_count += 1
        else:
            # 如果沒有調用工具，且回傳了內容，則視為最終結果
            try:
                content = message.content.strip()
                if content.startswith("```json"):
                    content = content[7:-3].strip()
                elif content.startswith("```"):
                    content = content[3:-3].strip()
                
                final_result = json.loads(content)
                
                log_to_markdown("### 🏁 處理結果")
                log_to_markdown(f"- **分類**: {final_result.get('category')}")
                log_to_markdown(f"- **優先級**: {final_result.get('priority')}")
                log_to_markdown(f"- **回覆內容**:\n\n```\n{final_result.get('reply')}\n```\n")
                log_to_markdown("---")
                
                return final_result
            except (json.JSONDecodeError, AttributeError):
                messages.append({"role": "user", "content": "請確保最終回覆為 JSON 格式，包含 category, priority, reply 三個欄位。"})

async def main():
    if not client:
        print("請先在 .env 中設定 GOOGLE_API_KEY 或 OPENAI_API_KEY。")
        return

    # 初始化日誌檔案
    log_to_markdown(f"# 🚀 Agent 執行日誌 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", mode="w")

    # 讀取信件
    with open(EMAILS_PATH, "r", encoding="utf-8") as f:
        emails = json.load(f)

    # 設定 MCP Server 啟動參數
    server_params = StdioServerParameters(
        command="python",
        args=[MCP_SERVER_PATH],
        env=os.environ.copy()
    )

    print("啟動 AI Email & Scheduling Agent...")
    
    results = []
    
    # 連線至 MCP Server
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            for email in emails:
                print(f"\n處理郵件 [{email['id']}] - {email['subject']} ...")
                try:
                    res = await process_email(email, session)
                    print(f"  分類: {res.get('category')}, 優先級: {res.get('priority')}")
                    
                    results.append({
                        "id": email["id"],
                        "category": res.get("category"),
                        "priority": res.get("priority"),
                        "reply": res.get("reply")
                    })
                except Exception as e:
                    print(f"處理失敗: {e}")
                    log_to_markdown(f"❌ **處理失敗**: {str(e)}\n---")
                    
    # 輸出最終報表
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n所有郵件處理完畢，結果已儲存至 {REPORT_PATH} 與 {LOG_PATH}")

if __name__ == "__main__":
    asyncio.run(main())

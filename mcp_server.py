import json
import os
from datetime import datetime
from fastmcp import FastMCP
import chinese_calendar as calendar

# 設定行事曆檔案路徑
CALENDAR_PATH = os.path.join(os.path.dirname(__file__), "data", "calendar.json")

# 初始化 MCP Server
mcp = FastMCP("calendar_server")

def load_calendar():
    if not os.path.exists(CALENDAR_PATH):
        return []
    with open(CALENDAR_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_calendar(events):
    with open(CALENDAR_PATH, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)

@mcp.tool()
def get_calendar_events() -> list[dict]:
    """
    查詢目前的行事曆所有行程。
    回傳的列表包含每個行程的 title, start, end (格式: YYYY-MM-DDTHH:MM:SS)。
    """
    return load_calendar()

@mcp.tool()
def check_holiday(date_str: str) -> str:
    """
    檢查指定日期是否為國定假日或補班日。
    :param date_str: 日期格式為 YYYY-MM-DD
    :return: 包含是否為假日、是否為工作日及假日名稱的說明字串
    """
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").date()
        on_holiday, holiday_name = calendar.get_holiday_detail(dt)
        is_workday = calendar.is_workday(dt)
        
        status = "放假日" if on_holiday else "工作日"
        if not on_holiday and not is_workday:
             status = "週末休息日"
        elif is_workday and not on_holiday:
             # 可能是補班日或是普通工作日
             # calendar.is_workday 在週末如果是補班日會回傳 True
             status = "工作日"

        res = f"日期: {date_str}, 狀態: {status}"
        if holiday_name:
            res += f", 節日名稱: {holiday_name}"
        
        # 針對補班日的特別提醒
        if is_workday and dt.weekday() >= 5:
            res += " (注意：此為週末補班日)"
            
        return res
    except ValueError:
        return f"失敗：日期格式錯誤，請使用 YYYY-MM-DD。收到: {date_str}"

@mcp.tool()
def add_calendar_event(title: str, start: str, end: str) -> str:
    """
    將確認後的會議寫入行事曆。
    :param title: 會議或行程標題
    :param start: 開始時間，ISO格式 (YYYY-MM-DDTHH:MM:SS)
    :param end: 結束時間，ISO格式 (YYYY-MM-DDTHH:MM:SS)
    """
    try:
        # 驗證時間格式
        datetime.strptime(start, "%Y-%m-%dT%H:%M:%S")
        datetime.strptime(end, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return f"失敗：時間格式錯誤，請使用 YYYY-MM-DDTHH:MM:SS。收到: start={start}, end={end}"

    events = load_calendar()
    # 簡單防重複寫入檢查 (相同時間範圍可能有衝突，這裡僅檢查是否完全一樣的會議)
    for event in events:
        if event["title"] == title and event["start"] == start and event["end"] == end:
            return f"失敗：行程已存在 ({title})"

    new_event = {
        "title": title,
        "start": start,
        "end": end
    }
    events.append(new_event)
    save_calendar(events)
    return f"成功：已新增行程 '{title}' ({start} ~ {end})"

@mcp.tool()
def delete_calendar_event(title: str, start: str = None) -> str:
    """
    刪除指定的行程。
    :param title: 要刪除的行程標題
    :param start: (選填) 行程開始時間 (YYYY-MM-DDTHH:MM:SS)，若有多個同名行程，請提供開始時間以利精確刪除。
    """
    events = load_calendar()
    original_count = len(events)
    
    if start:
        new_events = [e for e in events if not (e["title"] == title and e["start"] == start)]
    else:
        new_events = [e for e in events if e["title"] != title]
    
    if len(new_events) == original_count:
        msg = f"失敗：找不到名為 '{title}'"
        if start:
            msg += f" 且開始時間為 '{start}'"
        return msg + " 的行程。"
    
    save_calendar(new_events)
    return f"成功：已刪除行程 '{title}'"

@mcp.tool()
def update_calendar_event(
    original_title: str,
    original_start: str,
    new_title: str = None,
    new_start: str = None,
    new_end: str = None
) -> str:
    """
    修改既有的行程。僅傳入需要修改的欄位。
    :param original_title: 要修改的原始行程標題
    :param original_start: 要修改的原始行程開始時間 (YYYY-MM-DDTHH:MM:SS)，用來精確定位行程
    :param new_title: (選填) 新的標題
    :param new_start: (選填) 新的開始時間 (YYYY-MM-DDTHH:MM:SS)
    :param new_end: (選填) 新的結束時間 (YYYY-MM-DDTHH:MM:SS)
    """
    events = load_calendar()
    found_index = -1
    
    for i, event in enumerate(events):
        if event["title"] == original_title and event["start"] == original_start:
            found_index = i
            break
            
    if found_index == -1:
        return f"失敗：找不到行程 '{original_title}' 開始於 {original_start}"

    # 驗證新時間格式 (如果有傳入)
    try:
        if new_start:
            datetime.strptime(new_start, "%Y-%m-%dT%H:%M:%S")
        if new_end:
            datetime.strptime(new_end, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return "失敗：時間格式錯誤，請使用 YYYY-MM-DDTHH:MM:SS"

    # 更新內容
    event = events[found_index]
    if new_title:
        event["title"] = new_title
    if new_start:
        event["start"] = new_start
    if new_end:
        event["end"] = new_end
        
    save_calendar(events)
    return f"成功：已更新行程 '{original_title}'"

if __name__ == "__main__":
    # 以 stdio 模式啟動 MCP Server
    mcp.run()

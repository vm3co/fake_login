"""
AI 生成事件的獨立日誌系統。

每次 AI 生成（/generate_with_ai_stream）會產生一個 generation_id，
對應一個 ./ai_logs/{generation_id}.log 檔案，
記錄該次生成的請求、reasoning、回傳內容、design.md，以及後續上傳事件。
"""
import os
import time
import uuid
from pathlib import Path

from backend.services.log_manager import Logger

_logger = Logger().get_logger()

AI_LOG_DIR = Path("./ai_logs")
AI_LOG_DIR.mkdir(parents=True, exist_ok=True)


def new_generation_id() -> str:
    """產生 YYYYMMDD_HHMMSS_<6位hex> 格式的 ID。"""
    ts = time.strftime("%Y%m%d_%H%M%S")
    short = uuid.uuid4().hex[:6]
    return f"{ts}_{short}"


def log_path(generation_id: str) -> Path:
    return AI_LOG_DIR / f"{generation_id}.log"


def _safe_append(generation_id: str, text: str) -> None:
    try:
        path = log_path(generation_id)
        with path.open("a", encoding="utf-8") as f:
            f.write(text)
    except Exception as e:
        _logger.warning(f"[ai_log] 寫入 {generation_id} 失敗: {e}")


def write_header(generation_id: str, meta: dict) -> None:
    """寫入生成事件的 header 區塊。"""
    lines = ["=== AI Generation Log ==="]
    lines.append(f"generation_id: {generation_id}")
    lines.append(f"timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    for key in ("user_uuid", "model", "page_type", "use_design", "ref_url", "has_image"):
        if key in meta:
            lines.append(f"{key}: {meta[key]}")
    _safe_append(generation_id, "\n".join(lines) + "\n\n")


def write_section(generation_id: str, title: str, body: str) -> None:
    """寫入一個段落區塊。"""
    if body is None:
        body = ""
    _safe_append(generation_id, f"--- {title} ---\n{body}\n\n")


def _format_elapsed(seconds: float) -> str:
    """格式化耗時為人類易讀字串。"""
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes = int(seconds // 60)
    secs = seconds - minutes * 60
    return f"{minutes}m {secs:.2f}s"


def write_timing(generation_id: str, label: str, start_ts: float, end_ts: float) -> None:
    """寫入 LLM 呼叫時間區塊（開始 / 結束 / 經過秒數）。"""
    elapsed = end_ts - start_ts
    lines = [f"--- {label} Timing ---"]
    lines.append(f"start:   {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_ts))}")
    lines.append(f"end:     {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_ts))}")
    lines.append(f"elapsed: {_format_elapsed(elapsed)}")
    _safe_append(generation_id, "\n".join(lines) + "\n\n")


def write_upload_event(generation_id: str, meta: dict, success: bool = True) -> None:
    """寫入上傳事件區塊。"""
    title = "=== Upload Event ===" if success else "=== Upload Failed ==="
    lines = [title]
    lines.append(f"timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    for key in ("user_uuid", "page_label", "page_value", "saved_file", "error"):
        if key in meta:
            lines.append(f"{key}: {meta[key]}")

    path = log_path(generation_id)
    if not path.exists():
        _logger.warning(f"[ai_log] 找不到對應的生成日誌 {generation_id}.log，仍嘗試寫入")
    _safe_append(generation_id, "\n".join(lines) + "\n\n")

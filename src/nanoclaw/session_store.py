"""
会话状态持久化模块。

这个模块只管一件事：把当前 Claude session_id 保存到本地文件，
并在下次请求时再读出来。

它保存的是“继续上一轮会话的钥匙”，不是完整聊天记录本身。
完整聊天记录长期归档在 `conversations/`，短期连续上下文靠这里的 session_id。
"""

import json

from .config import DATE_DIR, STATE_FILE


def load_session_id() -> str | None:
    """从文件加载会话 ID，如果不存在则返回 None。"""
    if STATE_FILE.exists():
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            # `json.load()` 会把 JSON object 反序列化成 Python dict。
            data = json.load(file)
            return data.get("session_id")
    return None


def save_session_id(session_id: str) -> None:
    """将会话 ID 保存到文件中。"""
    # 这里再次确保 data 目录存在，是一种防御式写法：
    # 即使某些测试或脚本没有走完整启动流程，这里依旧能单独工作。
    DATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump({"session_id": session_id}, file)


def clear_session_id() -> None:
    """清除会话 ID，删除状态文件。"""
    if STATE_FILE.exists():
        STATE_FILE.unlink()

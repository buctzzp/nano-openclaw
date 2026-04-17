"""
MCP 工具注册模块。

这里的职责非常单一：把“给 Telegram 用户发消息”这个能力，
包装成 Claude Agent 能调用的 SDK MCP tool。

换句话说，这一层是在做“Telegram 世界”和“Claude Agent 工具世界”的桥接。
"""

from typing import Any
from nanoclaw import db
from claude_agent_sdk import tool
from datetime import datetime, timedelta, timezone
from croniter import croniter
def create_mcp_server_tools(bot, chat_id: int,db_path: str,sent_messages: list[str] | None = None) -> list:
    """创建供 Claude Agent 使用的 SDK MCP 工具。"""

    @tool("send_message", "发送消息给用户", {"text": str})
    async def send_message(args) -> dict[str, Any]:
        # 这里用闭包捕获当前 chat_id。
        # 这样 agent 在调用 `send_message` 时，不需要自己再传“该发给谁”，
        # 工具天然就会回复到触发本轮对话的那个 Telegram chat 里。
        await bot.send_message(chat_id=chat_id, text=args["text"])

        # 这里顺手把已经发给用户的文本记下来，后面归档时需要把它们也拼进去。
        if sent_messages is not None:
            sent_messages.append(str(args["text"]))
        

        # 这个返回结构不是随便写的，而是 Claude SDK 规定的 tool result 格式。
        # `content` 是一个列表；列表里每项都带 `type`，这里我们返回 text 类型。
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"已经给用户发送消息: {args['text']}",
                }
            ]
        }
    
    @tool(
        "schedule_task",
        "Schedule a task. schedule_type: 'cron', 'interval', or 'once'. schedule_value: cron expression, milliseconds, or ISO timestamp.",
        {"prompt": str, "schedule_type": str, "schedule_value": str},
    )
    async def schedule_task(args: dict[str, Any]) -> dict[str, Any]:
        stype = args["schedule_type"]
        svalue = args["schedule_value"]
        now = datetime.now(timezone.utc)

        if stype == "cron":
            next_run = croniter(svalue, now).get_next(datetime).isoformat()
        elif stype == "interval":
            next_run = (now + timedelta(milliseconds=int(svalue))).isoformat()
        elif stype == "once":
            next_run = svalue
        else:
            return {
                "content": [{"type": "text", "text": f"Unknown schedule_type: {stype}"}],
                "is_error": True,
            }

        task_id = await db.create_task(db_path, chat_id, args["prompt"], stype, svalue, next_run)
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Task {task_id} scheduled. Next run: {next_run}",
                }
            ]
        }

    @tool("list_tasks", "List all scheduled tasks", {})
    async def list_tasks(args: dict[str, Any]) -> dict[str, Any]:
        tasks = await db.get_all_tasks(db_path)
        if not tasks:
            return {"content": [{"type": "text", "text": "No scheduled tasks."}]}
        lines = [f"- [{t['id']}] {t['status']} | {t['schedule_type']}({t['schedule_value']}) | {t['prompt'][:60]}" for t in tasks]
        return {"content": [{"type": "text", "text": "\n".join(lines)}]}

    @tool("pause_task", "Pause a scheduled task", {"task_id": str})
    async def pause_task(args: dict[str, Any]) -> dict[str, Any]:
        ok = await db.update_task_status(db_path, args["task_id"], "paused")
        msg = f"Task {args['task_id']} paused." if ok else f"Task {args['task_id']} not found."
        return {"content": [{"type": "text", "text": msg}]}

    @tool("resume_task", "Resume a paused task", {"task_id": str})
    async def resume_task(args: dict[str, Any]) -> dict[str, Any]:
        ok = await db.update_task_status(db_path, args["task_id"], "active")
        msg = f"Task {args['task_id']} resumed." if ok else f"Task {args['task_id']} not found."
        return {"content": [{"type": "text", "text": msg}]}

    @tool("cancel_task", "Cancel and delete a scheduled task", {"task_id": str})
    async def cancel_task(args: dict[str, Any]) -> dict[str, Any]:
        ok = await db.delete_task(db_path, args["task_id"])
        msg = f"Task {args['task_id']} cancelled." if ok else f"Task {args['task_id']} not found."
        return {"content": [{"type": "text", "text": msg}]}


    return [send_message, schedule_task, list_tasks, pause_task, resume_task, cancel_task]

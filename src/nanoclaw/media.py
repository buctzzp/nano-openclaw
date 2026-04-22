"""
媒体资产模块。

这一层只负责把外部媒体接管成工作区里的稳定文件资产。
它不调用 Agent，不发 Telegram 消息，也不分析图片内容。
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable

from telegram import Update

from .config import ASSET_INDEX_FILE, IMAGE_ASSET_DIR, WORK_SPACE


ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass(frozen=True)
class MediaAsset:
    """被系统接管后的媒体文件。"""

    # 本地绝对路径：代码真正读写图片时使用，例如 send_image 会用它打开文件。
    path: Path
    # 相对 work_space 的路径：适合写入归档、提示词和索引，换机器后也更容易理解。
    relative_path: Path
    # 元数据文件路径：每个资产目录固定一个 metadata.json，用来长期记录来源和上下文。
    metadata_path: Path
    # MIME 类型：描述文件内容格式，例如 image/jpeg、image/png，后续扩展媒体处理时会用到。
    mime_type: str
    # 来源类型：例如 telegram_photo、screenshot，用于区分“用户发来的图”和“系统生成的截图”。
    source: str
    # 图片配文：用户随图片附带的文字；没有配文时为空字符串。
    caption: str
    # 接管时间：资产进入系统的时间，ISO 格式，方便后续排序、排查和归档。
    created_at: str
    # Telegram chat id：说明这份资产属于哪个 Telegram 会话。
    chat_id: int
    # Telegram message id：能定位原始消息；主动生成的资产没有原始消息时用 0。
    message_id: int
    # Telegram file_id：Telegram 下载文件需要的 id；主动生成的资产没有 Telegram 文件时为空字符串。
    file_id: str
    # 稳定文件 id：Telegram file_unique_id 或系统生成 id，用于资产目录命名和长期追踪。
    file_unique_id: str


async def ingest_telegram_photo(
    update: Update,
    chat_id: int,
    timestamp: datetime | None = None,
) -> MediaAsset:
    """把 Telegram 图片消息保存成 work_space/assets 下的媒体资产。"""
    current_time = timestamp or datetime.now()
    if not update.message.photo:
        raise ValueError("Telegram message does not contain photo sizes.")

    # Telegram 会为同一张图片生成多个 PhotoSize，例如缩略图、中等图、较大图。
    # 这里取最后一个，是为了保存 Telegram 返回的最高可用清晰度版本。
    photo = update.message.photo[-1]
    asset_id = f"{current_time:%H%M%S}_telegram_photo_{photo.file_unique_id}"
    asset_dir = IMAGE_ASSET_DIR / "telegram" / f"{current_time:%Y-%m-%d}" / asset_id
    asset_dir.mkdir(parents=True, exist_ok=True)

    image_path = asset_dir / "original.jpg"
    # get_file() 不会立刻下载图片，它只是向 Telegram 换取一个可下载的 File 对象。
    telegram_file = await photo.get_file()
    # download_to_drive() 才是真正把远端 Telegram 图片保存到本地磁盘。
    saved_path = await telegram_file.download_to_drive(image_path)

    # download_to_drive() 返回实际保存路径；重新转成 Path，保证后续统一按 pathlib 处理。
    image_path = Path(saved_path)
    metadata_path = asset_dir / "metadata.json"
    asset = MediaAsset(
        path=image_path,
        relative_path=image_path.relative_to(WORK_SPACE),
        metadata_path=metadata_path,
        mime_type="image/jpeg",
        source="telegram_photo",
        caption=(update.message.caption or "").strip(),
        created_at=current_time.isoformat(),
        chat_id=chat_id,
        message_id=update.message.message_id,
        file_id=photo.file_id,
        file_unique_id=photo.file_unique_id,
    )

    write_asset_metadata(asset)
    update_asset_index(asset, latest_keys=("telegram_photo",))
    return asset


async def _run_screencapture(output_path: Path) -> None:
    """调用 macOS screencapture，把当前屏幕保存到指定路径。"""
    process = await asyncio.create_subprocess_exec(
        "screencapture",
        str(output_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        error_text = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(error_text or "screencapture failed")


async def create_screenshot_asset(
    chat_id: int,
    timestamp: datetime | None = None,
    runner: Callable[[Path], Awaitable[None]] | None = None,
) -> MediaAsset:
    """创建当前屏幕截图资产，并维护 latest.screenshot 索引。"""
    current_time = timestamp or datetime.now()
    asset_id = f"{current_time:%H%M%S}_screenshot_desktop"
    asset_dir = IMAGE_ASSET_DIR / "screenshots" / f"{current_time:%Y-%m-%d}" / asset_id
    asset_dir.mkdir(parents=True, exist_ok=True)

    image_path = asset_dir / "original.png"
    screenshot_runner = runner or _run_screencapture
    await screenshot_runner(image_path)

    if not image_path.exists():
        raise RuntimeError("screencapture did not create an image file")

    asset = MediaAsset(
        path=image_path,
        relative_path=image_path.relative_to(WORK_SPACE),
        metadata_path=asset_dir / "metadata.json",
        mime_type="image/png",
        source="screenshot",
        caption="",
        created_at=current_time.isoformat(),
        chat_id=chat_id,
        message_id=0,
        file_id="",
        file_unique_id=asset_id,
    )
    write_asset_metadata(asset)
    update_asset_index(asset, latest_keys=("screenshot",))
    return asset


def write_asset_metadata(asset: MediaAsset) -> None:
    """把媒体资产元数据写到资产目录中的 metadata.json。"""
    asset.metadata_path.write_text(
        json.dumps(
            {
                **asdict(asset),
                "path": str(asset.path),
                "relative_path": str(asset.relative_path),
                "metadata_path": str(asset.metadata_path),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def update_asset_index(asset: MediaAsset, latest_keys: tuple[str, ...]) -> None:
    """维护一个极轻量索引，按具体资产类型定位最新文件。"""
    index: dict = {"latest": {}}
    if ASSET_INDEX_FILE.exists():
        try:
            index = json.loads(ASSET_INDEX_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            index = {"latest": {}}

    latest = index.setdefault("latest", {})
    asset_dir = asset.path.parent.relative_to(WORK_SPACE).as_posix()
    for key in latest_keys:
        latest[key] = asset_dir

    ASSET_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    ASSET_INDEX_FILE.write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_image_prompt(asset: MediaAsset) -> str:
    """把图片资产转换成 Claude Code SDK 可以稳定接收的纯文本 prompt。"""
    caption = asset.caption or "用户没有提供图片配文。"
    return f"""用户发送了一张图片。

图片保存路径：
{asset.path}

用户配文：
{caption}

请根据用户的问题处理这张图片。你可以使用 Read 工具尝试读取图片。
如果当前模型无法可靠理解图片内容，请明确告诉用户，不要编造图片内容。
"""


def format_image_markdown(asset: MediaAsset) -> str:
    """把图片资产转换成对话归档里可直接显示的 Markdown。"""
    caption = asset.caption or "用户发送了一张图片。"
    return f"[图片] {caption}\n\n![](../{asset.relative_path.as_posix()})"


def validate_workspace_image_path(
    image_path: str | Path,
    workspace: Path | None = None,
) -> Path:
    """校验图片路径是否存在、是否是图片、是否位于工作区内。"""
    workspace_path = (workspace or WORK_SPACE).resolve()
    raw_path = Path(image_path).expanduser()
    path = raw_path.resolve() if raw_path.is_absolute() else (workspace_path / raw_path).resolve()

    try:
        path.relative_to(workspace_path)
    except ValueError as error:
        raise ValueError(
            "Image path must be inside work_space. For managed media, use assets/images/..."
        ) from error

    if not path.exists():
        raise ValueError("Image file does not exist.")

    if path.suffix.lower() not in ALLOWED_IMAGE_SUFFIXES:
        raise ValueError("Only jpg, jpeg, png, and webp images can be sent.")

    return path

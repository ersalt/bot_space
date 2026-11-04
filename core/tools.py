"""模型侧工具：space_list / space_read / space_search / space_create / space_append。

工具是权限表：`allow_write = false` 时这里直接不返回 create/append，模型 schema
里就没有这两个函数。所有预期失败都抛 `SpaceError`，宿主会转成 `ok: false` 回给模型，
不会打断聊天主链路。
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable, Mapping
from typing import Any

from app.sdk import Tool, ToolContext

from .space import TRASH_LIST_LIMIT, Limits, SpaceError, SpaceStore

LIST_LIMIT = 40
PATH_DESCRIPTION = "相对路径，例如 notes/today.md；只允许 .md，最多两层子目录"


def allow_write(settings: Mapping[str, Any]) -> bool:
    """设置里的 allow_write；容忍手改 settings.toml 写成字符串。"""
    value = settings.get("allow_write", True)
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "off", "no"}
    return bool(value)


def _limits(settings: Callable[[], Mapping[str, Any]]) -> Limits:
    try:
        values = settings() or {}
    except Exception:  # noqa: BLE001 - 设置读炸了就用默认配额
        values = {}
    return Limits.from_settings(dict(values))


def _object(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def _string_arg(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SpaceError(f"{key} 不能为空")
    return value.strip()


def _text_arg(args: dict[str, Any]) -> str:
    value = args.get("text")
    if not isinstance(value, str) or not value.strip():
        raise SpaceError("text 不能为空")
    return value


def _raw_string_arg(args: dict[str, Any], key: str, *, allow_empty: bool = False) -> str:
    """保留原文空白：编辑用的 old/new 不能 strip，否则会找不到要改的片段。"""
    value = args.get(key)
    if not isinstance(value, str):
        raise SpaceError(f"{key} 必须是字符串")
    if not allow_empty and not value:
        raise SpaceError(f"{key} 不能为空")
    return value


def _bool_arg(args: dict[str, Any], key: str, default: bool = False) -> bool:
    value = args.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _int_arg(args: dict[str, Any], key: str, default: int) -> int:
    value = args.get(key, default)
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise SpaceError(f"{key} 必须是整数") from exc


def _session(ctx: ToolContext) -> str:
    return str(getattr(ctx, "session_key", "") or "")


async def _run(
    ctx: ToolContext,
    store: SpaceStore,
    name: str,
    path: str,
    call: Callable[[], Any],
    *,
    chars: int | None = None,
    chars_fn: Callable[[Any], int] | None = None,
) -> Any:
    """执行一次工具并记审计；异常保留给 ToolRunner 转成 ok:false。"""
    try:
        result = call()
        if inspect.isawaitable(result):
            result = await result
    except SpaceError as exc:
        store.audit(name, path, 0, False, session=_session(ctx), error=str(exc))
        raise
    except OSError as exc:
        message = f"文件读写失败：{exc}"
        store.audit(name, path, 0, False, session=_session(ctx), error=message)
        raise SpaceError(message) from exc
    size = chars
    if size is None:
        size = chars_fn(result) if chars_fn is not None else _result_chars(result)
    store.audit(name, path, size, True, session=_session(ctx))
    return result


def _result_chars(result: Any) -> int:
    try:
        return len(json.dumps(result, ensure_ascii=False, default=str))
    except (TypeError, ValueError):
        return 0


def build_tools(
    store: SpaceStore,
    settings: Callable[[], Mapping[str, Any]],
) -> list[Tool]:
    """按当前设置返回工具表；写工具随 allow_write 实时增减。"""

    async def space_list(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        subdir = args.get("dir") or ""
        return await _run(
            ctx,
            store,
            "space_list",
            str(subdir),
            lambda: store.list_files(subdir, limit=LIST_LIMIT),
        )

    async def space_read(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        path = _string_arg(args, "path")
        offset = _int_arg(args, "offset", 0)
        return await _run(
            ctx,
            store,
            "space_read",
            path,
            lambda: store.read(path, offset=offset, limit=_limits(settings).max_read_chars),
            chars_fn=lambda result: len(result.get("content", "")),
        )

    async def space_search(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        query = _string_arg(args, "query")
        return await _run(
            ctx,
            store,
            "space_search",
            query,
            lambda: store.search(query, limit=_limits(settings).max_search_hits),
        )

    async def space_create(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        path = _string_arg(args, "path")
        text = _text_arg(args)
        return await _run(
            ctx,
            store,
            "space_create",
            path,
            lambda: store.create(path, text, _limits(settings)),
            chars=len(text),
        )

    async def space_append(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        path = _string_arg(args, "path")
        text = _text_arg(args)
        return await _run(
            ctx,
            store,
            "space_append",
            path,
            lambda: store.append(path, text, _limits(settings)),
            chars=len(text),
        )

    async def space_edit(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        path = _string_arg(args, "path")
        old = _raw_string_arg(args, "old")
        new = _raw_string_arg(args, "new", allow_empty=True)
        replace_all = _bool_arg(args, "all", False)
        return await _run(
            ctx,
            store,
            "space_edit",
            path,
            lambda: store.edit(path, old, new, _limits(settings), replace_all=replace_all),
            chars=len(new),
        )

    async def space_delete(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        path = _string_arg(args, "path")
        return await _run(
            ctx,
            store,
            "space_delete",
            path,
            lambda: store.delete(path),
        )

    async def space_trash(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        return await _run(
            ctx,
            store,
            "space_trash",
            "",
            lambda: store.trash_items(TRASH_LIST_LIMIT),
        )

    async def space_restore(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        item_id = _string_arg(args, "id")
        return await _run(
            ctx,
            store,
            "space_restore",
            item_id,
            lambda: store.restore(item_id, _limits(settings)),
        )

    tools = [
        Tool(
            name="space_list",
            description=(
                "列出 BOT空间里的 Markdown 文件：路径、标题、大小、修改时间。"
                "不确定有哪些笔记、或要确认路径时先调用它；只读，最多返回 40 条。"
            ),
            parameters=_object(
                {
                    "dir": {
                        "type": "string",
                        "description": "子目录，例如 notes；留空表示根目录",
                        "maxLength": 160,
                    }
                }
            ),
            handler=space_list,
        ),
        Tool(
            name="space_read",
            description=(
                "读取手记里的一篇 Markdown。默认从头读，单次最多返回配置的字数，"
                "被截断时用 offset 继续读；只读。"
            ),
            parameters=_object(
                {
                    "path": {"type": "string", "description": PATH_DESCRIPTION, "maxLength": 160},
                    "offset": {
                        "type": "integer",
                        "description": "从第几个字符开始读，默认 0",
                        "minimum": 0,
                    },
                },
                ["path"],
            ),
            handler=space_read,
        ),
        Tool(
            name="space_search",
            description=(
                "在手记的所有 Markdown 里按关键词搜索（不区分大小写），"
                "返回路径、行号和匹配行。找以前记过什么时用；只读。"
            ),
            parameters=_object(
                {
                    "query": {
                        "type": "string",
                        "description": "要搜索的关键词，1 到 100 个字",
                        "minLength": 1,
                        "maxLength": 100,
                    }
                },
                ["query"],
            ),
            handler=space_search,
        ),
        Tool(
            name="space_trash",
            description=(
                "查看回收站里被删除的文件：id、原路径、大小、删除时间。"
                "删除不是永久的，可以用 space_restore 恢复；只读。"
            ),
            parameters=_object({}),
            handler=space_trash,
        ),
    ]
    if not allow_write(_settings(settings)):
        return tools

    tools += [
        Tool(
            name="space_create",
            description=(
                "在手记新建一篇 Markdown。已存在会失败，不会覆盖；"
                "要补充已有文件用 space_append，要修改已有内容用 space_edit。"
            ),
            parameters=_object(
                {
                    "path": {"type": "string", "description": PATH_DESCRIPTION, "maxLength": 160},
                    "text": {
                        "type": "string",
                        "description": "要写入的 Markdown 正文；不能为空",
                    },
                },
                ["path", "text"],
            ),
            handler=space_create,
            read_only=False,
        ),
        Tool(
            name="space_append",
            description=(
                "向手记的 Markdown 追加内容；文件不存在会自动新建。"
                "只用于新增；修改已有内容或删掉某一行请用 space_edit，不要用 append 反复追加“更正”。"
            ),
            parameters=_object(
                {
                    "path": {"type": "string", "description": PATH_DESCRIPTION, "maxLength": 160},
                    "text": {
                        "type": "string",
                        "description": "要追加的 Markdown 正文；不能为空",
                    },
                },
                ["path", "text"],
            ),
            handler=space_append,
            read_only=False,
        ),
        Tool(
            name="space_edit",
            description=(
                "精确修改一篇 Markdown：把 old 替换成 new。old 必须与文件中的原文逐字一致；"
                "命中多处时需 all=true。改内容、删某一行都用它，改前先 space_read。"
            ),
            parameters=_object(
                {
                    "path": {"type": "string", "description": PATH_DESCRIPTION, "maxLength": 160},
                    "old": {
                        "type": "string",
                        "description": "要替换的原文，必须逐字一致，不能为空",
                    },
                    "new": {
                        "type": "string",
                        "description": "替换成什么；可以为空字符串（等于删掉这段）",
                    },
                    "all": {
                        "type": "boolean",
                        "description": "old 命中多处时是否全部替换，默认 false",
                    },
                },
                ["path", "old", "new"],
            ),
            handler=space_edit,
            read_only=False,
        ),
        Tool(
            name="space_delete",
            description=(
                "把一篇 Markdown 移到回收站，不是永久删除；之后可以用 space_trash 查看、"
                "space_restore 恢复。删除也占配额。"
            ),
            parameters=_object(
                {"path": {"type": "string", "description": PATH_DESCRIPTION, "maxLength": 160}},
                ["path"],
            ),
            handler=space_delete,
            read_only=False,
        ),
        Tool(
            name="space_restore",
            description=(
                "把回收站里的文件恢复到原路径。先用 space_trash 拿 id；"
                "原路径已有文件时会失败。"
            ),
            parameters=_object(
                {
                    "id": {
                        "type": "string",
                        "description": "回收站条目的 id，例如 20261105-012345-a1b2c3",
                    }
                },
                ["id"],
            ),
            handler=space_restore,
            read_only=False,
        ),
    ]
    return tools


def _settings(settings: Callable[[], Mapping[str, Any]]) -> Mapping[str, Any]:
    try:
        return settings() or {}
    except Exception:  # noqa: BLE001 - 设置读炸了就当默认允许
        return {}

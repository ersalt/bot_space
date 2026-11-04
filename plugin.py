"""bot_space：bot 的 Markdown 手记（qq-bot-lite api=2 插件入口）。

只做三件事：

- 导出 `tools()`：五个模型工具，写工具受 `allow_write` 控制；
- 挂一个只读面板 `/plugins/bot_space/`，接口全部 GET；
- 固定根目录 `ctx.data_dir / "space"`，不提供用户命令。

设计见仓库 `docs/bot-space.md`；接口契约见 qq-bot-lite `docs/plugin.md`。
"""

from __future__ import annotations

from pathlib import Path

from app.sdk import Extension, PluginContext, Tool
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from .core.space import Limits, SpaceError, SpaceStore
from .core.tools import allow_write, build_tools

VERSION = "0.1.3"
SPACE_LABEL = "data/plugin_data/bot_space/space"

router = APIRouter()
_CONTEXT: PluginContext | None = None
_STORE: SpaceStore | None = None


def _settings() -> dict:
    return _CONTEXT.settings if _CONTEXT is not None else {}


def _limits() -> Limits:
    return Limits.from_settings(_settings())


def _fail(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "message": message}, status_code=status)


def _status_for(exc: SpaceError) -> int:
    if exc.code == "missing":
        return 404
    if exc.code == "exists":
        return 409
    return 400


@router.get("/ping")
async def ping() -> JSONResponse:
    """面板顶部状态：用量、配额、可写模式。"""
    store = _STORE
    if store is None:
        return _fail("插件还没就绪，看看启动日志", 503)
    try:
        stats = store.stats(_limits())
    except SpaceError as exc:
        return _fail(str(exc), 500)
    return JSONResponse(
        {
            "ok": True,
            "version": VERSION,
            "space": SPACE_LABEL,
            "allow_write": allow_write(_settings()),
            **stats,
        }
    )


@router.get("/tree")
async def tree() -> JSONResponse:
    """只读文件列表；面板自己按路径分组。"""
    store = _STORE
    if store is None:
        return _fail("插件还没就绪，看看启动日志", 503)
    try:
        data = store.list_files("", limit=1000)
    except SpaceError as exc:
        return _fail(str(exc), _status_for(exc))
    return JSONResponse({"ok": True, **data})


@router.get("/file")
async def file(path: str = Query(..., min_length=1, max_length=200)) -> JSONResponse:
    """读一篇 Markdown 原文；只读接口，不记审计。"""
    store = _STORE
    if store is None:
        return _fail("插件还没就绪，看看启动日志", 503)
    try:
        data = store.read(path, limit=1_000_000)
    except SpaceError as exc:
        return _fail(str(exc), _status_for(exc))
    return JSONResponse({"ok": True, **data})


@router.get("/audit")
async def audit(limit: int = Query(50, ge=1, le=200)) -> JSONResponse:
    """最近 N 条工具调用；新→旧。"""
    store = _STORE
    if store is None:
        return _fail("插件还没就绪，看看启动日志", 503)
    return JSONResponse({"ok": True, "items": store.recent_audit(limit)})


class BotSpace(Extension):
    name = "bot_space"

    def tools(self) -> list[Tool]:
        if _STORE is None:
            return []
        return build_tools(_STORE, _settings)

    async def on_start(self) -> None:
        if _STORE is not None:
            mode = "可写" if allow_write(_settings()) else "只读"
            self.ctx.log.info("手记就绪（%s，模型%s）", SPACE_LABEL, mode)


def setup(ctx: PluginContext) -> BotSpace:
    global _CONTEXT, _STORE
    _CONTEXT = ctx
    _STORE = None
    if ctx.data_dir is None:
        ctx.log.warning("宿主没有提供 data_dir，手记工具不会启用")
        return BotSpace()

    store = SpaceStore(Path(ctx.data_dir) / "space", log=ctx.log)
    try:
        store.ensure()
    except SpaceError as exc:
        ctx.log.error("手记初始化失败：%s", exc)
    else:
        _STORE = store
        ctx.log.info("手记根目录：%s", SPACE_LABEL)
    return BotSpace()

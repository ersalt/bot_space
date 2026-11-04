"""插件入口：setup、工具注册、只读面板接口。"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from core.space import Limits


@pytest.fixture()
def app(plugin_module, fake_ctx):
    plugin_module.setup(fake_ctx)
    application = FastAPI()
    application.include_router(plugin_module.router, prefix="/plugins/bot_space")
    return application


async def _get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    return await client.get(url)


def test_setup_creates_space_and_tools(plugin_module, fake_ctx) -> None:
    extension = plugin_module.setup(fake_ctx)
    space = fake_ctx.data_dir / "space"
    assert space.is_dir()
    assert plugin_module._STORE is not None
    assert [tool.name for tool in extension.tools()] == [
        "space_list",
        "space_read",
        "space_search",
        "space_create",
        "space_append",
    ]
    assert not hasattr(plugin_module, "COMMANDS"), "bot_space 不提供用户命令"


def test_allow_write_runtime_switch(plugin_module, fake_ctx) -> None:
    extension = plugin_module.setup(fake_ctx)
    fake_ctx.settings["allow_write"] = False
    assert [tool.name for tool in extension.tools()] == [
        "space_list",
        "space_read",
        "space_search",
    ]


def test_setup_without_data_dir_has_no_tools(plugin_module, fake_ctx) -> None:
    fake_ctx.data_dir = None
    extension = plugin_module.setup(fake_ctx)
    assert extension.tools() == []


@pytest.mark.asyncio
async def test_ping_tree_file_audit(plugin_module, fake_ctx, app) -> None:
    store = plugin_module._STORE
    assert store is not None
    await store.append("notes/today.md", "# 今天\n写代码", Limits())
    store.audit("space_append", "notes/today.md", 4, True, session="private:1")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        ping = await _get(client, "/plugins/bot_space/ping")
        assert ping.status_code == 200
        payload = ping.json()
        assert payload["ok"] is True
        assert payload["files"] == 1
        assert payload["allow_write"] is True
        assert payload["max_files"] == 200
        assert payload["space"].endswith("bot_space/space")

        tree = await _get(client, "/plugins/bot_space/tree")
        assert tree.status_code == 200
        files = tree.json()["files"]
        assert [item["path"] for item in files] == ["notes/today.md"]
        assert files[0]["title"] == "今天"

        file = await _get(client, "/plugins/bot_space/file?path=notes/today.md")
        assert file.status_code == 200
        assert file.json()["content"] == "# 今天\n写代码\n"

        audit = await _get(client, "/plugins/bot_space/audit?limit=10")
        assert audit.status_code == 200
        items = audit.json()["items"]
        assert items[0]["tool"] == "space_append"
        assert items[0]["path"] == "notes/today.md"

        missing = await _get(client, "/plugins/bot_space/file?path=missing.md")
        assert missing.status_code == 404
        assert missing.json()["ok"] is False
        assert "不存在" in missing.json()["message"]

        escape = await _get(client, "/plugins/bot_space/file?path=../outside.md")
        assert escape.status_code == 400
        assert escape.json()["ok"] is False


@pytest.mark.asyncio
async def test_file_endpoint_does_not_read_outside(plugin_module, fake_ctx, app) -> None:
    outside = fake_ctx.data_dir.parent / "outside-secret.md"
    outside.write_text("secret", encoding="utf-8")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await _get(client, "/plugins/bot_space/file?path=outside-secret.md")
        assert response.status_code == 404


def test_panel_is_get_only(plugin_module) -> None:
    for route in plugin_module.router.routes:
        methods = getattr(route, "methods", set()) or set()
        assert methods <= {"GET"}, f"{route.path} 暴露了非 GET 方法：{methods}"


@pytest.mark.asyncio
async def test_tools_are_private_and_audited(plugin_module, fake_ctx) -> None:
    extension = plugin_module.setup(fake_ctx)
    from app.sdk import ToolContext

    context = ToolContext(
        plugin="bot_space",
        session_key="private:42",
        is_group=False,
        is_admin=False,
        data_dir=fake_ctx.data_dir,
        log=None,
    )
    tool = next(item for item in extension.tools() if item.name == "space_append")
    result = await tool.handler(context, {"path": "journal/a.md", "text": "日记"})
    assert result["created"] is True
    records = plugin_module._STORE.recent_audit(5)
    assert records[0]["session"] == "private:42"
    assert records[0]["ok"] is True


def test_setup_keeps_root_inside_data_dir(plugin_module, fake_ctx) -> None:
    plugin_module.setup(fake_ctx)
    root = plugin_module._STORE.root
    assert root == (fake_ctx.data_dir / "space").resolve()
    assert root.is_dir()

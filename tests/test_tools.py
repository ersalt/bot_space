"""工具层：schema、只读/写权限、审计、配额错误。"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.sdk import ToolContext

from core.space import SpaceError, SpaceStore
from core.tools import build_tools


@pytest.fixture()
def store(tmp_path: Path) -> SpaceStore:
    instance = SpaceStore(tmp_path / "space")
    instance.ensure()
    return instance


def _ctx(session: str = "private:1") -> ToolContext:
    return ToolContext(
        plugin="bot_space",
        session_key=session,
        is_group=False,
        is_admin=True,
        data_dir=None,
        log=None,
    )


def _tool(tools, name: str):
    return next(item for item in tools if item.name == name)


def _names(tools) -> list[str]:
    return [item.name for item in tools]


def test_read_tools_always_present(store: SpaceStore) -> None:
    tools = build_tools(store, lambda: {})
    assert _names(tools) == ["space_list", "space_read", "space_search", "space_create", "space_append"]


def test_allow_write_off_hides_write_tools(store: SpaceStore) -> None:
    settings = {"allow_write": False}
    tools = build_tools(store, lambda: settings)
    assert _names(tools) == ["space_list", "space_read", "space_search"]
    settings["allow_write"] = True
    assert "space_append" in _names(build_tools(store, lambda: settings))
    settings["allow_write"] = "false"
    assert "space_append" not in _names(build_tools(store, lambda: settings))


@pytest.mark.asyncio
async def test_tools_roundtrip(store: SpaceStore) -> None:
    tools = build_tools(store, lambda: {})
    ctx = _ctx()

    appended = await _tool(tools, "space_append").handler(
        ctx, {"path": "notes/today.md", "text": "# 今天\n写代码"}
    )
    assert appended["created"] is True
    assert appended["path"] == "notes/today.md"

    read = await _tool(tools, "space_read").handler(ctx, {"path": "notes/today.md"})
    assert read["content"] == "# 今天\n写代码\n"

    listing = await _tool(tools, "space_list").handler(ctx, {})
    assert listing["total"] == 1
    assert listing["files"][0]["title"] == "今天"

    found = await _tool(tools, "space_search").handler(ctx, {"query": "代码"})
    assert found["total"] == 1
    assert found["hits"][0]["line"] == 2

    created = await _tool(tools, "space_create").handler(
        ctx, {"path": "journal/day.md", "text": "# 日记\n"}
    )
    assert created["created"] is True

    records = store.recent_audit(10)
    assert {item["tool"] for item in records} == {
        "space_append",
        "space_read",
        "space_list",
        "space_search",
        "space_create",
    }
    assert all(item["ok"] for item in records)
    assert all(item["session"] == "private:1" for item in records)


@pytest.mark.asyncio
async def test_create_existing_returns_space_error(store: SpaceStore) -> None:
    tools = build_tools(store, lambda: {})
    ctx = _ctx()
    await _tool(tools, "space_create").handler(ctx, {"path": "a.md", "text": "一"})
    with pytest.raises(SpaceError, match="已存在"):
        await _tool(tools, "space_create").handler(ctx, {"path": "a.md", "text": "二"})
    records = store.recent_audit(5)
    assert records[0]["ok"] is False
    assert "已存在" in records[0]["error"]


@pytest.mark.asyncio
async def test_bad_arguments(store: SpaceStore) -> None:
    ctx = _ctx()
    tools = build_tools(store, lambda: {})
    with pytest.raises(SpaceError, match="path"):
        await _tool(tools, "space_read").handler(ctx, {})
    with pytest.raises(SpaceError, match="text"):
        await _tool(tools, "space_append").handler(ctx, {"path": "a.md", "text": "  "})
    with pytest.raises(SpaceError, match="offset"):
        await _tool(tools, "space_read").handler(ctx, {"path": "a.md", "offset": "abc"})
    with pytest.raises(SpaceError):
        await _tool(tools, "space_list").handler(ctx, {"dir": "../outside"})


@pytest.mark.asyncio
async def test_quota_error_reaches_model_as_exception(store: SpaceStore) -> None:
    settings = {"max_file_kb": 1}
    tools = build_tools(store, lambda: settings)
    with pytest.raises(SpaceError, match="单文件"):
        await _tool(tools, "space_append").handler(
            _ctx(), {"path": "big.md", "text": "x" * 2000}
        )


@pytest.mark.asyncio
async def test_read_chars_setting(store: SpaceStore) -> None:
    await store.create("long.md", "字" * 1500, store_limits())
    settings = {"read_chars": 1000}
    tools = build_tools(store, lambda: settings)
    result = await _tool(tools, "space_read").handler(_ctx(), {"path": "long.md"})
    assert len(result["content"]) == 1000
    assert result["truncated"] is True
    assert result["total_chars"] == 1500


@pytest.mark.asyncio
async def test_search_hits_setting(store: SpaceStore) -> None:
    await store.create("a.md", "命中\n命中\n命中\n", store_limits())
    settings = {"search_hits": 2}
    tools = build_tools(store, lambda: settings)
    result = await _tool(tools, "space_search").handler(_ctx(), {"query": "命中"})
    assert len(result["hits"]) == 2
    assert result["truncated"] is True


def store_limits():
    from core.space import Limits

    return Limits()


def test_schemas_are_openai_functions(store: SpaceStore) -> None:
    tools = build_tools(store, lambda: {})
    for item in tools:
        schema = item.schema()
        assert schema["type"] == "function"
        function = schema["function"]
        assert function["name"] == item.name
        assert function["description"]
        assert function["parameters"]["type"] == "object"
        assert function["parameters"]["additionalProperties"] is False

    read = _tool(tools, "space_read")
    assert read.parameters["required"] == ["path"]
    append = _tool(tools, "space_append")
    assert append.parameters["required"] == ["path", "text"]
    assert append.read_only is False
    assert _tool(tools, "space_list").read_only is True

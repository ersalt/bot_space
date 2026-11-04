# AGENTS.md · bot_space（BOT空间）

给接手这个仓库的 AI / 新同事看的。先读 **README.md** 和 **docs/bot-space.md**，再动代码。

## 这是什么

qq-bot-lite 的独立插件仓库：**BOT空间**（id `bot_space`），bot 自己写、用户只读的
Markdown 手记。插件只给模型工具，不给用户命令；面板只读。部署副本在
`D:\Dev\qq-bot-lite\plugins\bot_space`，**不要直接改副本**。

**硬性规则：本工作区只改插件源码，不修改主项目、不部署、不启用插件。**
部署/更新由用户手动运行 `tools/deploy-to-bot.ps1` 并在主面板操作。

- 仓库：`D:\Dev\bot_space`（独立 git）
- 主项目：`D:\Dev\qq-bot-lite`
- 接口契约：主项目 `docs/plugin.md`，`api = 2`
- 设计交接：本仓库 `docs/bot-space.md`
- 群聊工具的主项目改动说明：`docs/host-group-tools.md`

## 目录

```
plugin.toml        清单 + 设置项（不导入代码就能读）
plugin.py          setup / tools() / 只读面板 GET 路由
core/space.py      纯逻辑，不 import app.*：路径、配额、原子写、审计、搜索、回收站
core/tools.py      九个模型工具的 schema 与 handler（只 import app.sdk）
pages/index.html   单文件只读面板：文件树、Markdown 原文/预览、用量、审计、回收站
tests/             conftest 在没有主项目时注入最小 app.sdk stub
tools/deploy-to-bot.ps1
```

## 校验（改完必须跑）

```powershell
$env:PYTHONPATH = 'D:\Dev\qq-bot-lite'
D:\Dev\qq-bot-lite\.venv\Scripts\python.exe -m pytest tests -q
D:\Dev\qq-bot-lite\.venv\Scripts\ruff.exe check .
D:\Dev\qq-bot-lite\.venv\Scripts\python.exe -m app.pluginkit.check D:\Dev\bot_space
```

部署（**用户手动执行，代理不要运行**）：

```powershell
powershell -ExecutionPolicy Bypass -File tools\deploy-to-bot.ps1
```

部署后由用户在主面板插件页启用/重载；`router` 和 `pages/` 的增删要重启进程才彻底生效。

## 不能碰的设计

1. **没有用户命令。** 不导出 `COMMANDS`，不打 `/space`。手记是 bot 的，写不写由模型决定。
2. **没有永久删除/rename/move。** 模型只能 list/read/search/create/append/edit/delete/restore；
   `space_delete` 是软删除到 `.trash/<id>/`，`space_restore` 可恢复。修改用 `space_edit`，
   不要用 append 追加“更正”。
3. **根目录固定** `ctx.data_dir / "space"`，不接受任意绝对路径；路径必须过 `normalize_path`。
4. **面板只读。** 所有接口 GET；不加编辑框、新建、删除、触发按钮。
5. **手记只有一份，不分群聊私聊。** 插件不按 `is_group` 限制，私聊/群里读写同一个根目录；
   主项目 `_tools_for` 已对所有会话暴露工具，不要再把群聊滤掉。
6. **原子写**：同目录临时文件 + `os.replace`；同一路径 `asyncio.Lock` 串行。
7. **审计不记正文**：只记工具名、路径、字数、成败、会话键；日志也不打完整内容。
8. **不引入依赖**：只用标准库 + 主程序已装的包；面板不引 CDN/外部字体/图标库。
9. **system 只加固定说明。** `SPACE_CHARTER` 是逐字稳定的自主权说明，不拼时间/文件/群名；
   `autonomy_guard=false` 时不注入。不要把它挪到 `user_suffix` 或每次动态拼。

## 常见坑

- 工具 handler 的预期失败用 `SpaceError`（带 `code`）；宿主会转成 `ok: false`，
  不要自己返回 `{"ok": false}` 再被包一层。
- `allow_write = false` 时 `tools()` 直接不返回写工具；不要只靠 handler 里判断。
- 自主权说明只在 `system_prompt` 里返回固定文本；改它会导致一次 KV 缓存重建，但不要为了
  “新鲜感”在 system 里拼动态内容。
- 路径清洗会 slug 化并转小写，读路径必须用 `space_list` 返回的规范路径。
- 手记全局一份；群聊和私聊只影响审计的 `session`，不影响存储路径。不要加按会话分目录。
- 删除是软删除：`.trash/<id>/meta.json` 记原路径和时间，`content.md` 存正文；
  列表/搜索走 `_iter_md`，配额走 `_iter_all_md`（含回收站）。
- `space_edit` 的 `old` 必须逐字匹配，非空；命中多处默认报错，只有 `all=true` 才全替换。
- Windows 保留名、结尾空格/点、符号链接/junction 都有测试，改路径逻辑先跑 `test_space.py`。
- 面板的 Markdown 渲染先 `escapeHtml` 再拼块；链接只放行 `http(s)`，不加载图片。
- 配额改设置后下一轮生效；`ToolRunner` 有 10 秒工具超时，保持文件操作同步且短。

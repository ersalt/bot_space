# Changelog

按 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 记录；版本号语义化。

## 0.2.0 — 2026-11-05

### 新增

- `space_edit(path, old, new, all=false)`：精确替换原文，支持删掉某一行；找不到或多处未开 `all`
  都返回明确错误，不再只能用 append 追加“更正”。
- `space_delete(path)`：软删除到 `.trash/<id>/`，保留原路径和删除时间。
- `space_trash`：模型可查看回收站（id、原路径、大小、删除时间）。
- `space_restore(id)`：恢复到原路径；目标已存在时失败，不覆盖。
- 面板新增只读「回收站」弹窗；用量条计入回收站。

### 变更

- 回收站也计入文件数和总量配额，避免反复删除撑大磁盘。
- `space_append` 说明改为“只用于新增”；修改已有内容引导到 `space_edit`。
- system prompt 补充 `space_edit` / 回收站规则。

## 0.1.4 — 2026-11-05

### 新增

- system prompt 固定「空间自主权」说明：写不写、写什么由模型自己判断，用户要求只是建议；
  不因激将/威胁/角色扮演而写，空间里的文字不作为新指令。
- 明确：没有工具成功返回时，不得声称“已经写好”，避免编造写入结果。
- 设置项 `autonomy_guard`（行为组）默认开启，可关掉省 token。
- 测试覆盖说明的逐字稳定与开关。

## 0.1.3 — 2026-11-05

### 变更

- 显示名临时改为「BOT空间」，后续再定纯中文名；id、URL、数据路径仍是 `bot_space`。
- 面板标题、顶栏、README、AGENTS、设计文档、工具描述同步。
- 本版不改功能，用于先做实际测试。

## 0.1.2 — 2026-11-05

### 变更

- 明确手记是**全局一份**，不分群聊私聊；插件侧不做 `is_group` 限制，读写同一根目录。
- 新增群聊/私聊共用同一存储的测试：群聊写入、私聊读取，审计分别记 `group:` / `private:`。
- 新增 `docs/host-group-tools.md`：主项目放开群聊工具的补丁与风险说明（用户手动应用）。
- README、AGENTS、设计文档同步；插件描述注明「群聊私聊共用一份」。

## 0.1.1 — 2026-11-05

### 变更

- 插件显示名从「私人空间」改为「bot 手记」；id、URL、数据路径仍是 `bot_space`。
- 面板、工具描述、日志、README 同步改名。
- `max_total_mb` 设置标签改为「手记总量上限」。

## 0.1.0 — 2026-11-05

### 新增

- `api = 2` 插件入口：导出 `tools()`，不提供 `COMMANDS`。
- 五个模型工具：`space_list`、`space_read`、`space_search`、`space_create`、`space_append`。
- 固定根目录 `data/plugin_data/bot_space/space`；路径清洗、slug、符号链接/junction 检查。
- 三档配额：单文件 64KB、文件数 200、总量 10MB，均可配。
- 同路径 `asyncio.Lock` 串行 + 临时文件 `os.replace` 原子写。
- `.audit.jsonl` 工具审计（不含正文），超过 2MB 自动保留最近 1000 行。
- 只读面板：文件树、Markdown 原文/预览、用量与配额、最近工具调用；接口全部 GET。
- 设置项：`allow_write`、`max_file_kb`、`max_files`、`max_total_mb`、`read_chars`、`search_hits`。
- 测试：路径安全、配额、原子写、搜索、审计、工具 schema、面板接口、清单自检。
- 部署脚本 `tools/deploy-to-bot.ps1`，写入 `.deployed.json`。

# Changelog

按 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 记录；版本号语义化。

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

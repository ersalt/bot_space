"""把插件打成可直接在主面板「安装 ZIP」导入的干净包。

只收集运行时要用的文件，不带 .git / tests / docs / 缓存。
ZIP 结构是 bot_space/plugin.toml，主面板会按顶层目录识别插件 id。

    python tools/package_plugin.py

输出：dist/bot_space-<version>.zip
"""

from __future__ import annotations

import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
PLUGIN_ID = "bot_space"
INCLUDE_FILES = ("plugin.toml", "plugin.py", "README.md", "CHANGELOG.md", "LICENSE")
INCLUDE_DIRS = ("core", "pages")
SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache", ".ruff_cache", ".venv"}
SKIP_SUFFIXES = {".pyc", ".pyo"}


def _iter_files(base: Path):
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if set(relative.parts) & SKIP_DIRS:
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        yield path


def build() -> Path:
    for name in INCLUDE_FILES:
        if not (ROOT / name).is_file():
            raise SystemExit(f"missing runtime file: {name}")
    if not (ROOT / "core" / "__init__.py").is_file():
        raise SystemExit("missing core/__init__.py")
    if not (ROOT / "pages" / "index.html").is_file():
        raise SystemExit("missing pages/index.html")

    manifest = tomllib.loads((ROOT / "plugin.toml").read_text(encoding="utf-8"))
    version = str(manifest.get("version") or "0.0.0")
    DIST.mkdir(parents=True, exist_ok=True)
    target = DIST / f"{PLUGIN_ID}-{version}.zip"

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in INCLUDE_FILES:
            archive.write(ROOT / name, f"{PLUGIN_ID}/{name}")
        for dirname in INCLUDE_DIRS:
            for path in _iter_files(ROOT / dirname):
                archive.write(path, f"{PLUGIN_ID}/{path.relative_to(ROOT).as_posix()}")

    with zipfile.ZipFile(target) as archive:
        names = archive.namelist()
    bad = [
        name
        for name in names
        if any(part in {".git", "tests", "tools", "docs", "__pycache__"} for part in Path(name).parts)
    ]
    if bad:
        target.unlink(missing_ok=True)
        raise SystemExit(f"package contains dev files: {bad[:5]}")
    if not names:
        raise SystemExit("package is empty")
    return target


def main() -> int:
    target = build()
    with zipfile.ZipFile(target) as archive:
        names = archive.namelist()
    print(f"OK: {target}")
    print(f"files={len(names)} size={target.stat().st_size / 1024:.1f}KB")
    print("Install via main panel: Plugins -> Install ZIP")
    return 0


if __name__ == "__main__":
    sys.exit(main())

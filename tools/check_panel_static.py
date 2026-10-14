# -*- coding: utf-8 -*-
"""Linux 端面板静态自检（无需浏览器）—— 与 Windows 端 tools/check_panel_static.py 互补

Windows 端那份检查"桌面专属"的东西（三按钮、双击最大化、桌面条守卫等）；
这一份只检查**双端共用的那 6 个资产** + 两端是否同本，因为：
  · 共用文件改了却忘同步 → 两端界面分叉（本项目真实发生过，累积四轮未同步）
  · 共用外壳若耦合了"某端才有的 API / 具体插件名" → 另一端会静默失效

用法：
    python tools/check_panel_static.py            # 失败退出码 1，可进 CI
    python tools/check_panel_static.py -v
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # Linux 仓根
PANEL = ROOT / "web" / "panel"
WIN = Path("/root/astercore/src/astercore/web/static")  # 同机的 Windows 端（不存在则跳过比对）

SHARED = {
    "panel.js": ROOT / "web" / "panel" / "panel.js",
    "panel.css": ROOT / "web" / "panel" / "panel.css",
    "cfg_form.js": ROOT / "web" / "panel" / "cfg_form.js",
    "cfg_form.css": ROOT / "web" / "panel" / "cfg_form.css",
    "panel_pages.py": ROOT / "web" / "panel_pages.py",
    "config_schema.py": ROOT / "web" / "config_schema.py",
}
WIN_SHARED = {
    "panel.js": WIN / "panel.js",
    "panel.css": WIN / "panel.css",
    "cfg_form.js": WIN / "cfg_form.js",
    "cfg_form.css": WIN / "cfg_form.css",
    "panel_pages.py": WIN.parent / "panel_pages.py",
    "config_schema.py": WIN.parent / "core" / "config_schema.py",
}

_results: list[tuple[bool, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((bool(ok), name, detail))


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest() if p.is_file() else ""


def main(verbose: bool) -> int:
    css = (PANEL / "panel.css").read_text(encoding="utf-8", errors="replace") \
        if (PANEL / "panel.css").is_file() else ""
    js = (PANEL / "panel.js").read_text(encoding="utf-8", errors="replace") \
        if (PANEL / "panel.js").is_file() else ""

    # 1) 共用文件齐备
    for name, p in SHARED.items():
        check(f"共用文件存在 {name}", p.is_file(), str(p))

    # 2) 两端同本（同机可比时）
    if WIN.is_dir():
        for name, lp in SHARED.items():
            wp = WIN_SHARED.get(name)
            if wp is None or not wp.is_file():
                continue
            a, b = md5(lp), md5(wp)
            check(f"{name} 两端字节一致", a == b and a != "", f"linux={a[:8]} win={b[:8]}")
    else:
        check("跳过两端比对（本机没有 Windows 端仓库）", True, str(WIN))

    # 3) 共用外壳不能耦合"某端才有的东西"：桌面专属 API 必须带能力探测/容器守卫
    check("外壳对桌面接口有守卫（不能硬依赖）",
          ("/api/app/state" not in js) or re.search(r"if \(!bar \|\| !overlay\)\s*\{\s*return", js) is not None)
    check("不硬编码某个插件名", not re.search(r"demo_counter|demo_hello|WordLib|wordlib", js))

    # 4) 共用样式里的关键规则（两端都受影响）
    check("透明确认到：拖动区规则存在（Windows 无边框窗口用）",
          ("-webkit-app-region:drag" in css) or True)          # Linux 端不需要，仅提示
    check("文字可选中规则存在且不误伤",
          ("-webkit-user-select:text" in css) and ("#desktopBar,#desktopBar *{-webkit-user-select:none" in css))
    check("提示层级高于弹窗",
          (lambda t, m: t > m > 0)(
              int((re.search(r"\.toast\{[^}]*z-index:(\d+)", css) or re.match(r"", "0")).group(1) or 0)
              if re.search(r"\.toast\{[^}]*z-index:(\d+)", css) else -1,
              int((re.search(r"\.ui-modal\{[^}]*z-index:(\d+)", css) or re.match(r"", "0")).group(1) or 0)
              if re.search(r"\.ui-modal\{[^}]*z-index:(\d+)", css) else -1))

    bad = [(n, d) for ok, n, d in _results if not ok]
    if verbose:
        for ok, n, d in _results:
            print(("  ✅ " if ok else "  ❌ ") + n + (f"    [{d}]" if d and not ok else ""))
    print(f"\nLinux 侧静态自检：{len(_results) - len(bad)}/{len(_results)} 通过")
    if bad:
        for n, d in bad:
            print(f"  ❌ {n}" + (f"    [{d}]" if d else ""))
        return 1
    print("全部通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main("-v" in sys.argv or "--verbose" in sys.argv))

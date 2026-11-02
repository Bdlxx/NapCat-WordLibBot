# -*- coding: utf-8 -*-
"""群状态指令（`#状态`）：从词库插件迁到主程序，并把结果渲染成图片发送。

迁出来的两个原因：
  1. 原来在词库插件里 → 词库在某个群被关掉就看不到状态了；
  2. 纯文本不好看，现在用 PIL 画成卡片图（不启浏览器，见 status_card.py 的说明）。
"""
import base64
import json
import os

import utils.status_card as _card
from utils.api import send_message

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_C_FG = {"on": "#15803d", "off": "#94a3b8", "mode": "#6d28d9"}
_C_BG = {"on": "#e9f8f0", "off": "#f2f4f8", "mode": "#f3ecff"}


def _cfg(key, default=None):
    try:
        from utils.config import get_config
        return get_config(key, default)
    except Exception:
        return default


def status_words():
    w = _cfg("STATUS_COMMAND", None)
    if isinstance(w, (list, tuple)):
        out = [str(x).strip() for x in w if str(x).strip()]
        if out:
            return out
    elif isinstance(w, str) and w.strip():
        return [w.strip()]
    return ["#状态"]


def _plugin_rows(gid):
    """[(中文名, 状态文本, 颜色, 是否子行)] —— 只保留中文名与开关状态；伪人模式挂在 AI 对话下面"""
    rows = []
    try:
        import utils.plugin_toggle as pt
        meta = pt.get_plugin_meta(None, os.path.join(_BASE, "plugins")) or {}
        order = ["wordlib", "pseudo", "video_parser", "marry", "jm_downloader"]
        keys = [k for k in order if k in meta] + [k for k in meta if k not in order]
        for k in keys:
            m = meta.get(k) or {}
            on = bool(pt.is_enabled(gid, k))
            rows.append((m.get("name_cn") or k, "是" if on else "否",
                         (_C_FG["on"], _C_BG["on"]) if on else (_C_FG["off"], _C_BG["off"]), False))
            if k == "pseudo":
                if on:
                    m2 = _group_mode(gid)
                    _m = m2 == "pseudo"
                    rows.append(("伪人模式", "伪人模式" if _m else "普通模式",
                                 (_C_FG["mode"], _C_BG["mode"]) if _m else (_C_FG["off"], _C_BG["off"]), True))
                else:
                    rows.append(("伪人模式", "否", (_C_FG["off"], _C_BG["off"]), True))
    except Exception as e:
        print(f"[状态] 读插件开关失败: {e}")
    return rows


def _group_mode(gid):
    try:
        with open(os.path.join(_BASE, "data", "persona_config.json"), encoding="utf-8") as f:
            pc = json.load(f)
    except Exception:
        return "normal"
    gm = (pc.get("group_chat_modes") or {}).get(str(gid))
    m = str(gm or pc.get("chat_mode") or "normal").strip().lower()
    return "pseudo" if m == "pseudo" else "normal"


def _chat_mode_desc(gid):
    try:
        with open(os.path.join(_BASE, "data", "persona_config.json"), encoding="utf-8") as f:
            pc = json.load(f)
    except Exception:
        return ""
    gm = (pc.get("group_chat_modes") or {}).get(str(gid))
    m = str(gm or pc.get("chat_mode") or "normal").strip().lower()
    if m == "pseudo":
        return "🤖 AI 对话模式：伪人模式（会主动接话）"
    return "🤖 AI 对话模式：普通模式（只认 @ 与唤醒词）"


def _send_png(event, path):
    try:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        send_message(event, [{"type": "image", "data": {"file": "base64://" + b64}}])
        return True
    except Exception as e:
        print(f"[状态] 图片发送失败: {e}")
        return False


def try_handle(event):
    """命中 #状态 就处理并返回 True；否则 False（交回插件链）"""
    raw = (event.get("raw_message") or "").strip()
    words = status_words()
    if raw not in words:
        return False
    if event.get("message_type") != "group":
        send_message(event, f"「{words[0]}」要在群里发哦（每个群的插件开关是独立的）")
        return True

    gid = str(event.get("group_id"))
    gname = ""
    try:
        from utils.log import get_group_name
        gname = get_group_name(event.get("group_id")) or ""
    except Exception:
        pass
    from datetime import datetime
    try:
        import zoneinfo
        now = datetime.now(zoneinfo.ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M")
    except Exception:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

    rows = _plugin_rows(gid)
    title = f"群状态 · {gname or '本群'}"
    subtitle = f"群号 {gid} · {now}"
    try:
        path = _card.render_status(title, subtitle, rows,
                                   footer=f"{_cfg('BOT_NAME', '')} · 自动生成")
    except Exception as e:
        print(f"[状态] 渲染失败，回退纯文本: {e}")
        lines = [f"📋 {title}", f"群号 {gid}"]
        lines += [("  " if (len(r) > 3 and r[3]) else "") + f"{'🟢' if r[1] == '是' else '⚪'} {r[0]}：{r[1]}"
                  for r in rows]
        send_message(event, "\n".join(lines))
        return True
    if not _send_png(event, path):
        lines = [f"📋 {title}"] + [f"{r[0]}：{r[1]}" for r in rows]
        send_message(event, "\n".join(lines))
    print(f"[状态] 已发送群状态图（{len(rows)} 个插件）: {path}")
    return True

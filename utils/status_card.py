# -*- coding: utf-8 -*-
"""群状态卡片（PIL 直绘，不用浏览器）。

设计目标：像正经 App 的「设置」页 —— 白卡片 + 柔和底色 + 左侧圆点 + 右侧胶囊徽章，
不再是一行行裸文字。尺寸 **750×1000（竖屏 4:3）**，2 倍图便于 QQ 里看清。

配色取自面板设计令牌（与 Web 面板观感一致）：
  背景 #eef1f7 · 卡片 #fff · 主文 #1f2937 · 次文 #94a3b8
  开 #16a34a/#e9f8f0 · 关 #94a3b8/#f2f4f8 · 伪人 #7c3aed/#f3ecff
字体：assets/fonts/HanaSC-{Regular,Bold}.ttf（鸿蒙黑体子集）
"""
import os
import time

from PIL import Image, ImageDraw, ImageFont

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CACHE = {}

W, H = 750, 1000          # 竖屏 4:3（高:宽 = 4:3）
M = 40                    # 卡片外边距
PAD = 44                  # 卡片内边距


def _font_dirs():
    out = [os.path.join(_BASE, "assets", "fonts")]
    p = _BASE
    for _ in range(4):
        p = os.path.dirname(p)
        if not p or p == "/":
            break
        out.append(os.path.join(p, "assets", "fonts"))
    return [d for d in out if os.path.isdir(d)]


_FONT_DIR = (_font_dirs() or [os.path.join(_BASE, "assets", "fonts")])[0]


def _font(bold=False, size=18):
    key = (bold, size)
    if key in _CACHE:
        return _CACHE[key]
    path = os.path.join(_FONT_DIR, "HanaSC-Bold.ttf" if bold else "HanaSC-Regular.ttf")
    try:
        f = ImageFont.truetype(path, size)
    except Exception:
        f = ImageFont.load_default()
    _CACHE[key] = f
    return f


def _avatar(path, size, radius):
    """把群头像裁成圆角方块（取不到就返回 None，由调用方画兜底）"""
    try:
        im = Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
    except Exception:
        return None
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size, size], radius=radius, fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    return out


def _switch(d, right, cy, on, on_color="#22c55e", w=76, h=40):
    """右侧开关样式：药丸轨道 + 右侧/左侧白色圆钮"""
    x1, y1 = right - w, cy - h / 2
    d.rounded_rectangle([x1, y1, right, y1 + h], radius=h / 2,
                        fill=on_color if on else "#d3dbe6")
    kr = h / 2 - 4
    kx = (right - kr - 4) if on else (x1 + kr + 4)
    d.ellipse([kx - kr, cy - kr, kx + kr, cy + kr], fill="#ffffff",
              outline=None if on else "#c3cddb", width=1)


def render_status(title, subtitle, rows, out_path=None, footer=None, avatar=None):
    """rows: [{"name": 名称, "on": bool, "kind": "on|off|mode", "indent": bool, "label": 可选小字}]"""
    img = Image.new("RGB", (W, H), "#eef1f7")
    d = ImageDraw.Draw(img)

    d.rounded_rectangle([M, M + 6, W - M, H - M + 6], radius=26, fill="#e3e8f1")
    d.rounded_rectangle([M, M, W - M, H - M], radius=26, fill="#ffffff")

    # ===== 顶部：群头像 + 群名/群号 =====
    av_size, av_x, av_y = 92, M + PAD - 12, M + 44
    box = _avatar(avatar, av_size, 24) if avatar else None
    if box is not None:
        img.paste(box, (av_x, av_y), box)
        d.rounded_rectangle([av_x, av_y, av_x + av_size, av_y + av_size], radius=24, outline="#eef1f6", width=2)
    else:
        d.rounded_rectangle([av_x, av_y, av_x + av_size, av_y + av_size], radius=24, fill="#eef2f9")
        d.text((av_x + av_size / 2, av_y + av_size / 2), (title or "群")[:1],
               font=_font(True, 38), fill="#9fb0c4", anchor="mm")

    tx = av_x + av_size + 24
    d.text((tx, av_y + 16), title, font=_font(True, 32), fill="#1b2432")
    d.text((tx, av_y + 62), subtitle, font=_font(False, 17), fill="#5d6b7c")

    # 右上角小标签
    tag = "群状态"
    tw = d.textlength(tag, font=_font(True, 14))
    d.rounded_rectangle([W - M - PAD + 12 - tw - 24, M + 52, W - M - PAD + 12, M + 52 + 30],
                        radius=15, fill="#eef4ff")
    d.text((W - M - PAD + 12 - 12 - tw / 2, M + 67), tag, font=_font(True, 14), fill="#2563eb", anchor="mm")

    d.line([M + 24, M + 176, W - M - 24, M + 176], fill="#eef1f6", width=2)

    # 行区：左侧中文名，右侧开关
    top, bottom = M + 196, H - M - 76
    n = max(1, len(rows))
    row_h = (bottom - top) / n
    font_name, font_sub = _font(False, 22), _font(False, 19)
    for i, row in enumerate(rows):
        name = row.get("name") or ""
        on = bool(row.get("on"))
        kind = row.get("kind") or ("on" if on else "off")
        indent = bool(row.get("indent"))
        label = row.get("label") or ""
        cy = top + row_h * i + row_h / 2
        x = M + PAD + (34 if indent else 0)
        d.text((x, cy), name, font=(font_sub if indent else font_name),
               fill="#5b6b7e" if indent else "#243244", anchor="lm")
        color = "#8b5cf6" if kind == "mode" else "#22c55e"
        if label:
            lw = d.textlength(label, font=_font(False, 15))
            d.text((W - M - PAD - 92 - lw, cy), label, font=_font(False, 15),
                   fill="#8b5cf6" if kind == "mode" else "#8b97a6", anchor="lm")
        _switch(d, W - M - PAD, cy, on, color)
        if i < n - 1:
            d.line([M + PAD, cy + row_h / 2, W - M - PAD, cy + row_h / 2], fill="#f4f6fa", width=1)

    d.text((W / 2, H - M - 34), footer or "", font=_font(False, 15), fill="#8b97a6", anchor="mm")

    if out_path is None:
        out_dir = os.path.join(_BASE, "data", "status_img")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"status_{int(time.time() * 1000)}.png")
    img.save(out_path, "PNG")
    return out_path

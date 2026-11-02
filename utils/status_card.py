# -*- coding: utf-8 -*-
"""把「群状态」画成图片（PIL 直绘，不依赖浏览器）。

为什么不用截图方案：跑 Chromium 一次要 1.5s + 300MB，三个实例同时来会顶爆内存；
haruka 插件当初也明确"不走 playwright 截图"，这里保持同一取舍。
字体用鸿蒙黑体子集（assets/fonts/HanaSC-{Regular,Bold}.ttf）。
"""
import os
import time
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 实例根目录（或仓库根）


def _font_dirs():
    """字体目录候选：实例下的 assets/fonts → 往上找到仓库根下的 assets/fonts"""
    out = [os.path.join(_BASE, "assets", "fonts")]
    p = _BASE
    for _ in range(4):
        p = os.path.dirname(p)
        if not p or p == "/":
            break
        out.append(os.path.join(p, "assets", "fonts"))
    return [d for d in out if os.path.isdir(d)]


_FONT_DIR = (_font_dirs() or [os.path.join(_BASE, "assets", "fonts")])[0]
_CACHE = {}

W = 760            # 画布宽
PAD = 28           # 卡片内边距
GAP = 10


def _font(bold=False, size=18):
    key = (bold, size)
    if key in _CACHE:
        return _CACHE[key]
    name = "HanaSC-Bold.ttf" if bold else "HanaSC-Regular.ttf"
    path = os.path.join(_FONT_DIR, name)
    try:
        f = ImageFont.truetype(path, size)
    except Exception:
        f = ImageFont.load_default()
    _CACHE[key] = f
    return f


def _text_h(font):
    box = font.getbbox("汉字Ag")
    return box[3] - box[1]


def render_status(title, subtitle, rows, footer=None, out_path=None):
    """rows: [(名称, 说明, 状态文本, 状态色)]；footer: 末尾一行说明"""
    row_h = 46
    head_h = 96
    body_h = row_h * len(rows)
    foot_h = 40 if footer else 0
    h = head_h + body_h + foot_h + PAD * 2

    img = Image.new("RGB", (W, h), "#f6f8fb")
    d = ImageDraw.Draw(img)

    # 外卡片
    d.rounded_rectangle([12, 12, W - 12, h - 12], radius=16, fill="#ffffff", outline="#e3e8f0")

    # 标题 + 副标题
    d.text((PAD, 26), title, font=_font(True, 24), fill="#1f2937")
    d.text((PAD, 60), subtitle, font=_font(False, 13), fill="#7b8794")

    y = head_h + PAD - 8
    d.line([PAD, y - 10, W - PAD, y - 10], fill="#eef2f7")
    for name, desc, state, color in rows:
        d.text((PAD, y + 6), name, font=_font(True, 17), fill="#263445")
        if desc:
            d.text((PAD + 150, y + 9), desc, font=_font(False, 12), fill="#8b97a6")
        tw = d.textlength(state, font=_font(True, 15))
        d.text((W - PAD - tw, y + 6), state, font=_font(True, 15), fill=color)
        y += row_h
        d.line([PAD, y - 8, W - PAD, y - 8], fill="#f2f5f9")

    if footer:
        d.text((PAD, y + 6), footer, font=_font(False, 12), fill="#8b97a6")

    if out_path is None:
        out_dir = os.path.join(_BASE, "data", "status_img")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"status_{int(time.time() * 1000)}.png")
    img.save(out_path, "PNG")
    return out_path

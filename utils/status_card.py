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


def _pill(d, right, cy, text, fg, bg, font):
    """右侧胶囊徽章：底色圆角 + 居中文字，返回左边界 x"""
    tw = d.textlength(text, font=font)
    pw, ph = tw + 28, 32
    x1, y1 = right - pw, cy - ph / 2
    d.rounded_rectangle([x1, y1, right, cy + ph / 2], radius=ph / 2, fill=bg)
    d.text(((x1 + right) / 2, cy), text, font=font, fill=fg, anchor="mm")
    return x1


def render_status(title, subtitle, rows, out_path=None, footer=None):
    """rows: [(名称, 状态文本, (前景色, 底色), 是否子行)]"""
    img = Image.new("RGB", (W, H), "#eef1f7")
    d = ImageDraw.Draw(img)

    # 卡片 + 极淡投影
    d.rounded_rectangle([M, M + 6, W - M, H - M + 6], radius=26, fill="#e3e8f1")
    d.rounded_rectangle([M, M, W - M, H - M], radius=26, fill="#ffffff")

    # 顶部标题区
    d.text((PAD + M - 24, M + 52), title, font=_font(True, 34), fill="#1b2432")
    d.text((PAD + M - 24, M + 104), subtitle, font=_font(False, 17), fill="#7c8898")
    # 右上角小标签
    tag = "群状态"
    tw = d.textlength(tag, font=_font(True, 15))
    d.rounded_rectangle([W - M - PAD + 24 - tw - 26, M + 46, W - M - PAD + 24, M + 46 + 34],
                        radius=17, fill="#eef4ff")
    d.text((W - M - PAD + 24 - 13 - tw / 2, M + 63), tag, font=_font(True, 15), fill="#2563eb", anchor="mm")

    d.line([M + 24, M + 158, W - M - 24, M + 158], fill="#eef1f6", width=2)

    # 行区：左侧「首字方块」图标（不依赖 emoji 字体）+ 名称 + 右侧紧凑徽章
    top, bottom = M + 176, H - M - 76
    n = max(1, len(rows))
    row_h = (bottom - top) / n
    font_name, font_sub = _font(False, 21), _font(False, 18)
    for i, row in enumerate(rows):
        name, state, colors = row[0], row[1], row[2]
        indent = bool(row[3]) if len(row) > 3 else False
        cy = top + row_h * i + row_h / 2
        # 图标方块：开启时浅绿底绿字，关闭时浅灰底灰字；子项用小一号
        tile = 40 if not indent else 32
        tx = M + PAD + (34 if indent else 0)
        on = state in ("是", "伪人模式")
        bg = "#e9f8f0" if on else "#f1f3f7"
        if state == "伪人模式":
            bg = "#f3ecff"
        d.rounded_rectangle([tx - tile / 2, cy - tile / 2, tx + tile / 2, cy + tile / 2],
                            radius=12 if not indent else 9, fill=bg)
        # 取中文名的第一个字（"AI 对话"→"AI"）
        glyph = "AI" if name.startswith("AI") else name[:1]
        latin = glyph.isascii()
        fsz = (20 if latin else 19) if not indent else (15 if latin else 14)
        d.text((tx, cy), glyph, font=_font(True, fsz),
               fill=colors[0] if on else "#9aa6b5", anchor="mm")
        if indent:   # 子项：一条很淡的连接线，表明从属
            d.line([M + PAD + 6, cy - row_h / 2 + 6, M + PAD + 6, cy], fill="#e6ebf3", width=3)
        d.text((tx + tile / 2 + 16, cy), name,
               font=(font_sub if indent else font_name),
               fill="#5b6b7e" if indent else "#243244", anchor="lm")
        _pill(d, W - M - PAD, cy, state, colors[0], colors[1], _font(True, 15))
        if i < n - 1:
            d.line([M + PAD, cy + row_h / 2, W - M - PAD, cy + row_h / 2], fill="#f4f6fa", width=1)

    d.text((W / 2, H - M - 34), footer or "", font=_font(False, 15), fill="#8b97a6", anchor="mm")

    if out_path is None:
        out_dir = os.path.join(_BASE, "data", "status_img")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"status_{int(time.time() * 1000)}.png")
    img.save(out_path, "PNG")
    return out_path

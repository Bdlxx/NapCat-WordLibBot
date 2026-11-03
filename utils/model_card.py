# -*- coding: utf-8 -*-
"""模型列表卡片（PIL 直绘，和群状态卡片同一套视觉）。

只读展示：每行 = 显示名 + 调用名小字 + 右侧标签（当前 / 识图 / 已关闭）。
尺寸同样 750×1000 竖屏 4:3，四角透明。
"""
import os
import time

from PIL import Image, ImageDraw

import utils.status_card as _sc

W, H = _sc.W, _sc.H
PAD = _sc.PAD

_TAG_STYLE = {
    "当前": ("#15803d", "#e9f8f0"),
    "识图": ("#2563eb", "#eaf1ff"),
    "纯文本": ("#94a3b8", "#f2f4f8"),
    "已关闭": ("#b45309", "#fdf3e6"),
}


def _tag(d, right, cy, text):
    fg, bg = _TAG_STYLE.get(text, ("#64748b", "#f1f5f9"))
    f = _sc._font(True, 14)
    tw = d.textlength(text, font=f)
    w, h = tw + 22, 28
    x1 = right - w
    d.rounded_rectangle([x1, cy - h / 2, right, cy + h / 2], radius=h / 2, fill=bg)
    d.text(((x1 + right) / 2, cy), text, font=f, fill=fg, anchor="mm")
    return x1


def render_model_list(rows, subtitle="", footer=None, out_path=None):
    """rows: [{"name","model","tags":[...],"cur":bool,"on":bool}]"""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=28, fill="#ffffff",
                        outline="#e6ebf3", width=2)

    d.text((PAD, PAD + 6), "模型列表", font=_sc._font(True, 32), fill="#1b2432")
    d.text((PAD, PAD + 54), subtitle or "", font=_sc._font(False, 17), fill="#5d6b7c")
    d.line([PAD, PAD + 100, W - PAD, PAD + 100], fill="#eef1f6", width=2)

    top, bottom = PAD + 120, H - 92
    n = max(1, len(rows))
    row_h = min((bottom - top) / n, 98)
    f_name, f_sub = _sc._font(True, 22), _sc._font(False, 15)
    for i, r in enumerate(rows):
        cy = top + row_h * i + row_h / 2
        d.text((PAD, cy - 12), r.get("name") or "", font=f_name,
               fill="#243244" if r.get("on") else "#a8b3c1", anchor="lm")
        d.text((PAD, cy + 14), r.get("model") or "", font=f_sub, fill="#8b97a6", anchor="lm")
        x = W - PAD
        for tag in reversed(r.get("tags") or []):
            x = _tag(d, x, cy, tag) - 8
        if i < n - 1:
            d.line([PAD, cy + row_h / 2, W - PAD, cy + row_h / 2], fill="#f4f6fa", width=1)

    d.text((W / 2, H - 46), footer or "", font=_sc._font(False, 15), fill="#8b97a6", anchor="mm")

    if out_path is None:
        out_dir = os.path.join(_sc._BASE, "data", "status_img")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"models_{int(time.time() * 1000)}.png")
    img.save(out_path, "PNG")
    return out_path

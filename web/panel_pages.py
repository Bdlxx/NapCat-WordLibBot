"""两端共用的页面片段（Python 侧）

主本：/root/mybot2/web/panel_pages.py
副本：/root/astercore/src/astercore/web/panel_pages.py（必须字节一致）
一致性校验：/root/mybot2/tests/test_dual_end_assets.py

这里只放**两端结构必须完全相同**的页面与标记：
  · 插件配置页框架（控件由插件声明的 schema 驱动，见 config_schema.py / cfg_form.js）
  · 运行日志页（含工具栏、行数/级别/自动刷新、阅读不被打断的提示）
  · 通用小件：状态标签、卡片、空状态、错误状态
各端特有的页面（Linux 的仪表盘/群组矩阵、桌面端的账号/设置页）写在各端自己的 ui_pages.py 里。
"""

import html as _html
import time


# ---------------------------------------------------------------- 基础
def esc(v):
    """HTML 转义。所有插进模板的动态值都必须过这里。"""
    return _html.escape('' if v is None else str(v), quote=True)


def fmt_uptime(sec):
    try:
        sec = int(sec or 0)
    except (TypeError, ValueError):
        sec = 0
    if sec <= 0:
        return '-'
    d, h, m = sec // 86400, sec % 86400 // 3600, sec % 3600 // 60
    return (f'{d} 天 ' if d > 0 else '') + (f'{h} 小时 ' if h > 0 else '') + f'{m} 分钟'


def need_js_time(ts=None):
    return int(ts if ts is not None else time.time())


def status_tag(ok, on_text='运行中', off_text='已停止', unknown=None):
    """运行状态标签（两端同一套颜色语义）"""
    if ok is None and unknown is not None:
        return f'<span class="el-tag warning"><span class="status-dot yellow"></span> {esc(unknown)}</span>'
    cls = 'success' if ok else 'danger'
    dot = 'green' if ok else 'red'
    return f'<span class="el-tag {cls}"><span class="status-dot {dot}"></span> {esc(on_text if ok else off_text)}</span>'


def card(title, body, extra='', icon=''):
    return (f'<div class="card"><div class="card-header"><h3>{icon}{esc(title)}</h3>{extra}</div>'
            f'<div class="card-body">{body}</div></div>')


def empty_state(icon, title, hint='', retry_label=''):
    html = f'<div class="empty-state"><div class="icon">{icon}</div><p>{esc(title)}</p>'
    if hint:
        html += f'<div style="margin-top:8px;font-size:12px;color:var(--text-secondary)">{esc(hint)}</div>'
    if retry_label:
        html += f'<div style="margin-top:14px"><button class="btn btn-default" data-refresh="1">{esc(retry_label)}</button></div>'
    return html + '</div>'


def info_table(rows):
    """键值信息表（两端同一套）"""
    body = ''.join(f'<tr><td>{esc(k)}</td><td>{v if raw else esc(v)}</td></tr>'
                   for k, v, raw in [(r[0], r[1], len(r) > 2 and r[2]) for r in rows])
    return f'<table class="el-table"><tr><th width="150">项目</th><th>值</th></tr>{body}</table>'


# ---------------------------------------------------------------- 插件配置页
def config_page(ctx=None):
    """配置页只给**框架**：标题/来源徽标/表单容器/JSON 页签。

    控件的类型映射在前端共用 cfg_form.js，字段与当前值来自各端的 /schema 接口
    （插件自己声明的 __config_schema__）。两端这段标记逐字相同。
    """
    return """
      <div class="card">
        <div class="card-header" style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
          <h3 id="cfgTitle" style="margin:0">插件配置</h3>
          <span class="el-tag muted" id="cfgSrc" style="font-weight:400">载入中…</span>
          <span class="badge" id="cfgCount" style="margin-left:auto;font-size:11px;padding:2px 10px;border-radius:10px;background:var(--bg-active);color:var(--color-primary)"></span>
        </div>
        <div class="card-body">
          <div class="cf-tabs" style="margin-bottom:10px">
            <button class="btn btn-default mini" id="tab-form" data-cfg-tab="form">表单</button>
            <button class="btn btn-default mini" id="tab-json" data-cfg-tab="json">JSON 原文</button>
          </div>
          <div id="cfgSchemaErrors" style="display:none"></div>
          <div id="configForm" class="cf-form">载入中…</div>
          <textarea id="configJson" spellcheck="false" rows="18"
            style="width:100%;display:none;font-family:var(--font-mono);font-size:12px;padding:10px;
                   background:var(--bg-input);color:var(--text-primary);border:1px solid var(--border-color);
                   border-radius:var(--radius);outline:none"></textarea>
          <div id="cfgMsg" style="font-size:12px;color:var(--text-secondary);margin-top:10px"></div>
        </div>
      </div>"""


# ---------------------------------------------------------------- 日志页
def log_toolbar(sfx, lines, auto=True, with_filter=True):
    """日志工具栏（两端共用；sfx 区分同一端上的多个日志源）

    级别筛选只有带级别标注的日志需要（如项目日志）；容器原样日志不显示它。
    """
    opts = ''.join(f'<option value="{n}"{" selected" if n == lines else ""}>{n} 行</option>'
                   for n in (50, 100, 200, 500))
    filt = ('''<select id="logFilterSel" data-log-filter="1">
          <option value="info" selected>默认(仅信息)</option>
          <option value="debug">仅调试</option>
          <option value="all">全部级别</option>
          <option value="warn">仅警告</option>
          <option value="error">仅错误</option>
        </select>''' if with_filter else '')
    return f"""
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:12px">
        <select id="logLinesSel{sfx}" data-log-lines="1" data-sfx="{sfx}">{opts}</select>
        {filt}
        <label style="display:flex;align-items:center;gap:6px;font-size:13px;color:var(--text-regular);cursor:pointer">
          <input type="checkbox" id="logAutoRef{sfx}"{' checked' if auto else ''}
            data-log-auto="1" data-sfx="{sfx}"> 自动刷新(5s)
        </label>
        <button class="btn btn-default" data-log-act="refresh" data-sfx="{sfx}">🔄 刷新</button>
        <button class="btn btn-default" data-log-act="more" data-sfx="{sfx}">⬇ 再加载 200 行</button>
        <span class="log-hint" id="logScrollHint{sfx}" role="button" tabindex="0" style="display:none"
          data-log-act="scroll" data-sfx="{sfx}">已暂停自动滚动 · 回到最新</span>
      </div>"""


def logs_page(ctx, title='运行日志', subtitle='', napcat=False):
    """运行日志页（两端同一套；napcat=True 时用容器日志的查看器 id）"""
    sfx = '2' if napcat else ''
    viewer_id = 'napcatLogViewer' if napcat else 'logViewer'
    ctx = ctx or {}
    return (f'<div class="card"><div class="card-header"><h3>{esc(title)}</h3>'
            f'<span style="font-size:12px;color:var(--text-secondary)" id="logTotalInfo">{esc(subtitle)}</span></div>'
            f'<div class="card-body">'
            f'{log_toolbar(sfx, ctx.get("log_lines", 100), ctx.get("log_auto", True), with_filter=not napcat)}'
            f'<div class="log-viewer" id="{viewer_id}" style="max-height:calc(100vh - 260px)">加载中...</div>'
            f'</div></div>')

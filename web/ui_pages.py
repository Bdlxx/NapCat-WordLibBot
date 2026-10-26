"""面板页面片段（服务端渲染）

架构（2026-09-27 改版，用户要求）：
  - `web/panel/index.html` 只留**大框架**：布局、导航、样式、通用交互（Toast/弹窗/
    脏值保护/轮询/图标水合）。它是静态文件，浏览器直接缓存，首屏快。
  - **页面内容由后端生成**（本模块），经 `GET /api/bot/<n>/ui/page/<page>` 交给前端挂载。
    前端只负责"插进来 + 事件委托"，不再自己拼业务 HTML。

所以：改页面结构只改这一个 Python 文件；改交互逻辑才动 index.html。
"""

import html as _html
import json
import time

# 两端共用的页面/小件：配置页、日志页、状态标签、空状态（与 Windows 端同一份字节）
import panel_pages as pp
from panel_pages import esc, fmt_uptime, card, empty_state, status_tag

# ---------------------------------------------------------------- 基础工具

def napcat_text(nc):
    if not nc:
        return '检测中'
    if nc.get('online') is True:
        return '在线'
    if nc.get('online') is False:
        return '离线'
    return '未知' if nc.get('error') else '检测中'


def _napcat_tag_class(nc):
    if nc and nc.get('online') is True:
        return 'success'
    if nc and nc.get('online') is False:
        return 'danger'
    return 'warning'


def _napcat_dot_class(nc):
    if nc and nc.get('online') is True:
        return 'green'
    if nc and nc.get('online') is False:
        return 'red'
    return 'yellow'


def napcat_online_tag(nc):
    return (f'<span class="el-tag {_napcat_tag_class(nc)}">'
            f'<span class="status-dot {_napcat_dot_class(nc)}"></span> {napcat_text(nc)}</span>')


def napcat_restart_btn(nc, small=False):
    """账号不在线才给重启按钮（在线时重启=自找麻烦）"""
    if nc and nc.get('online') is True:
        return ''
    style = ' style="margin-top:8px;padding:4px 10px;font-size:12px"' if small else ''
    return f'<button class="btn btn-primary"{style} data-act="napcat-restart">🔄 重启 NapCat</button>'


def napcat_webui_btn(nc, small=False):
    """跳转 NapCat 自己的 WebUI（地址来自实例注册文件，未配置则不显示）"""
    if not nc or not nc.get('webui'):
        return ''
    style = ' style="margin-top:8px;padding:4px 10px;font-size:12px"' if small else ''
    return (f'<a class="btn btn-default"{style} href="{esc(nc["webui"])}" target="_blank" '
            f'rel="noopener">🖥 打开 NapCat 面板</a>')


def napcat_desc(nc, fallback_qq=''):
    login = (nc or {}).get('login') or {}
    if login.get('nickname'):
        return f'{esc(login["nickname"])} ({esc(login.get("user_id") or "")})'
    if (nc or {}).get('error'):
        return esc(nc['error'])
    return 'QQ ' + esc((nc or {}).get('qq') or fallback_qq or '')


# ---------------------------------------------------------------- 各页面

def _dashboard(ctx):
    info = ctx.get('info') or {}
    nc = ctx.get('napcat') or {}
    plugins = ctx.get('plugins') or []
    group_count = ctx.get('group_count', 0)
    running = bool(info.get('running'))

    if plugins:
        chips = ''.join(
            f'<div class="chip-btn" role="button" tabindex="0" data-open="config" data-key="{esc(p["key"])}">'
            f'<span style="font-size:16px">🧩</span>'
            f'<span style="font-size:13px;font-weight:500">{esc(p.get("name_cn") or p["key"])}</span>'
            f'<span style="font-size:11px;color:var(--text-secondary)">{esc(p.get("name_en") or "")}</span>'
            + ('' if p.get('declared') else '<span class="el-tag warning" title="该插件未声明配置项，字段按当前值推断">推断</span>')
            + '</div>' for p in plugins)
    else:
        chips = '<div style="padding:20px;color:var(--text-secondary);text-align:center">暂无插件</div>'

    return f"""
      <div class="stat-grid">
        <div class="stat-card"><div class="stat-icon blue">🤖</div><div class="stat-info">
          <div class="label">Bot 状态</div>
          <div class="value" id="dashBotVal">{'运行中' if running else '已停止'}</div>
          <div class="desc" id="dashBotDesc">{esc(info.get('name') or '')} · PID {esc(info.get('pid') or '-')}</div>
        </div></div>
        <div class="stat-card"><div class="stat-icon green">🐱</div><div class="stat-info">
          <div class="label">NapCat 账号</div>
          <div class="value" id="dashNapcatVal">{napcat_text(nc)}</div>
          <div class="desc" id="dashNapcatDesc">{napcat_desc(nc, info.get('qq'))}</div>
          <div id="dashNapcatAction">{napcat_restart_btn(nc, True)}{napcat_webui_btn(nc, True)}</div>
        </div></div>
        <div class="stat-card"><div class="stat-icon orange">🧩</div><div class="stat-info">
          <div class="label">已安装插件</div><div class="value">{len(plugins)} 个</div>
          <div class="desc">点击下方插件可直接配置</div>
        </div></div>
        <div class="stat-card"><div class="stat-icon purple">👥</div><div class="stat-info">
          <div class="label">关联群组</div><div class="value">{group_count} 个</div>
          <div class="desc"><a href="#" data-nav="groups" style="color:var(--color-primary)">管理群组开关 →</a></div>
        </div></div>
      </div>
      <div class="card"><div class="card-header"><h3>🧩 插件概览</h3>
        <span style="font-size:12px;color:var(--text-secondary)">点击进入对应插件配置</span></div>
        <div class="card-body"><div style="display:flex;flex-wrap:wrap;gap:10px;padding:4px 0">{chips}</div></div></div>
      <div class="card"><div class="card-header"><h3>🔍 系统信息</h3></div><div class="card-body">
        <table class="el-table"><tr><th width="130">项目</th><th>值</th></tr>
        <tr><td>机器人</td><td>{esc(info.get('name') or '')} (QQ:{esc(info.get('qq') or '-')})</td></tr>
        <tr><td>主人 QQ</td><td>{esc(info.get('master') or '-')}</td></tr>
        <tr><td>运行时长</td><td>{fmt_uptime(info.get('uptime'))} {('(PID ' + esc(info.get('pid')) + ')') if info.get('pid') else ''}</td></tr>
        <tr><td>运行目录</td><td>{esc(info.get('dir') or '-')}</td></tr>
        <tr><td>Screen</td><td>{esc(info.get('screen') or '-')}</td></tr>
        <tr><td>NapCat 账号</td><td>{napcat_text(nc)}{(' · ' + esc((nc.get('login') or {}).get('nickname'))) if (nc.get('login') or {}).get('nickname') else ''}{(' · ' + esc(nc.get('error'))) if nc.get('error') else ''}</td></tr>
        </table></div></div>"""


def _manage(ctx):
    info = ctx.get('info') or {}
    nc = ctx.get('napcat') or {}
    running = bool(info.get('running'))
    return f"""
      <div class="card"><div class="card-header"><h3>🤖 Bot 管理</h3></div><div class="card-body">
        <div style="margin-bottom:12px;display:flex;align-items:center;gap:12px;flex-wrap:wrap" id="botStatusArea">
          {bot_status_html(info)}
        </div>
        <div style="display:flex;gap:10px;flex-wrap:wrap">
          <button class="btn btn-primary" data-act="start">▶ 启动</button>
          <button class="btn btn-default" data-act="stop">⏹ 停止</button>
          <button class="btn btn-default" data-act="restart">🔄 重启</button>
        </div>
      </div></div>
      <div class="card"><div class="card-header"><h3>🐱 NapCat 账号</h3></div><div class="card-body">
        <div style="margin-bottom:12px;display:flex;align-items:center;gap:12px;flex-wrap:wrap" id="napcatStatusArea">
          {napcat_status_html(nc, info)}
        </div>
        <div style="display:flex;gap:10px;flex-wrap:wrap">
          <button class="btn btn-primary" data-act="qr">📱 查看二维码</button>
          <span id="napcatActionArea">{napcat_restart_btn(nc)}{napcat_webui_btn(nc)}</span>
        </div>
        <div id="qrArea" style="display:none;margin-top:14px;border-top:1px solid var(--border-light);padding-top:12px;text-align:center">
          <div style="font-size:13px;font-weight:600;margin-bottom:8px">📱 二维码</div>
          <div id="qrContainer">加载中...</div>
        </div>
      </div></div>"""


def bot_status_html(info):
    """Bot 状态区（整页与轮询共用同一份标记）"""
    info = info or {}
    running = bool(info.get('running'))
    return (f'<span class="el-tag {"success" if running else "danger"}">'
            f'<span class="status-dot {"green" if running else "red"}"></span> {"运行中" if running else "已停止"}</span>'
            f'<span style="font-size:13px;font-weight:600">{esc(info.get("name") or "")}</span>'
            f'<span style="font-size:12px;color:var(--text-secondary)">PID: {esc(info.get("pid") or "-")}'
            f' · 运行时长: {fmt_uptime(info.get("uptime"))}</span>')


def napcat_status_html(nc, info=None):
    info = info or {}
    login = (nc or {}).get('login') or {}
    name = login.get('nickname') or (nc or {}).get('name') or info.get('name') or ''
    qq = login.get('user_id') or (nc or {}).get('qq') or info.get('qq') or ''
    err = (nc or {}).get('error') or ''
    return (napcat_online_tag(nc)
            + f'<span style="font-size:13px;font-weight:600">{esc(name)}</span>'
            + f'<span style="font-size:12px;color:var(--text-secondary)">QQ {esc(qq)}'
            + (f' · {esc(err)}' if err else '') + '</span>')


def _groups(ctx):
    tg = ctx.get('toggles') or {}
    groups = tg.get('groups') or []
    plugins = tg.get('plugins') or []
    toggles = tg.get('toggles') or {}
    meta = tg.get('_pluginMeta') or {}
    group_info = tg.get('groupInfo') or {}

    if not groups:
        return ('<div class="empty-state"><div class="icon">🔀</div><p>还没有可管理的群</p>'
                '<div style="margin-top:8px;font-size:12px;color:var(--text-secondary)">'
                '群列表来自 NapCat 账号，需要账号在线才能读取。可先到「运行管理」确认账号状态。</div>'
                '<div style="margin-top:14px"><button class="btn btn-default" data-refresh="1">'
                '🔄 重新获取群列表</button></div></div>')

    def pname(p):
        m = meta.get(p) or {}
        return m.get('name_cn') or p

    # 开关文件里记着、但本账号当前不在的群（另一个账号的群/已退出的群）——单独标出来，
    # 否则"开关绑了一堆自己不认识的群"会被当成绑定错误（2026-10-25 线上就踩了这次）
    missing = [g for g in groups if group_info and g not in group_info] if group_info else []
    head = ['<div class="card"><div class="card-header"><h3>👥 分群插件开关</h3>',
            f'<span class="badge" style="font-size:11px;padding:2px 10px;border-radius:10px;'
            f'background:var(--bg-active);color:var(--color-primary)">{len(groups)} 个群</span>',
            (f'<span class="el-tag warning" style="margin-left:8px" title="开关存着，但该账号当前不在这些群里，'
             f'开关不会生效">{len(missing)} 个群本账号未加入</span>') if missing else '',
            '</div>',
            '<div class="card-body"><div class="table-wrapper"><table class="el-table" style="min-width:600px">',
            '<thead><tr><th class="sticky-col">群号</th>']
    for p in plugins:
        m = meta.get(p) or {}
        head.append(f'<th style="text-align:center;min-width:90px">{esc(m.get("name_cn") or p)}<br>'
                    f'<span style="font-weight:400;font-size:11px;color:var(--text-secondary)">'
                    f'{esc(m.get("name_en") or p)}</span></th>')
    head.append('<th style="text-align:center;min-width:70px">全选</th></tr></thead><tbody>')

    # 全选行（每列 = 该插件在所有群的状态）
    head.append('<tr style="background:var(--bg-active)"><td class="sticky-col is-active" style="font-weight:600">全选</td>')
    for p in plugins:
        all_on = all(bool((toggles.get(g) or {}).get(p)) for g in groups)
        head.append(f'<td style="text-align:center"><label class="el-switch">'
                    f'<input type="checkbox" {"checked" if all_on else ""} class="tg-ac" data-tgp="{esc(p)}" '
                    f'aria-label="在所有群开启「{esc(pname(p))}」"><span class="track"></span></label></td>')
    head.append('<td style="text-align:center"><label class="el-switch">'
                '<input type="checkbox" data-tg-all="1" aria-label="全部群全部插件全选">'
                '<span class="track"></span></label></td></tr>')

    for g in groups:
        gi = group_info.get(g) or {}
        gname = gi.get('name') or g
        avatar = gi.get('avatar') or ''
        row_all = all(bool((toggles.get(g) or {}).get(p)) for p in plugins)
        head.append('<tr><td class="sticky-col"><div class="group-cell"><div class="g-avatar">')
        if avatar:
            head.append(f'<img src="{esc(avatar)}" alt="" onerror="this.style.display=\'none\';'
                        f'this.parentElement.textContent=\'👥\'">')
        else:
            head.append('👥')
        name_html = esc(gname)
        if g in missing:
            name_html += (' <span class="el-tag warning" style="font-size:10px;padding:1px 6px" '
                          'title="该账号当前不在此群：开关存着但不会生效">未加入</span>')
        head.append(f'</div><div class="g-info"><div class="g-name">{name_html}</div>'
                    f'<div class="g-id">{esc(g)}</div></div></div></td>')
        for p in plugins:
            on = bool((toggles.get(g) or {}).get(p))
            head.append(f'<td style="text-align:center"><label class="el-switch">'
                        f'<input type="checkbox" {"checked" if on else ""} class="tg-c" data-tgg="{esc(g)}" '
                        f'data-tgp="{esc(p)}" aria-label="{esc(gname)} 的「{esc(pname(p))}」">'
                        f'<span class="track"></span></label></td>')
        head.append(f'<td style="text-align:center"><label class="el-switch">'
                    f'<input type="checkbox" {"checked" if row_all else ""} class="tg-r" data-tgg="{esc(g)}" '
                    f'aria-label="在 {esc(gname)} 开启所有插件"><span class="track"></span></label></td></tr>')
    head.append('</tbody></table></div></div></div>')

    head.append('<div class="card"><div class="card-header"><h3>💡 说明</h3></div>'
                '<div class="card-body" style="font-size:13px;color:var(--text-secondary);line-height:1.8">'
                '所有插件在每个群默认关闭。<br>在群内发送对应命令开启：<code>开启词库</code> / <code>关闭词库</code><br>'
                '私聊发送 = 全局控制。横向「全选」列控制单个插件在所有群的状态，'
                '纵向「全选」行控制单个群的所有插件。</div></div>')
    # 群组状态交给前端做交互（innerHTML 插入的 <script> 不会执行，所以用 JSON 数据块）
    state = {g: {p: bool((toggles.get(g) or {}).get(p)) for p in plugins} for g in groups}
    head.append('<script type="application/json" id="groupsState">'
                + json.dumps(state, ensure_ascii=False).replace('</', '<\\/') + '</script>')
    return ''.join(head)


def _unused_removed():
    pass


PAGES = {
    'dashboard': (_dashboard, '仪表盘', []),
    'manage': (_manage, '运行管理', []),
    'groups': (_groups, '群组开关', ['save']),
    'config': (pp.config_page, '插件配置', ['save', 'save_restart']),
    'logs': (lambda ctx: pp.logs_page(ctx, '运行日志', 'runtime.log'), '运行日志', []),
    'napcat_logs': (lambda ctx: pp.logs_page(ctx, 'NapCat 容器日志', '', napcat=True), 'NapCat 日志', []),
}

ACTION_TITLES = {
    'groups': lambda ctx: f'群组开关（{len((ctx.get("toggles") or {}).get("groups") or [])} 个群 × '
                          f'{len((ctx.get("toggles") or {}).get("plugins") or [])} 个插件）',
    'config': lambda ctx: f'正在配置：{ctx.get("plugin_name") or ctx.get("plugin_key") or ""}',
}


def render_page(page, ctx):
    """渲染一个页面的片段。返回给 /api/bot/<n>/ui/page/<page> 的 data 部分。"""
    h = ctx.get('_html')
    fn, title, actions = PAGES.get(page, PAGES['dashboard'])
    title = ctx.get('title_override') or title
    at = ACTION_TITLES.get(page)
    return {
        'page': page,
        'crumb': title,
        'html': fn(ctx),
        'actions': actions,
        'action_title': at(ctx) if at else (title if actions else ''),
        'generated_at': int(time.time()),
    }

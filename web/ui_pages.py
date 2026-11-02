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
    """群聊管理 = 群卡片列表（点卡片进该群详情页）"""
    tg = ctx.get('toggles') or {}
    groups = tg.get('groups') or []
    plugins = tg.get('plugins') or []
    toggles = tg.get('toggles') or {}
    meta = tg.get('_pluginMeta') or {}
    group_info = tg.get('groupInfo') or {}
    chat_modes = tg.get('chatModes') or {}

    if not groups:
        return ('<div class="empty-state"><div class="icon">🔀</div><p>还没有可管理的群</p>'
                '<div style="margin-top:8px;font-size:12px;color:var(--text-secondary)">'
                '群列表来自 NapCat 账号，需要账号在线才能读取。可先到「运行管理」确认账号状态。</div>'
                '<div style="margin-top:14px"><button class="btn btn-default" data-refresh="1">'
                '🔄 重新获取群列表</button></div></div>')

    missing = [g for g in groups if group_info and g not in group_info] if group_info else []
    out = ['<div class="card"><div class="card-header"><h3>👥 群聊管理</h3>',
           f'<span class="badge" style="font-size:11px;padding:2px 10px;border-radius:10px;'
           f'background:var(--bg-active);color:var(--color-primary)">{len(groups)} 个群</span>',
           (f'<span class="el-tag warning" style="margin-left:8px" title="开关存着，但该账号当前不在这些群里，'
            f'开关不会生效">{len(missing)} 个群本账号未加入</span>') if missing else '',
           '</div><div class="card-body">',
           '<div style="font-size:12px;color:var(--text-secondary);margin-bottom:12px">'
           '点任意一个群 → 进入该群的开关设置（改动即时生效，不用点保存）。</div>',
           '<div class="group-grid">']

    for g in groups:
        gi = group_info.get(g) or {}
        gname = gi.get('name') or g
        avatar = gi.get('avatar') or ''
        on_cnt = sum(1 for p in plugins if (toggles.get(g) or {}).get(p))
        cm = (chat_modes.get(g) or {}).get('mode') or 'normal'
        pseudo_on = bool((toggles.get(g) or {}).get('pseudo'))
        mode_txt = ('伪人' if cm == 'pseudo' else '普通') if pseudo_on else 'AI 未开'
        avatar_html = (f'<img class="group-card-avatar" src="{esc(avatar)}" alt="" loading="lazy" '
                       f'onerror="this.style.display=\'none\'">') if avatar else \
                      '<div class="group-card-avatar" style="display:flex;align-items:center;' \
                      'justify-content:center;font-size:20px">👥</div>'
        name_html = esc(gname)
        if g in missing:
            name_html += (' <span class="el-tag warning" style="font-size:10px;padding:1px 6px" '
                          'title="该账号当前不在此群：开关存着但不会生效">未加入</span>')
        out.append(
            f'<div class="group-card" data-open="group" data-key="{esc(g)}" role="button" tabindex="0" '
            f'aria-label="进入 {esc(gname)} 的开关设置">'
            f'{avatar_html}'
            f'<div class="group-card-main">'
            f'<div class="group-card-name" title="{esc(gname)}">{name_html}</div>'
            f'<div class="group-card-meta">{esc(g)} · 已开 {on_cnt}/{len(plugins)} · {mode_txt}</div>'
            f'</div><div class="group-card-arrow">›</div></div>')

    out.append('</div></div></div>')
    out.append('<div class="card"><div class="card-header"><h3>💡 说明</h3></div>'
               '<div class="card-body" style="font-size:13px;color:var(--text-secondary);line-height:1.8">'
               '所有插件在每个群默认关闭；也可以在群里直接发命令：<code>开启词库</code> / <code>关闭词库</code>。'
               '<br>「AI 对话模式」按群设置：先在本群开启「AI 对话」，模式开关才可用；'
               '关 = 普通（只认 @ 与唤醒词），开 = 伪人（额外会主动接话）。</div></div>')
    return ''.join(out)


def _group_detail(ctx):
    """单个群的开关详情（从群卡片点进来）"""
    gid = str(ctx.get('group_id') or '')
    tg = ctx.get('toggles') or {}
    groups = tg.get('groups') or []
    plugins = tg.get('plugins') or []
    meta = tg.get('_pluginMeta') or {}
    toggles = (tg.get('toggles') or {}).get(gid) or {}
    gi = ctx.get('group_info') or {}
    gname = gi.get('name') or gid or '未知群'
    avatar = gi.get('avatar') or ''
    cm = (tg.get('chatModes') or {}).get(gid) or {}
    cm_mode = cm.get('mode') or 'normal'
    cm_explicit = bool(cm.get('explicit'))
    pseudo_on = bool(toggles.get('pseudo'))
    in_groups = gid in groups if groups else True

    if not gid:
        return ('<div class="empty-state"><div class="icon">⚠️</div><p>没有指定群号</p>'
                '<div style="margin-top:14px"><button class="btn btn-default" data-page="groups">'
                '‹ 返回群列表</button></div></div>')

    avatar_html = (f'<img class="group-card-avatar" src="{esc(avatar)}" alt="" onerror="this.style.display=\'none\'">'
                   if avatar else '<div class="group-card-avatar" style="display:flex;align-items:center;'
                   'justify-content:center;font-size:20px">👥</div>')
    out = ['<div style="margin-bottom:12px"><button class="btn btn-default" data-page="groups">'
           '‹ 返回群列表</button></div>',
           '<div class="card"><div class="card-header" style="gap:12px">',
           avatar_html,
           f'<div style="min-width:0;flex:1"><div class="group-card-name" style="font-size:17px">{esc(gname)}</div>'
           f'<div class="group-card-meta">{esc(gid)}'
           + ('' if in_groups else ' · <span class="el-tag warning" style="font-size:10px;padding:1px 6px">本账号未加入</span>')
           + '</div></div>',
           '<div style="display:flex;gap:8px">',
           '<button class="btn btn-default btn-sm" data-tg-group-all="1">全部开启</button>',
           '<button class="btn btn-default btn-sm" data-tg-group-all="0">全部关闭</button>',
           '</div></div>',
           '<div class="card-body">']

    # 插件开关行（按"常用优先"排序：词库 → AI 对话（含伪人模式子行）→ 视频解析 → 结婚 → JM → 其它）
    _order = ["wordlib", "pseudo", "video_parser", "marry", "jm_downloader"]
    plugins = [p for p in _order if p in plugins] + [p for p in plugins if p not in _order]
    for p in plugins:
        m = meta.get(p) or {}
        label = m.get('name_cn') or p
        en = m.get('name_en') or p
        on = bool(toggles.get(p))
        extra = ''
        if p == 'pseudo':
            extra = (' <span class="el-tag" style="font-size:10px;padding:1px 6px;margin-left:6px">'
                     f'模式：{"伪人" if cm_mode == "pseudo" else "普通"}{"" if cm_explicit else "（默认）"}</span>')
        out.append(
            '<div class="gd-row">'
            f'<div style="min-width:0;flex:1"><div class="gd-name" title="{esc(en)}">{esc(label)}</div>'
            f'<div class="gd-desc">{esc((m.get("description") or "").strip())[:80]}</div></div>'
            f'<label class="el-switch"><input type="checkbox" class="tg-c" data-tgg="{esc(gid)}" '
            f'data-tgp="{esc(p)}" {"checked" if on else ""} aria-label="本群「{esc(label)}」">'
            '<span class="track"></span></label>'
            '</div>')
        if p == 'pseudo':
            # 「AI 对话」只管插件开关；模式是它下面的子开关：开=伪人，关=普通
            out.append(
                '<div class="gd-row gd-sub">'
                '<div style="min-width:0;flex:1"><div class="gd-name">伪人模式'
                '<span class="gd-en">开启后会自动接话；关闭则只回应 @ 和唤醒词</span></div>'
                + ('' if pseudo_on else '<div class="gd-desc">先开启上面的「AI 对话」，这个开关才可用</div>')
                + '</div>'
                f'<label class="el-switch"><input type="checkbox" class="tg-mode" data-tgg="{esc(gid)}" '
                f'{"checked" if cm_mode == "pseudo" else ""} {"disabled" if not pseudo_on else ""} '
                f'aria-label="本群伪人模式"><span class="track"></span></label>'
                '</div>')

    out.append('</div></div>')
    state = {gid: {p: bool(toggles.get(p)) for p in plugins}}
    out.append('<script type="application/json" id="groupsState">'
               + json.dumps(state, ensure_ascii=False).replace('</', '<\\/') + '</script>')
    out.append('<script type="application/json" id="groupsModes">'
               + json.dumps({gid: cm_mode}, ensure_ascii=False).replace('</', '<\\/') + '</script>')
    return ''.join(out)


def _unused_removed():
    pass


def _settings(ctx):
    """设置页：主人 QQ + 管理员 QQ（都在实例 config.json，管理员全插件通用）

    值来自 `_page_ctx` 注入的 master_qq / admins / settings_meta；
    保存走 `POST /api/bot/<n>/settings`（见 api.py），按钮在底部操作栏。
    """
    master = ctx.get('master_qq') or []
    admins = ctx.get('admins') or []
    meta = ctx.get('settings_meta') or {}
    has_wl = bool(meta.get('has_wordlib_plugin'))
    legacy = bool(meta.get('admins_legacy'))
    bot = f"{esc(meta.get('bot_name') or '')}（{esc(meta.get('bot_qq') or '-')}）"
    admin_hint = ('<b>全插件通用</b>：除下面两条「特别重要」的指令外，管理员与主人同权'
                  '（各插件的开启/关闭、参数设置、词条管理、模型切换等都可以用）。<br>'
                  '🔒 仍为主人专属：<code>jm更新</code>（会安装依赖包）、'
                  '<code>B站登录</code>（会替换机器人账号的登录凭证）。')
    if legacy:
        admin_hint += '<br>⚠️ 这个实例以前只在词库插件里配过管理员，保存后会统一迁到全局 ADMIN_QQ。'

    style = ('width:100%;box-sizing:border-box;min-height:96px;resize:vertical;'
             'font-family:var(--font-mono,Consolas,monospace)')
    return f"""
      <div class="card"><div class="card-header"><h3>👑 主人 QQ</h3>
        <span style="font-size:12px;color:var(--text-secondary)">所有插件都认，权限最高</span></div>
        <div class="card-body">
          <textarea id="setMasterQQ" rows="4" spellcheck="false" placeholder="一行一个 QQ 号"
            style="{style}">{esc(chr(10).join(master))}</textarea>
          <p class="cf-help" style="margin:10px 0 0">一行一个（也可用逗号分隔），<b>至少填一个</b>。
            写入实例 <code>config.json</code> 的 <code>MASTER_QQ</code>；保存后立即生效
            （各插件每次判断都重新读取，不用重启）。</p>
        </div></div>
      <div class="card" style="margin-top:16px"><div class="card-header"><h3>🛡️ 管理员 QQ（全插件通用）</h3>
        <span style="font-size:12px;color:var(--text-secondary)">除主人专属指令外与主人同权</span></div>
        <div class="card-body">
          <p class="cf-help" style="margin:0 0 10px">{admin_hint}</p>
          <textarea id="setAdmins" rows="4" spellcheck="false" placeholder="一行一个 QQ 号"
            style="{style}">{esc(chr(10).join(admins))}</textarea>
          <p class="cf-help" style="margin:10px 0 0">写入实例 <code>config.json</code> 的
            <code>ADMIN_QQ</code>（并同步旧版词库 <code>admins</code>）；保存后通知 bot 立即重载配置。</p>
        </div></div>
      <div class="card" style="margin-top:16px"><div class="card-header"><h3>ℹ️ 当前生效</h3></div>
        <div class="card-body">
          <table class="el-table"><tr><th width="140">项目</th><th>值</th></tr>
            <tr><td>机器人</td><td>{bot}</td></tr>
            <tr><td>主人 QQ</td><td>{esc('、'.join(master) or '（未设置）')}</td></tr>
            <tr><td>管理员 QQ</td><td>{esc('、'.join(admins) or '（未设置）')}</td></tr>
            <tr><td>词库插件</td><td>{'已安装' if has_wl else '未安装'}</td></tr>
          </table>
        </div></div>
"""


PAGES = {
    'dashboard': (_dashboard, '仪表盘', []),
    'manage': (_manage, '运行管理', []),
    'groups': (_groups, '群聊管理', []),
    'group': (_group_detail, '群聊详情', []),
    'config': (pp.config_page, '插件配置', ['save', 'save_restart']),
    'logs': (lambda ctx: pp.logs_page(ctx, '运行日志', 'runtime.log'), '运行日志', []),
    'napcat_logs': (lambda ctx: pp.logs_page(ctx, 'NapCat 容器日志', '', napcat=True), 'NapCat 日志', []),
    'settings': (_settings, '设置', ['save']),
}

ACTION_TITLES = {
    'groups': lambda ctx: f'群组开关（{len((ctx.get("toggles") or {}).get("groups") or [])} 个群 × '
                          f'{len((ctx.get("toggles") or {}).get("plugins") or [])} 个插件）',
    'config': lambda ctx: f'正在配置：{ctx.get("plugin_name") or ctx.get("plugin_key") or ""}',
    'settings': lambda ctx: f'设置：{ctx.get("bot", {}).get("name") or ""}'
                            f'（QQ {ctx.get("bot", {}).get("qq") or "-"}）',
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

/* ==========================================================================
   面板外壳（**两端共用同一份**：Linux 机器人面板 / Windows 桌面面板）
   主本：/root/mybot2/web/panel/panel.js
   副本：/root/astercore/src/astercore/web/static/panel.js（必须字节一致）
   一致性校验：/root/mybot2/tests/test_dual_end_assets.py

   分工（这是"双端界面相同"的实现方式）：
     · 本文件 = 布局骨架 + 全部通用交互（导航/页面挂载/动作栏/脏值保护/弹窗/
       轮询/日志查看/群组矩阵/键盘可达/图标水合/主题/移动端抽屉）
     · 每个端在 index.html 里注入：
         PANEL.endpoints  —— 各接口地址怎么拼（两端 API 路径不同）
         PANEL.nav        —— 显示哪些页面（Linux 有 NapCat 日志，桌面端没有）
         PANEL.beforeStart—— 桌面端要先装 Transport + fetch 垫片
         PANEL.hooks      —— 少数端特有行为（二维码、重启 NapCat、额外按钮）
     · 页面内容一律来自后端片段（各端 ui_pages.py），前端不拼业务 HTML
   ========================================================================== */
(function (global) {
'use strict';

/* ---------------------------------------------------------------- 状态 */
const P = {
  page: 'dashboard',          // 当前页
  key: null,                  // 当前"对象"（Linux: 插件 key；桌面端: 插件 key，账号另算）
  endpoints: {},              // 各端注入
  nav: [],                    // [{id,label,icon,group,sub}]
  hooks: {},
  icons: {},
  dirty: {},                  // 插件表单脏值
  dirtyGroups: false,
  plugins: {},
  schema: null,
  tab: 'form',
  logs: {},                   // {'': {lines,auto,raw}, '2': {...}}
  filter: 'info',
  timer: null, pollFn: null, pollMs: 10000,
  booted: false
};
global.PANEL = P;

/* 界面骨架与图标：由 panel.js 统一注入，保证两端结构逐字相同 */
const ICON_SPRITE = "<svg xmlns=\"http://www.w3.org/2000/svg\" style=\"display:none\" aria-hidden=\"true\" focusable=\"false\">\n<symbol id=\"i-bot\" viewBox=\"0 0 24 24\"><path d=\"M12 8V4H8\"/><rect width=\"16\" height=\"12\" x=\"4\" y=\"8\" rx=\"2\"/><path d=\"M2 14h2\"/><path d=\"M20 14h2\"/><path d=\"M15 13v2\"/><path d=\"M9 13v2\"/></symbol>\n<symbol id=\"i-paw\" viewBox=\"0 0 24 24\"><circle cx=\"11\" cy=\"4\" r=\"2\"/><circle cx=\"18\" cy=\"8\" r=\"2\"/><circle cx=\"20\" cy=\"16\" r=\"2\"/><path d=\"M9 10a5 5 0 0 1 5 5v3.5a3.5 3.5 0 0 1-6.84 1.04Q6.52 17.48 4.46 16.84A3.5 3.5 0 0 1 5.5 10Z\"/></symbol>\n<symbol id=\"i-puzzle\" viewBox=\"0 0 24 24\"><path d=\"M19.4 7.9a1.1 1.1 0 0 0 .3.8l1.6 1.6a2.4 2.4 0 0 1 0 3.4l-1.6 1.6a1 1 0 0 1-.9.3c-.4-.1-.8-.5-.9-.9a2.5 2.5 0 1 0-3.2 3.2c.4.1.8.5.9.9a1 1 0 0 1-.3.9l-1.6 1.6a2.4 2.4 0 0 1-3.4 0l-1.6-1.6a1 1 0 0 0-.9-.3c-.5.1-.8.5-1 1a2.5 2.5 0 1 1-3.2-3.3c.4-.2.9-.5 1-1a1 1 0 0 0-.4-.9L2.7 13.7a2.4 2.4 0 0 1 0-3.4l1.5-1.5a1 1 0 0 1 .9-.3c.5.1.9.5 1 1a2.5 2.5 0 1 0 3.3-3.2c-.5-.2-.9-.6-1-1.1a1 1 0 0 1 .3-.9l1.5-1.5a2.4 2.4 0 0 1 3.4 0l1.6 1.6a1 1 0 0 0 .9.3c.5-.1.8-.5 1-1a2.5 2.5 0 1 1 3.3 3.2c-.5.2-.9.6-1 1.1Z\"/></symbol>\n<symbol id=\"i-users\" viewBox=\"0 0 24 24\"><path d=\"M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2\"/><circle cx=\"9\" cy=\"7\" r=\"4\"/><path d=\"M22 21v-2a4 4 0 0 0-3-3.87\"/><path d=\"M16 3.13a4 4 0 0 1 0 7.75\"/></symbol>\n<symbol id=\"i-chart\" viewBox=\"0 0 24 24\"><path d=\"M3 3v16a2 2 0 0 0 2 2h16\"/><path d=\"M7 16v-4\"/><path d=\"M12 16V8\"/><path d=\"M17 16v-7\"/></symbol>\n<symbol id=\"i-search\" viewBox=\"0 0 24 24\"><circle cx=\"11\" cy=\"11\" r=\"8\"/><path d=\"m21 21-4.3-4.3\"/></symbol>\n<symbol id=\"i-qr\" viewBox=\"0 0 24 24\"><rect width=\"14\" height=\"20\" x=\"5\" y=\"2\" rx=\"2\"/><path d=\"M12 18h.01\"/></symbol>\n<symbol id=\"i-refresh\" viewBox=\"0 0 24 24\"><path d=\"M21 12a9 9 0 1 1-2.64-6.36\"/><path d=\"M21 3v6h-6\"/></symbol>\n<symbol id=\"i-play\" viewBox=\"0 0 24 24\"><path d=\"m6 3 14 9-14 9V3z\"/></symbol>\n<symbol id=\"i-stop\" viewBox=\"0 0 24 24\"><rect width=\"14\" height=\"14\" x=\"5\" y=\"5\" rx=\"2\"/></symbol>\n<symbol id=\"i-monitor\" viewBox=\"0 0 24 24\"><rect width=\"20\" height=\"14\" x=\"2\" y=\"3\" rx=\"2\"/><path d=\"M8 21h8\"/><path d=\"M12 17v4\"/></symbol>\n<symbol id=\"i-external\" viewBox=\"0 0 24 24\"><path d=\"M15 3h6v6\"/><path d=\"M10 14 21 3\"/><path d=\"M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6\"/></symbol>\n<symbol id=\"i-moon\" viewBox=\"0 0 24 24\"><path d=\"M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z\"/></symbol>\n<symbol id=\"i-sun\" viewBox=\"0 0 24 24\"><circle cx=\"12\" cy=\"12\" r=\"4\"/><path d=\"M12 2v2\"/><path d=\"M12 20v2\"/><path d=\"m4.9 4.9 1.4 1.4\"/><path d=\"m17.7 17.7 1.4 1.4\"/><path d=\"M2 12h2\"/><path d=\"M20 12h2\"/><path d=\"m6.3 17.7-1.4 1.4\"/><path d=\"m19.1 4.9-1.4 1.4\"/></symbol>\n<symbol id=\"i-settings\" viewBox=\"0 0 24 24\"><path d=\"M4 21v-7\"/><path d=\"M4 10V3\"/><path d=\"M12 21v-9\"/><path d=\"M12 8V3\"/><path d=\"M20 21v-5\"/><path d=\"M20 12V3\"/><path d=\"M1 14h6\"/><path d=\"M9 8h6\"/><path d=\"M17 16h6\"/></symbol>\n<symbol id=\"i-folder\" viewBox=\"0 0 24 24\"><path d=\"M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.7-.9l-.8-1.2A2 2 0 0 0 7.9 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z\"/></symbol>\n<symbol id=\"i-file\" viewBox=\"0 0 24 24\"><path d=\"M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z\"/><path d=\"M14 2v4a2 2 0 0 0 2 2h4\"/></symbol>\n<symbol id=\"i-flask\" viewBox=\"0 0 24 24\"><path d=\"M10 2v7.3\"/><path d=\"M14 9.3V2\"/><path d=\"M8.5 2h7\"/><path d=\"M14 9.3a6.5 6.5 0 1 1-4 0\"/></symbol>\n<symbol id=\"i-chat\" viewBox=\"0 0 24 24\"><path d=\"M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z\"/></symbol>\n<symbol id=\"i-rocket\" viewBox=\"0 0 24 24\"><path d=\"M4.5 16.5c-1.5 1.3-2 5-2 5s3.7-.5 5-2c.7-.8.7-2.1-.1-2.9a2.2 2.2 0 0 0-2.9 0z\"/><path d=\"m12 15-3-3a22 22 0 0 1 2-3.9A12.9 12.9 0 0 1 22 2c0 2.7-.8 7.5-6 11a22 22 0 0 1-4 2z\"/><path d=\"M9 12H4s.6-3 2-4c1.6-1.1 5 0 5 0\"/><path d=\"M12 15v5s3-.6 4-2c1.1-1.6 0-5 0-5\"/></symbol>\n<symbol id=\"i-warn\" viewBox=\"0 0 24 24\"><path d=\"m21.7 18-8-14a2 2 0 0 0-3.5 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3Z\"/><path d=\"M12 9v4\"/><path d=\"M12 17h.01\"/></symbol>\n<symbol id=\"i-check\" viewBox=\"0 0 24 24\"><path d=\"M20 6 9 17l-5-5\"/></symbol>\n<symbol id=\"i-x\" viewBox=\"0 0 24 24\"><path d=\"M18 6 6 18\"/><path d=\"m6 6 12 12\"/></symbol>\n<symbol id=\"i-lock\" viewBox=\"0 0 24 24\"><rect width=\"18\" height=\"11\" x=\"3\" y=\"11\" rx=\"2\"/><path d=\"M7 11V7a5 5 0 0 1 10 0v4\"/></symbol>\n<symbol id=\"i-user\" viewBox=\"0 0 24 24\"><path d=\"M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2\"/><circle cx=\"12\" cy=\"7\" r=\"4\"/></symbol>\n<symbol id=\"i-clock\" viewBox=\"0 0 24 24\"><circle cx=\"12\" cy=\"12\" r=\"10\"/><path d=\"M12 6v6l4 2\"/></symbol>\n<symbol id=\"i-trend\" viewBox=\"0 0 24 24\"><path d=\"M16 7h6v6\"/><path d=\"m22 7-8.5 8.5-5-5L2 17\"/></symbol>\n<symbol id=\"i-clipboard\" viewBox=\"0 0 24 24\"><rect width=\"8\" height=\"4\" x=\"8\" y=\"2\" rx=\"1\"/><path d=\"M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2\"/></symbol>\n<symbol id=\"i-menu\" viewBox=\"0 0 24 24\"><path d=\"M4 6h16\"/><path d=\"M4 12h16\"/><path d=\"M4 18h16\"/></symbol>\n<symbol id=\"i-logout\" viewBox=\"0 0 24 24\"><path d=\"M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4\"/><path d=\"m16 17 5-5-5-5\"/><path d=\"M21 12H9\"/></symbol>\n<symbol id=\"i-shuffle\" viewBox=\"0 0 24 24\"><path d=\"M2 18h1.4c1.3 0 2.5-.6 3.3-1.7l6.1-8.6c.8-1.1 2-1.7 3.3-1.7H22\"/><path d=\"m18 2 4 4-4 4\"/><path d=\"M2 6h1.9c1.5 0 2.9.9 3.6 2.2\"/><path d=\"M22 18h-5.9c-1.3 0-2.6-.7-3.3-1.8l-.5-.8\"/><path d=\"m18 14 4 4-4 4\"/></symbol>\n<symbol id=\"i-bulb\" viewBox=\"0 0 24 24\"><path d=\"M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5\"/><path d=\"M9 18h6\"/><path d=\"M10 22h4\"/></symbol>\n<symbol id=\"i-download\" viewBox=\"0 0 24 24\"><path d=\"M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4\"/><path d=\"m7 10 5 5 5-5\"/><path d=\"M12 15V3\"/></symbol>\n<symbol id=\"i-save\" viewBox=\"0 0 24 24\"><path d=\"M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z\"/><path d=\"M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7\"/><path d=\"M7 3v4a1 1 0 0 0 1 1h7\"/></symbol>\n<symbol id=\"i-mailOpen\" viewBox=\"0 0 24 24\"><path d=\"M21.2 8.4c.5.4.8 1 .8 1.6v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V10a2 2 0 0 1 .8-1.6l8-6a2 2 0 0 1 2.4 0Z\"/><path d=\"m22 10-9 5.7a1.9 1.9 0 0 1-2 0L2 10\"/></symbol>\n<symbol id=\"i-wrench\" viewBox=\"0 0 24 24\"><path d=\"M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.8-3.8a6 6 0 0 1-7.9 7.9l-6.9 6.9a2.1 2.1 0 0 1-3-3l6.9-6.9a6 6 0 0 1 7.9-7.9l-3.8 3.8z\"/></symbol>\n</svg>";
const SHELL_HTML = "<div class=\"sidebar-overlay\" id=\"sidebarOverlay\" onclick=\"PANEL.toggleSidebar()\"></div>\n<div class=\"app\">\n  <aside class=\"sidebar\" id=\"sidebar\">\n    <div class=\"sidebar-logo\">\n      <div class=\"logo-identity\">\n        <img id=\"botAvatar\" src=\"\" alt=\"\">\n        <div class=\"logo-meta\">\n          <div class=\"logo-text\" id=\"botName\">加载中...</div>\n          <div class=\"logo-sub\" id=\"botSub\"></div>\n        </div>\n      </div>\n      <div id=\"shellIdentityExtra\"></div>\n    </div>\n    <nav class=\"sidebar-nav\" id=\"sidebarNav\"></nav>\n  </aside>\n  <div class=\"main\">\n    <header class=\"header\">\n      <button class=\"header-btn mobile-menu-btn\" onclick=\"PANEL.toggleSidebar()\" aria-label=\"打开导航\">☰</button>\n      <div class=\"header-breadcrumb\" id=\"breadcrumb\"><span class=\"current\">概览</span></div>\n      <div class=\"header-right\">\n        <span id=\"headerExtraSlot\"></span>\n        <span class=\"el-tag\" id=\"statusTag\"><span class=\"status-dot yellow\"></span> 检测中</span>\n        <button class=\"theme-btn\" onclick=\"PANEL.toggleTheme()\" id=\"themeBtn\" aria-label=\"切换主题\">🌙</button>\n        <button class=\"header-btn\" onclick=\"PANEL.refreshCurrentPage()\" title=\"重新加载当前页数据\">🔄 刷新</button>\n        <a class=\"header-btn\" href=\"#\" onclick=\"PANEL.logout();return false;\" id=\"logoutBtn\">🚪 退出</a>\n      </div>\n    </header>\n    <div class=\"content\" id=\"pageContent\"></div>\n    <div class=\"action-bar\" id=\"actionBar\" style=\"display:none\">\n      <span class=\"action-bar-title\" id=\"actionBarTitle\" style=\"font-size:13px;color:var(--text-secondary)\"></span>\n      <span class=\"el-tag warning\" id=\"actionBarDirty\" style=\"display:none\" title=\"有未保存的修改\">未保存</span>\n      <div class=\"bar-actions\">\n        <button class=\"btn btn-success\" id=\"actionSaveRestartBtn\" style=\"display:none\">💾 保存并重启</button>\n        <button class=\"btn btn-primary\" id=\"actionSaveBtn\">💾 保存</button>\n      </div>\n    </div>\n  </div>\n</div>\n<div class=\"toast\" id=\"toast\" role=\"status\" aria-live=\"polite\" aria-atomic=\"true\" onclick=\"PANEL.dismissToast()\"></div>\n<div class=\"ui-modal\" id=\"uiModal\" role=\"dialog\" aria-modal=\"true\" aria-labelledby=\"uiModalTitle\" hidden>\n  <div class=\"ui-modal-backdrop\" data-ui-cancel></div>\n  <div class=\"ui-modal-box\">\n    <h2 class=\"ui-modal-title\" id=\"uiModalTitle\">确认操作</h2>\n    <div class=\"ui-modal-msg\" id=\"uiModalMsg\"></div>\n    <div class=\"ui-modal-actions\">\n      <button class=\"btn btn-default\" id=\"uiModalCancel\" data-ui-cancel>取消</button>\n      <button class=\"btn btn-primary\" id=\"uiModalOk\">确认</button>\n    </div>\n  </div>\n</div>";
function ensureShell() {
  if (document.getElementById("appReady")) return;
  const holder = document.createElement("div");
  holder.id = "appReady";
  holder.innerHTML = ICON_SPRITE + SHELL_HTML;
  document.body.insertBefore(holder, document.body.firstChild);
}


/* ---------------------------------------------------------------- 小工具 */
function $(id) { return document.getElementById(id); }
function esc(s) { const d = document.createElement('div'); d.textContent = s == null ? '' : s; return d.innerHTML; }
function api(path, opts) { return fetch(path, opts).then(r => r.json()); }
function err(res) { return (res && (res.error || res.message)) || '未知错误'; }

/* ---------------------------------------------------------------- Toast */
function dismissToast() { const t = $('toast'); if (t) { clearTimeout(t._timer); t.className = 'toast'; } }
function toast(msg, type) {
  type = type || 'info';
  const t = $('toast');
  if (!t) return;
  t.textContent = msg; t.className = 'toast ' + type + ' show';
  clearTimeout(t._timer);
  /* 错误信息需要更长时间阅读（也可点击 toast 或按 Esc 提前关闭） */
  t._timer = setTimeout(() => { t.className = 'toast'; }, type === 'error' ? 6000 : 3000);
}

/* 加载失败要给出下一步，不能只说"失败" */
function errorState(msg) {
  return '<div class="empty-state"><div class="icon">❌</div><p>' + esc(msg || '加载失败') + '</p>'
    + '<div style="margin-top:14px"><button class="btn btn-default" onclick="PANEL.refreshCurrentPage()">🔄 重新加载</button></div></div>';
}

/* ---------------------------------------------------------------- 确认弹窗 */
function uiDialog(opts) {
  opts = opts || {};
  return new Promise(function (resolve) {
    const modal = $('uiModal'), ok = $('uiModalOk'), cancel = $('uiModalCancel');
    const prev = document.activeElement;
    $('uiModalTitle').textContent = opts.title || '确认操作';
    $('uiModalMsg').textContent = opts.message || '';
    ok.textContent = opts.confirmText || '确认';
    ok.className = 'btn ' + (opts.danger ? 'btn-danger-ghost' : 'btn-primary');
    cancel.textContent = opts.cancelText || '取消';
    cancel.style.display = opts.alertOnly ? 'none' : '';
    modal.hidden = false;
    /* 破坏性操作默认聚焦「取消」：误按回车不会造成后果 */
    if (opts.danger && !opts.alertOnly) cancel.focus(); else ok.focus();
    function close(v) {
      modal.hidden = true;
      ok.removeEventListener('click', onOk);
      cancel.removeEventListener('click', onCancel);
      modal.removeEventListener('click', onBackdrop);
      document.removeEventListener('keydown', onKey, true);
      if (prev && prev.focus) { try { prev.focus(); } catch (e) { } }
      resolve(v);
    }
    function onOk() { close(true); }
    function onCancel() { close(false); }
    function onBackdrop(e) { if (e.target.hasAttribute && e.target.hasAttribute('data-ui-cancel')) close(false); }
    function onKey(e) {
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(false); }
      else if (e.key === 'Enter' && document.activeElement !== cancel) { e.preventDefault(); close(true); }
      else if (e.key === 'Tab') { e.preventDefault(); (document.activeElement === ok && !opts.alertOnly ? cancel : ok).focus(); }
    }
    ok.addEventListener('click', onOk);
    cancel.addEventListener('click', onCancel);
    modal.addEventListener('click', onBackdrop);
    document.addEventListener('keydown', onKey, true);
  });
}

/* 防重复提交：请求进行中禁用按钮并回显进度 */
async function runBusy(btn, busyText, fn) {
  if (btn && btn.getAttribute('aria-busy') === 'true') return null;
  let old = null;
  if (btn) { old = btn.innerHTML; btn.setAttribute('aria-busy', 'true'); btn.disabled = true; if (busyText) btn.textContent = busyText; }
  try { return await fn(); }
  finally { if (btn) { btn.removeAttribute('aria-busy'); btn.disabled = false; if (old !== null) btn.innerHTML = old; } }
}

/* ---------------------------------------------------------------- 未保存保护 */
function isDirty(k) { return !!P.dirty[k]; }
function hasUnsaved() {
  if (P.page === 'config') return !!(P.key && P.dirty[P.key]);
  if (P.page === 'groups') return P.dirtyGroups;
  return false;
}
function syncDirtyUI() {
  const tag = $('actionBarDirty');
  if (tag) tag.style.display = hasUnsaved() ? '' : 'none';
  document.querySelectorAll('.nav-sub-item .unsaved-dot, .nav-item .unsaved-dot').forEach(function (d) { d.remove(); });
  if (P.key && P.dirty[P.key]) {
    const sub = document.querySelector('#sub_config .nav-sub-item.active');
    if (sub) sub.insertAdjacentHTML('beforeend', '<span class="unsaved-dot" title="有未保存的修改"></span>');
  }
  if (P.dirtyGroups) {
    const nav = document.querySelector('.nav-item[data-page="groups"]');
    if (nav) nav.insertAdjacentHTML('beforeend', '<span class="unsaved-dot" title="有未保存的修改"></span>');
  }
}
function clearDirty() { if (P.key) P.dirty[P.key] = false; P.dirtyGroups = false; syncDirtyUI(); }
function guardUnsaved(label) {
  if (!hasUnsaved()) return Promise.resolve(true);
  return uiDialog({
    title: '放弃未保存的修改？',
    message: (label ? label + '会丢弃' : '离开本页会丢弃') + '当前未保存的修改（配置项或群组开关）。',
    confirmText: '放弃修改', cancelText: '继续编辑', danger: true
  });
}

/* ---------------------------------------------------------------- 轮询 */
function startPoll(fn, ms) {
  if (P.timer) { clearInterval(P.timer); P.timer = null; }
  P.pollFn = fn || null; P.pollMs = ms || 10000;
  if (!P.pollFn || document.hidden) return;
  P.timer = setInterval(P.pollFn, P.pollMs);
}
function stopPoll() { if (P.timer) { clearInterval(P.timer); P.timer = null; } P.pollFn = null; }
function bindVisibility() {
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) { if (P.timer) { clearInterval(P.timer); P.timer = null; } return; }
    P.refreshHeaderStatus();
    if (P.pollFn) { try { P.pollFn(); } catch (e) { } startPoll(P.pollFn, P.pollMs); }
  });
  setInterval(function () { if (!document.hidden) P.refreshHeaderStatus(); }, 15000);
}

/* ---------------------------------------------------------------- 侧边栏 */
function renderSidebar() {
  const nav = $('sidebarNav');
  if (!nav) return;
  const groups = {};
  P.nav.forEach(function (it) { if (it.hidden) return; (groups[it.group || ''] = groups[it.group || ''] || []).push(it); });
  let html = '';
  Object.keys(groups).forEach(function (g) {
    if (g) html += '<div class="nav-group-title">' + esc(g) + '</div>';
    groups[g].forEach(function (it) {
      const active = P.page === it.id || (it.ids || []).indexOf(P.page) >= 0;
      const a11y = ' role="button" tabindex="0"' + (active ? ' aria-current="page"' : '');
      if (it.sub) {
        const open = !!P.subOpen[it.id];
        html += '<div class="nav-item ' + (active ? 'active' : '') + '"' + a11y + ' data-page="' + it.id + '"'
          + ' aria-expanded="' + (open ? 'true' : 'false') + '" aria-controls="sub_' + it.id + '"'
          + ' onclick="PANEL.toggleSubMenu(\'' + it.id + '\')">'
          + '<span class="icon">' + (it.icon || '') + '</span> ' + esc(it.label)
          + '<span class="nav-arrow" id="arrow_' + it.id + '">' + (open ? '▴' : '▾') + '</span></div>';
        html += '<div class="nav-sub" id="sub_' + it.id + '"></div>';
      } else {
        html += '<div class="nav-item ' + (active ? 'active' : '') + '"' + a11y + ' data-page="' + it.id + '"'
          + ' onclick="PANEL.navigate(\'' + it.id + '\')"><span class="icon">' + (it.icon || '') + '</span> '
          + esc(it.label) + '</div>';
      }
    });
  });
  nav.innerHTML = html;
  restoreSubMenus();
  syncDirtyUI();
}
P.subOpen = {};
function restoreSubMenus() {
  P.nav.forEach(function (it) {
    if (!it.sub) return;
    const sub = $('sub_' + it.id), arrow = $('arrow_' + it.id);
    if (!sub) return;
    const open = !!P.subOpen[it.id];
    sub.style.display = open ? 'block' : 'none';
    if (arrow) arrow.textContent = open ? '▴' : '▾';
    if (open) renderSubMenu(it.id);
  });
}
function toggleSubMenu(id) {
  P.subOpen[id] = !P.subOpen[id];
  restoreSubMenus();
}
/* 二级菜单项：两端都由各自的 endpoints 提供（Linux: 插件；桌面端: 账号 + 插件） */
function renderSubMenu(id) {
  const sub = $('sub_' + id);
  if (!sub) return;
  const render = (P.hooks.subMenus || {})[id];
  if (!render) { sub.innerHTML = ''; return; }
  sub.innerHTML = '';
  render(sub);
}
function subMenuLoading(id, text) {
  const sub = $('sub_' + id);
  if (sub) sub.innerHTML = '<div class="nav-sub-loading">' + esc(text || '加载中...') + '</div>';
}

/* ---------------------------------------------------------------- 导航 */
function closeSidebar() { $('sidebar').classList.remove('open'); $('sidebarOverlay').classList.remove('open'); }
function goPage(page, key) {
  P.page = page;
  if (key !== undefined) P.key = key;
  closeSidebar();
  renderPage();
}
function navigate(page) {
  if (page === P.page) { closeSidebar(); return; }
  guardUnsaved('切换页面').then(function (ok) { if (!ok) return; clearDirty(); goPage(page); });
}
function openPage(page, key) {
  guardUnsaved('切换页面').then(function (ok) {
    if (!ok) return;
    clearDirty();
    if (key !== undefined) P.key = key;
    P.subOpen[page] = true;
    P.page = page;
    closeSidebar();
    renderSidebar();
    renderPage();
  });
}
function refreshCurrentPage() {
  guardUnsaved('重新加载当前页').then(function (ok) { if (!ok) return; clearDirty(); renderPage(); });
}

/* ---------------------------------------------------------------- 页面挂载 */
function applyActions(data) {
  const acts = data.actions || [];
  if (!acts.length) { hideActionBar(); return; }
  const save = (P.hooks.save || {})[data.page];
  showActionBar(data.action_title, function (btn) { save && save(btn); },
    acts.indexOf('save_restart') >= 0 && P.hooks.saveRestart
      ? function (btn) { P.hooks.saveRestart(btn); } : null);
}
function showActionBar(title, onSave, onSaveRestart) {
  const bar = $('actionBar'), t = $('actionBarTitle'), btn = $('actionSaveBtn'), btn2 = $('actionSaveRestartBtn');
  if (t) t.textContent = title || '';
  /* 回调统一收到按钮元素：用于「进行中禁用 + 文案回显」 */
  if (btn) { btn.style.display = ''; btn.onclick = function () { onSave(btn); }; }
  if (btn2) {
    if (onSaveRestart) { btn2.style.display = ''; btn2.onclick = function () { onSaveRestart(btn2); }; }
    else { btn2.style.display = 'none'; btn2.onclick = null; }
  }
  if (bar) bar.style.display = 'flex';
  syncDirtyUI();
}
function hideActionBar() {
  const bar = $('actionBar');
  if (bar) bar.style.display = 'none';
  const tag = $('actionBarDirty');
  if (tag) tag.style.display = 'none';
}
function mountError(msg) { $('pageContent').innerHTML = errorState(msg); hideActionBar(); }

async function renderPage() {
  const page = P.page;
  stopPoll();
  $('pageContent').innerHTML = '<div style="text-align:center;padding:60px;color:var(--text-secondary)">⏳ 加载中...</div>';
  hideActionBar();
  try {
    const r = await api(P.endpoints.page(page));
    if (!r.ok) { mountError(r.error || '页面加载失败'); return; }
    const data = r.data;
    $('breadcrumb').innerHTML = '<span class="current">' + esc(data.crumb || page) + '</span>';
    $('pageContent').innerHTML = data.html;
    renderSidebar();
    applyActions(data);
    hydrateIcons($('pageContent'));
    const hook = (P.hooks.mounted || {})[page];
    if (hook) hook(data);
  } catch (e) { mountError('页面加载失败：' + (e.message || e)); }
}

/* ---------------------------------------------------------------- 头部状态 + 状态区片段 */
async function refreshHeaderStatus() {
  const tag = $('statusTag');
  if (!tag || !P.endpoints.headerStatus) return;
  try {
    const d = await api(P.endpoints.headerStatus());
    if (d.running) { tag.innerHTML = '<span class="status-dot green"></span> 运行中'; tag.className = 'el-tag success'; }
    else { tag.innerHTML = '<span class="status-dot red"></span> 已停止'; tag.className = 'el-tag danger'; }
  } catch (e) { tag.innerHTML = '<span class="status-dot yellow"></span> 连接失败'; tag.className = 'el-tag warning'; }
}
/* 状态区一律由后端片段提供：{html:{id:html}, text:{id:text}} —— 两端页面骨架相同，所以这里通用 */
async function refreshStatusParts() {
  if (!P.endpoints.status) return;
  try {
    const d = await api(P.endpoints.status());
    if (!d.ok) return;
    const parts = d.data || {};
    const html = parts.html || {}, text = parts.text || {};
    Object.keys(html).forEach(function (id) { const el = $(id); if (el) el.innerHTML = html[id]; });
    Object.keys(text).forEach(function (id) { const el = $(id); if (el) el.textContent = text[id]; });
    hydrateIcons($('pageContent'));
  } catch (e) { }
}

/* ---------------------------------------------------------------- 图标水合 */
const ICON_MAP = { '\u{1F916}': 'bot', '\u{1F431}': 'paw', '\u{1F9E9}': 'puzzle', '\u{1F465}': 'users', '\u{1F4CA}': 'chart', '\u{1F50D}': 'search', '\u{1F4F1}': 'qr', '\u{1F504}': 'refresh', '\u25B6': 'play', '\u23F9': 'stop', '\u{1F5A5}': 'monitor', '\u{1F319}': 'moon', '\u2600': 'sun', '\u2699': 'settings', '\u{1F6E0}': 'wrench', '\u{1F4C4}': 'file', '\u{1F5C2}': 'folder', '\u{1F9EA}': 'flask', '\u{1F4AC}': 'chat', '\u{1F680}': 'rocket', '\u26A0': 'warn', '\u2705': 'check', '\u2713': 'check', '\u274C': 'x', '\u2717': 'x', '\u{1F512}': 'lock', '\u{1F464}': 'user', '\u{1F552}': 'clock', '\u231B': 'clock', '\u{1F4C8}': 'trend', '\u{1F4CB}': 'clipboard', '\u2630': 'menu', '\u{1F6AA}': 'logout', '\u{1F500}': 'shuffle', '\u{1F4A1}': 'bulb', '\u2B07': 'download', '\u{1F4BE}': 'save', '\u{1F4ED}': 'mailOpen', '\u{1F4C1}': 'folder', '\u2795': 'plus', '\u{1F527}': 'wrench', '\u{1F517}': 'lock', '\u{1F4E6}': 'puzzle' };
const ICON_SKIP = { INPUT: 1, TEXTAREA: 1, SELECT: 1, PRE: 1, CODE: 1, SCRIPT: 1, STYLE: 1, SVG: 1 };
function iconSvg(id) { return '<svg class="ico" aria-hidden="true" focusable="false"><use href="#i-' + id + '"></use></svg>'; }
function _skip(node) {
  let el = node.parentElement;
  while (el) {
    if (ICON_SKIP[el.tagName] || el.id === 'toast' || el.classList.contains('log-viewer')) return true;
    el = el.parentElement;
  }
  return false;
}
function hydrateIcons(root) {
  root = root || document.body;
  if (!root || !document.createTreeWalker) return;
  /* emoji 多为星外平面（代理对）：字符类正则会误匹配单个代理项，必须 u 标志 + 择一匹配 */
  const RE = new RegExp('(' + Object.keys(ICON_MAP).join('|') + ')', 'u');
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: function (n) {
      if (!n.nodeValue || !RE.test(n.nodeValue)) return NodeFilter.FILTER_REJECT;
      return _skip(n) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
    }
  });
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  nodes.forEach(function (node) {
    let html = '';
    for (const ch of node.nodeValue) {
      if (ch === '\uFE0F') continue;
      const id = ICON_MAP[ch];
      html += id ? iconSvg(id) : esc(ch);
    }
    if (!html) return;
    const holder = document.createElement('span');
    holder.className = 'ico-holder';
    holder.innerHTML = html;
    node.parentNode.replaceChild(holder, node);
  });
}
let _tick = null;
function scheduleHydrate() {
  if (_tick) return;
  _tick = requestAnimationFrame(function () { _tick = null; try { hydrateIcons(document.body); } catch (e) { } });
}

/* ---------------------------------------------------------------- 主题 */
function toggleTheme() {
  const html = document.documentElement;
  const dark = html.getAttribute('data-theme') === 'dark';
  html.setAttribute('data-theme', dark ? '' : 'dark');
  try { localStorage.setItem('theme', dark ? 'light' : 'dark'); } catch (e) { }
  const btn = $('themeBtn');
  if (btn) btn.textContent = dark ? '🌙' : '☀️';
}
function restoreTheme() {
  let saved = null;
  try { saved = localStorage.getItem('theme'); } catch (e) { }
  if (saved === 'dark') { document.documentElement.setAttribute('data-theme', 'dark'); const b = $('themeBtn'); if (b) b.textContent = '☀️'; }
}
function toggleSidebar() { $('sidebar').classList.toggle('open'); $('sidebarOverlay').classList.toggle('open'); }

/* ---------------------------------------------------------------- 日志查看 */
/* 日志 DOM 上限：行数上限是 2000，全塞进 DOM 会让页面随日志增长越来越卡
   （手册 §6.3 说的"简单版虚拟滚动"：只渲染最近 N 行） */
const LOG_MAX_ROWS = 500;
function logState(sfx) {
  if (!P.logs[sfx]) P.logs[sfx] = { lines: 100, auto: true, raw: '' };
  return P.logs[sfx];
}
function logViewerEl(sfx) { return $(sfx === '2' ? 'napcatLogViewer' : 'logViewer'); }
function logNearBottom(v) { return !v || (v.scrollHeight - v.scrollTop - v.clientHeight) < 48; }
function scrollLogToEnd(sfx) {
  const v = logViewerEl(sfx);
  if (!v) return;
  v.scrollTop = v.scrollHeight;
  const h = $('logScrollHint' + sfx);
  if (h) h.style.display = 'none';
}
function syncLogState(sfx) {
  const st = logState(sfx);
  const sel = $('logLinesSel' + sfx);
  if (sel) sel.value = String(st.lines);
  const ref = $('logAutoRef' + sfx);
  if (ref) ref.checked = !!st.auto;
}
function setLogLines(n, sfx) {
  sfx = sfx || '';
  const st = logState(sfx);
  st.lines = Math.max(50, Math.min(2000, n | 0));
  const sel = $('logLinesSel' + sfx);
  if (sel) {
    if (!Array.prototype.some.call(sel.options, function (o) { return +o.value === st.lines; })) {
      const o = document.createElement('option');
      o.value = st.lines; o.textContent = st.lines + ' 行';
      sel.appendChild(o);
    }
    sel.value = String(st.lines);
  }
  loadLogs(sfx);
}
function moreLogs(sfx) { sfx = sfx || ''; setLogLines(logState(sfx).lines + 200, sfx); }
function setLogAutoRefresh(sfx, on) {
  sfx = sfx || '';
  logState(sfx).auto = !!on;
  if (!on) { stopPoll(); return; }
  startPoll(function () { loadLogs(sfx); }, 5000);
}
function applyLogFilter() {
  const sel = $('logFilterSel');
  if (sel) P.filter = sel.value;
  scrollLogToEnd('');
  renderLogViewer('');
}
function logLineClass(line) {
  if (line.indexOf('接收 <-') !== -1) return 'recv';
  if (line.indexOf('发送 ->') !== -1) return 'send';
  const m = line.match(/\[(debug|info|warn|error)\]/i);
  if (m) return m[1].toLowerCase();
  if (line.match(/失败|异常|错误|✗|❌|error|exception|traceback/i)) return 'error';
  if (line.match(/超时|警告|⚠|防抖|跳过|不可用|无效|warn/i)) return 'warn';
  if (line.match(/✓|成功|完成|启动|连接|加载|ok|发送|接收|处理|info/i)) return 'info';
  return '';
}
async function loadLogs(sfx) {
  sfx = sfx || '';
  try {
    const st = logState(sfx);
    const d = await api(P.endpoints.logs(sfx, st.lines));
    st.raw = d.log || (sfx === '2' ? '' : '暂无日志');
    renderLogViewer(sfx);
    if (sfx !== '2') {
      const total = $('logTotalInfo');
      if (total && d.total !== undefined) total.textContent = '共 ' + (d.total || '-') + ' 行 · 显示 ' + st.lines + ' 行';
    }
  } catch (e) { }
}
function renderLogViewer(sfx) {
  const v = logViewerEl(sfx);
  if (!v) return;
  const st = logState(sfx);
  const stick = logNearBottom(v);
  if (sfx === '2') {
    v.innerHTML = (st.raw || '暂无容器日志').split('\n').map(function (l) { return esc(l); }).join('\n');
  } else {
    const rows = [];
    (st.raw || '暂无日志').split('\n').forEach(function (line) {
      const cls = logLineClass(line);
      if (P.filter === 'error' && cls !== 'error') return;
      if (P.filter === 'warn' && cls !== 'warn' && cls !== 'error') return;
      if (P.filter === 'info' && cls === 'debug') return;
      if (P.filter === 'debug' && cls !== 'debug') return;
      let display = esc(line);
      const tm = line.match(/^(\d{2}-\d{2} \d{2}:\d{2}:\d{2})/);
      if (tm) display = '<span style="color:#6a737d">' + tm[1] + '</span>' + display.slice(tm[1].length);
      rows.push('<div class="' + cls + '">' + display + '</div>');
    });
    let html = '';
    if (rows.length > LOG_MAX_ROWS) {
      html += '<div style="color:var(--text-secondary);padding:4px 10px">（已省略较早的 '
        + (rows.length - LOG_MAX_ROWS) + ' 行，只显示最近 ' + LOG_MAX_ROWS + ' 行）</div>';
      rows.splice(0, rows.length - LOG_MAX_ROWS);
    }
    if (!rows.length) {
      html = '<div style="color:var(--text-secondary);padding:10px">没有匹配的日志。把「级别」切到「全部级别」可以看到更多内容。</div>';
    } else {
      html += rows.join('');
    }
    v.innerHTML = html;
  }
  /* 自动滚动只在"用户本来就在底部"时执行：否则刷新会把正在翻日志的人拽回底部 */
  if (!v._scrollBound) {
    v._scrollBound = true;
    v.addEventListener('scroll', function () {
      const h = $('logScrollHint' + sfx);
      if (h) h.style.display = logNearBottom(v) ? 'none' : '';
    });
  }
  if (stick) v.scrollTop = v.scrollHeight;
  const hint = $('logScrollHint' + sfx);
  if (hint) hint.style.display = stick ? 'none' : '';
}

/* ---------------------------------------------------------------- 群组矩阵 */
function markGroupsDirty() { if (!P.dirtyGroups) P.dirtyGroups = true; syncDirtyUI(); }
function tgState() { return global._tgState || (global._tgState = {}); }
function tgToggle(gid, plugin, checked) {
  const st = tgState();
  if (!st[gid]) st[gid] = {};
  st[gid][plugin] = checked;
  markGroupsDirty();
  const rowChk = document.querySelector('.tg-r[data-tgg="' + gid + '"]');
  if (rowChk) rowChk.checked = Object.keys(st[gid]).every(function (p) { return st[gid][p]; });
  const colChk = document.querySelector('.tg-ac[data-tgp="' + plugin + '"]');
  if (colChk) colChk.checked = Object.keys(st).every(function (g) { return st[g] && st[g][plugin]; });
}
function tgToggleGroup(gid, checked) {
  const st = tgState();
  if (!st[gid]) return;
  Object.keys(st[gid]).forEach(function (p) { st[gid][p] = checked; });
  markGroupsDirty();
  document.querySelectorAll('.tg-c[data-tgg="' + gid + '"]').forEach(function (c) { c.checked = checked; });
  const rowChk = document.querySelector('.tg-r[data-tgg="' + gid + '"]');
  if (rowChk) rowChk.checked = checked;
  document.querySelectorAll('.tg-ac').forEach(function (c) {
    const pk = c.getAttribute('data-tgp');
    c.checked = Object.keys(st).every(function (g) { return st[g] && st[g][pk]; });
  });
}
function tgToggleAllPlugin(plugin, checked) {
  const st = tgState();
  Object.keys(st).forEach(function (g) { st[g][plugin] = checked; });
  markGroupsDirty();
  document.querySelectorAll('.tg-c[data-tgp="' + plugin + '"]').forEach(function (c) { c.checked = checked; });
  const colChk = document.querySelector('.tg-ac[data-tgp="' + plugin + '"]');
  if (colChk) colChk.checked = checked;
  document.querySelectorAll('.tg-r').forEach(function (r) {
    const gid = r.getAttribute('data-tgg');
    r.checked = Object.keys(st[gid] || {}).every(function (p) { return st[gid][p]; });
  });
}
function tgToggleAll(checked) {
  const st = tgState();
  Object.keys(st).forEach(function (g) { Object.keys(st[g]).forEach(function (p) { st[g][p] = checked; }); });
  markGroupsDirty();
  document.querySelectorAll('.tg-c, .tg-r, .tg-ac').forEach(function (c) { c.checked = checked; });
}
async function tgSave(btn) {
  const st = global._tgState;
  if (!st || !Object.keys(st).length) return;
  btn = btn || $('actionSaveBtn');
  const snapshot = JSON.parse(JSON.stringify(st));
  await runBusy(btn, '保存中…', async function () {
    const d = await P.endpoints.saveToggles(snapshot);
    if (!d.ok) { toast('群组开关保存失败：' + err(d), 'error'); return; }
    P.dirtyGroups = false; syncDirtyUI();
    toast('群组开关已保存（' + Object.keys(snapshot).length + ' 个群）', 'success');
  });
}
/* 群组状态由后端片段带过来（innerHTML 插入的 <script> 不执行，所以用 JSON 数据块） */
function readGroupsState(id) {
  const el = $(id || 'groupsState');
  try { global._tgState = el ? JSON.parse(el.textContent) : {}; } catch (e) { global._tgState = {}; }
  P.dirtyGroups = false; syncDirtyUI();
}

/* ---------------------------------------------------------------- 插件配置（schema 驱动） */
function renderConfigForm(key) {
  const form = $('configForm');
  if (!form) return Promise.resolve();
  P.key = key;
  if (!key) { form.innerHTML = '<div class="cf-help" style="padding:10px 0">没有可配置的插件。</div>'; return Promise.resolve(); }
  form.innerHTML = '<div class="cf-help" style="padding:10px 0">载入中…</div>';
  return api(P.endpoints.schema(key)).then(async function (d) {
    if (!d.ok) { form.innerHTML = errorState(d.error || '读不到配置声明'); return; }
    P.schema = d.data;
    /* 群号选择器的选项来自外壳，且必须**渲染前**就位：否则首屏是一张空下拉，
       用户会以为"一个群都没有"（以前只是异步拉取、拉回来又不重渲染，就成这样了）。
       拉失败不阻塞表单：provider 会退化成"可手填群号"。 */
    if ((P.schema.fields || []).some(function (f) { return f.type === 'group_select'; })) {
      const lg = P.hooks.loadGroups;
      if (lg) { try { await lg(); } catch (e) { } }
    }
    CFGCTL.renderForm(form, P.schema);
    const title = $('cfgTitle'), src = $('cfgSrc'), cnt = $('cfgCount');
    if (title) title.textContent = P.schema.plugin_name || key;
    if (src) {
      src.textContent = P.schema.declared
        ? '由插件声明（' + (P.schema.declared_by || '__config_schema__') + '）'
        : '插件未声明配置项 · 字段按当前值自动推断';
      src.className = 'el-tag ' + (P.schema.declared ? 'success' : 'warning');
    }
    if (cnt) cnt.textContent = (P.schema.fields || []).length + ' 项';
    const box = $('cfgSchemaErrors');
    if (box) {
      const errs = P.schema.schema_errors || [];
      box.style.display = errs.length ? '' : 'none';
      box.innerHTML = errs.length
        ? '<div class="el-tag warning" style="display:block;padding:8px 12px;white-space:normal">声明有 '
          + errs.length + ' 处问题（已跳过这些字段）：' + esc(errs.join('；')) + '</div>' : '';
    }
    P.dirty[key] = false;
    syncDirtyUI();
  }).catch(function (e) { form.innerHTML = errorState('读不到配置声明：' + (e.message || e)); });
}
function cfgTab(which) {
  if (which === P.tab) return;
  const form = $('configForm'), json = $('configJson');
  if (which === 'json') {
    json.value = JSON.stringify((P.schema && P.schema.values) || {}, null, 2);
  } else {
    let obj;
    try { obj = JSON.parse(json.value); }
    catch (e) { toast('JSON 格式错误，无法切回表单：' + e.message, 'error'); return; }
    if (P.schema) {
      P.schema.values = obj;
      /* 按 path 回填：分段配置（settings.foo）用字段名去取是取不到的 */
      (P.schema.fields || []).forEach(function (f) {
        const v = CFGCTL.getPath(obj, CFGCTL.fieldPath(f));
        if (v !== undefined) f.value = v;
      });
      CFGCTL.renderForm(form, P.schema);
    }
  }
  P.tab = which;
  form.style.display = which === 'form' ? '' : 'none';
  json.style.display = which === 'json' ? '' : 'none';
  const tf = $('tab-form'), tj = $('tab-json');
  if (tf) tf.classList.toggle('on', which === 'form');
  if (tj) tj.classList.toggle('on', which === 'json');
}
function cfgMsg(text, bad) {
  const el = $('cfgMsg');
  if (!el) return;
  el.textContent = text || '';
  el.style.color = bad ? 'var(--color-danger)' : 'var(--text-secondary)';
}
function markCfgDirty() { if (P.page === 'config' && P.key && !P.dirty[P.key]) { P.dirty[P.key] = true; syncDirtyUI(); } }

async function saveConfig(btn, restart) {
  if (!P.key) return;
  btn = btn || $(restart ? 'actionSaveRestartBtn' : 'actionSaveBtn');
  const root = $('configForm'), isRaw = P.tab === 'json';
  let obj;
  if (isRaw) {
    try { obj = JSON.parse($('configJson').value); }
    catch (e) { cfgMsg('JSON 解析失败：' + e.message, true); return; }
  } else obj = CFGCTL.collect(root, P.schema);
  await runBusy(btn, '保存中…', async function () {
    const d = await P.endpoints.saveConfig(P.key, obj, isRaw);
    if (!d.ok) {
      /* 精确到字段的错误 → 标红到控件（服务端此时一字节都没落盘）
         错误走 `{ok:false, error, field_errors}`、成功走 `{ok:true, data:{...}}`，
         所以这里两种位置都认一下，别因为信封层级不同把提示变成假话。 */
      const errs = d.field_errors || (d.data && d.data.field_errors) || {};
      CFGCTL.clearErrors(root);
      let n = 0;
      for (const k of Object.keys(errs)) { CFGCTL.fieldError(root, k, errs[k]); n++; }
      const msg = (d.error || '保存失败') + (n ? '（' + n + ' 个字段有问题，已标红）' : '');
      cfgMsg(msg, true);
      toast('保存失败：' + (d.error || '校验未通过'), 'error');
      return;
    }
    /* 成功信封两端不同：Linux 是 `{ok, validated, ...}` 扁平，桌面端是 `{ok, data:{...}}`。
       共用外壳必须都认，否则会显示"未做类型校验"这种假话。 */
    const dd = (d.data && typeof d.data === 'object') ? d.data : d;
    P.dirty[P.key] = false; syncDirtyUI();
    cfgMsg('');
    toast('已保存：' + ((P.schema && (P.schema.plugin_name || P.schema.plugin)) || P.key)
      + (dd.validated ? '' : '（该插件未声明配置项，未做类型校验）'), 'success');
    refreshHeaderStatus();
    await renderConfigForm(P.key);          // 回读服务端归一化后的值
    if (restart) {
      toast('已保存，正在重启…', 'success');
      await new Promise(function (r) { setTimeout(r, 300); });
      const rd = await (P.hooks.restart || function () { return Promise.resolve({ ok: true }); })();
      if (rd && !rd.ok) toast('已保存，但重启失败：' + err(rd), 'error');
      else toast('已保存并重启', 'success');
      refreshHeaderStatus();
    }
  });
}


/* ---------------------------------------------------------------- 动作（启动/停止/重启/二维码）
   确认语义与进行中文案只在这里定义一次，两端行为必然一致；各端只需实现 hooks.actions[name]。 */
const ACTIONS = {
  start: { label: '启动', busy: '启动中…', done: '机器人已启动' },
  stop: { label: '停止', busy: '停止中…', done: '机器人已停止',
          confirm: { title: '停止机器人？', message: '停止后机器人不再接收和回复任何消息，直到你再次启动它。', confirmText: '停止机器人' } },
  restart: { label: '重启', busy: '重启中…', done: '机器人已重启' },
  'napcat-restart': { label: '重启 NapCat', busy: '重启中…', done: 'NapCat 已重启',
          confirm: { title: '重启 NapCat？', message: '重启会短暂断开与 QQ 的连接。如果登录态已失效，重启后需要重新扫码登录。', confirmText: '重启 NapCat' } },
  'del-account': { label: '删除账号', confirm: { title: '删除账号？', message: '删除后该账号的配置与数据目录都会被移除，无法撤销。', confirmText: '删除账号' } }
};
P.act = async function (name, btn) {
  const a = ACTIONS[name] || { label: name, busy: '处理中…' };
  if (name === 'qr') return P.showQR(btn);
  if (a.confirm) {
    const ok = await uiDialog(Object.assign({ cancelText: '取消', danger: true }, a.confirm));
    if (!ok) return;
  }
  const fn = (P.hooks.actions || {})[name];
  if (!fn) { toast('该功能在当前端不可用', 'warning'); return; }
  await runBusy(btn, a.busy, async function () {
    toast('正在' + a.label + '…', 'info');
    let r = null;
    /* 回调统一收到按钮元素：动作要能读到 data-key（如"编辑/删除第 N 个账号"） */
    try { r = await fn(btn); } catch (e) { r = { ok: false, error: e.message || '网络错误' }; }
    if (r && r.ok === false) toast(a.label + '失败：' + err(r), 'error');
    else toast((r && (r.message || r.msg)) || a.done, 'success');
    refreshHeaderStatus();
    setTimeout(refreshStatusParts, 1500);
  });
};
/* 二维码：两端同一套交互（展开/收起 + 拿不到就说明原因） */
P.showQR = async function (btn) {
  const area = $('qrArea');
  if (!area) return;
  if (area.style.display === 'block') { area.style.display = 'none'; return; }
  area.style.display = 'block';
  const box = $('qrContainer');
  box.innerHTML = '获取中…';
  await runBusy(btn, null, async function () {
    if (!P.endpoints.qr) { box.innerHTML = '<div style="color:var(--text-secondary)">当前端不支持二维码登录</div>'; return; }
    try {
      const d = await api(P.endpoints.qr());
      if (d && d.qr) box.innerHTML = '<img src="data:image/png;base64,' + d.qr + '" style="max-width:240px;width:100%;border-radius:8px" alt="登录二维码">';
      else box.innerHTML = '<div style="color:var(--text-secondary)">暂无二维码<br>' + esc((d && (d.error || d.message)) || '账号可能已登录') + '</div>';
    } catch (e) {
      box.innerHTML = '<div style="color:var(--color-danger)">二维码获取失败，请稍后重试</div>';
    }
  });
};

function logAct(name, sfx) {
  if (name === 'refresh') return loadLogs(sfx);
  if (name === 'more') return moreLogs(sfx);
  if (name === 'scroll') return scrollLogToEnd(sfx);
}

/* ---------------------------------------------------------------- 事件委托 + 键盘可达 */
function bindDelegates() {
  document.addEventListener('input', function (e) {
    if (e.target.closest && e.target.closest('#configForm')) markCfgDirty();
  });
  document.addEventListener('change', function (e) {
    const t = e.target;
    if (t.closest && t.closest('#configForm')) markCfgDirty();
    let el = t.closest('[data-log-lines]');
    if (el) { setLogLines(+el.value, el.getAttribute('data-sfx') || ''); return; }
    el = t.closest('[data-log-auto]');
    if (el) { setLogAutoRefresh(el.getAttribute('data-sfx') || '', el.checked); return; }
    el = t.closest('[data-log-filter]');
    if (el) { P.filter = el.value; scrollLogToEnd(''); renderLogViewer(''); return; }
    el = t.closest('[data-tg-all]');
    if (el) { tgToggleAll(el.checked); return; }
    el = t.closest('.tg-ac');
    if (el) { tgToggleAllPlugin(el.getAttribute('data-tgp'), el.checked); return; }
    el = t.closest('.tg-r');
    if (el) { tgToggleGroup(el.getAttribute('data-tgg'), el.checked); return; }
    el = t.closest('.tg-c');
    if (el) { tgToggle(el.getAttribute('data-tgg'), el.getAttribute('data-tgp'), el.checked); return; }
  });
  document.addEventListener('click', function (e) {
    const t = e.target;
    /* 后端片段里不写内联 JS：一律用 data-* 声明"这是干什么的"，行为在这里统一绑定 */
    let el = t.closest('[data-act]');
    if (el) { if (el.tagName === 'A') e.preventDefault(); P.act(el.getAttribute('data-act'), el); return; }
    el = t.closest('[data-nav]');
    if (el && el.tagName === 'A') e.preventDefault();
    el = t.closest('[data-open]');
    if (el) { openPage(el.getAttribute('data-open'), el.getAttribute('data-key')); return; }
    el = t.closest('[data-nav]');
    if (el) { navigate(el.getAttribute('data-nav')); return; }
    el = t.closest('[data-acct-pick]');
    if (el) { P.hooks.pickAccount && P.hooks.pickAccount(el.getAttribute('data-acct-pick')); return; }
    el = t.closest('[data-cfg-tab]');
    if (el) { cfgTab(el.getAttribute('data-cfg-tab')); return; }
    el = t.closest('[data-log-act]');
    if (el) { logAct(el.getAttribute('data-log-act'), el.getAttribute('data-sfx') || ''); return; }
    el = t.closest('[data-refresh]');
    if (el) { refreshCurrentPage(); return; }
    el = t.closest('[data-page]');
    if (el) { navigate(el.getAttribute('data-page')); return; }
    el = t.closest('.tg-ac');
    if (el) { tgToggleAllPlugin(el.getAttribute('data-tgp'), el.checked); return; }
    el = t.closest('.tg-r');
    if (el) { tgToggleGroup(el.getAttribute('data-tgg'), el.checked); return; }
    el = t.closest('.tg-c');
    if (el) { tgToggle(el.getAttribute('data-tgg'), el.getAttribute('data-tgp'), el.checked); return; }
  });
  /* role="button" 的自定义控件（导航项、插件卡片、日志提示）用回车/空格触发 */
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { dismissToast(); return; }
    if (e.key !== 'Enter' && e.key !== ' ' && e.key !== 'Spacebar') return;
    const el = e.target && e.target.closest ? e.target.closest('[role="button"][tabindex]') : null;
    if (!el) return;
    e.preventDefault();
    el.click();
  });
}

/* ---------------------------------------------------------------- 启动 */
P.start = async function () {
  if (P.booted) return;
  P.booted = true;
  ensureShell();
  try { localStorage.getItem('theme'); } catch (e) {
    /* file:// 下 localStorage 可能不可用：套一层内存兜底，避免裸访问就白屏 */
    const mem = {};
    global.localStorage = { getItem: k => (k in mem ? mem[k] : null), setItem: (k, v) => { mem[k] = String(v); }, removeItem: k => { delete mem[k]; } };
  }
  if (P.hooks.beforeStart) { try { await P.hooks.beforeStart(); } catch (e) { } }
  restoreTheme();
  if (P.hooks.headerButtons) P.hooks.headerButtons($('headerExtraSlot'));
  if (P.hooks.bindExtra) P.hooks.bindExtra();
  if (global.CFGCTL) {
    CFGCTL.groupSelectProvider = function () { return (P.hooks.groupSelect && P.hooks.groupSelect()) || { groups: [], error: '' }; };
    CFGCTL.onGroupRefresh = function () { P.hooks.loadGroups && P.hooks.loadGroups(true); };
  }
  bindDelegates();
  bindVisibility();
  renderSidebar();
  hydrateIcons(document.body);
  new MutationObserver(scheduleHydrate).observe(document.body, { childList: true, subtree: true });
  scheduleHydrate();
  if (P.hooks.identity) { try { await P.hooks.identity(); } catch (e) { } }
  refreshHeaderStatus();
  if (P.hooks.startPage) P.page = P.hooks.startPage();
  renderPage();
  if (P.hooks.subMenus && P.hooks.subMenus.config) { P.subOpen.config = true; renderSidebar(); }
};

/* 供各端与页面胶水使用 */
P.$ = $; P.api = api; P.err = err; P.esc = esc;
P.toast = toast; P.dialog = uiDialog; P.runBusy = runBusy; P.errorState = errorState;
P.navigate = navigate; P.openPage = openPage; P.goPage = goPage;
P.renderPage = renderPage; P.refreshCurrentPage = refreshCurrentPage;
P.renderSidebar = renderSidebar; P.toggleSubMenu = toggleSubMenu; P.renderSubMenu = renderSubMenu;
P.subMenuLoading = subMenuLoading; P.restoreSubMenus = restoreSubMenus;
P.toggleSidebar = toggleSidebar; P.toggleTheme = toggleTheme; P.hydrateIcons = hydrateIcons;
P.startPoll = startPoll; P.stopPoll = stopPoll; P.showActionBar = showActionBar; P.hideActionBar = hideActionBar;
P.refreshStatusParts = refreshStatusParts; P.refreshHeaderStatus = refreshHeaderStatus;
P.renderConfigForm = renderConfigForm; P.cfgTab = cfgTab; P.cfgMsg = cfgMsg;
P.saveConfig = saveConfig; P.markCfgDirty = markCfgDirty;
P.tgSave = tgSave; P.readGroupsState = readGroupsState; P.markGroupsDirty = markGroupsDirty;
P.loadLogs = loadLogs; P.setLogLines = setLogLines; P.moreLogs = moreLogs;
P.renderLogViewer = renderLogViewer; P.LOG_MAX_ROWS = LOG_MAX_ROWS;
P.setLogAutoRefresh = setLogAutoRefresh; P.applyLogFilter = applyLogFilter;
P.scrollLogToEnd = scrollLogToEnd; P.syncLogState = syncLogState; P.logState = logState;
P.syncDirtyUI = syncDirtyUI; P.hasUnsaved = hasUnsaved; P.clearDirty = clearDirty;
P.dismissToast = dismissToast;
P.logout = function () { if (P.hooks.logout) P.hooks.logout(); };
})(window);

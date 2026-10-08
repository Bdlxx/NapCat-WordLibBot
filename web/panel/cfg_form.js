/* ==========================================================================
   插件配置表单：**字段类型 → 控件 的唯一映射表**（两端共用）
   主本：/root/mybot2/web/panel/cfg_form.js
   副本：/root/astercore/src/astercore/web/static/cfg_form.js（必须字节一致）
   一致性校验：/root/mybot2/tests/test_dual_end_assets.py

   可配置项由插件自己声明（模块级 `__config_schema__`，见 web/config_schema.py），
   所以这份文件里**不出现任何具体插件的名字**：加插件不用改前端。

   支持类型：text / textarea / number / bool / select / multiselect / list /
             password / group_select / color / file（+ json 兜底嵌套对象）

   字段的 `path` 是值在配置文件里的位置（如 settings.favor_add_max、glm.api_key）；
   控件用 `data-k="<字段名>"` 提交，服务端按 path 写回 —— 分段配置（commands/
   settings/messages）必须靠它才不会写错地方。
   ========================================================================== */
(function (global) {
'use strict';

/* ---------------------------------------------------------------- 小工具 */
function esc(v) {
  return String(v == null ? '' : v)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
/* 按点号路径取值（JSON 页签切回表单时用） */
function getPath(obj, path) {
  var cur = obj;
  var parts = String(path == null ? '' : path).split('.');
  for (var i = 0; i < parts.length; i++) {
    if (cur == null || typeof cur !== 'object' || !(parts[i] in cur)) return undefined;
    cur = cur[parts[i]];
  }
  return cur;
}
/* 按点号路径写值（JSON 页签里改过的值同步回字段） */
function setPath(obj, path, value) {
  var parts = String(path == null ? '' : path).split('.');
  var cur = obj;
  for (var i = 0; i < parts.length - 1; i++) {
    if (typeof cur[parts[i]] !== 'object' || cur[parts[i]] === null) cur[parts[i]] = {};
    cur = cur[parts[i]];
  }
  cur[parts[parts.length - 1]] = value;
}
function fieldPath(f) { return f && (f.path || f.name); }
function optHtml(options) {
  return (options || []).map(function (o) {
    return '<option value="' + esc(o.value) + '">' + esc(o.label) + '</option>';
  }).join('');
}

/* ---------------------------------------------------------------- 控件 */
/* f = 字段声明，value = 当前值，path = 提交用的键（字段名） */
function control(f, value, path) {
  var k = 'data-k="' + esc(path) + '"';
  var ph = f.placeholder ? ' placeholder="' + esc(f.placeholder) + '"' : '';
  switch (f.type) {
    case 'textarea':
      return '<textarea ' + k + ' rows="' + (f.rows || 4) + '"' + ph + '>' + esc(value) + '</textarea>';
    case 'json':
      return '<textarea ' + k + ' rows="' + (f.rows || 5) + '" spellcheck="false">'
        + esc(typeof value === 'string' ? value : JSON.stringify(value == null ? {} : value, null, 2))
        + '</textarea><div class="cf-help">JSON 格式，保存时校验</div>';
    case 'number':
      return '<div class="cf-inline"><input type="number" ' + k + ' value="' + esc(value) + '"'
        + (f.min != null ? ' min="' + f.min + '"' : '')
        + (f.max != null ? ' max="' + f.max + '"' : '')
        + (f.step != null ? ' step="' + f.step + '"' : '') + '>'
        + (f.unit ? '<span class="cf-unit">' + esc(f.unit) + '</span>' : '') + '</div>';
    case 'bool':
      return '<label class="cf-check"><input type="checkbox" ' + k + (value ? ' checked' : '') + '>'
        + '<span>' + (value ? '已开启' : '已关闭') + '</span></label>';
    case 'select':
      return '<select ' + k + '><option value="">（未设置）</option>' + optHtml(f.options) + '</select>';
    case 'multiselect':
      var vals = Array.isArray(value) ? value.map(String) : [];
      return '<div class="cf-rows">' + (f.options || []).map(function (o) {
        var on = vals.indexOf(String(o.value)) >= 0;
        return '<label class="cf-check"><input type="checkbox" data-multi="' + esc(path) + '"'
          + ' value="' + esc(o.value) + '"' + (on ? ' checked' : '') + '><span>' + esc(o.label) + '</span></label>';
      }).join('') + '</div>';
    case 'list':
      return listHtml(f, Array.isArray(value) ? value : [], path);
    case 'password':
      return '<div class="cf-inline"><input type="' + (f.secret === false ? 'text' : 'password') + '" ' + k
        + ' value="' + esc(value) + '"' + ph + ' autocomplete="new-password">'
        + '<button class="mini" type="button" onclick="cfgPeek(this)">显示</button></div>';
    case 'group_select':
      return groupSelect(f, value, path);
    case 'color':
      return '<div class="cf-inline"><input type="color" data-color="' + esc(path) + '"'
        + ' value="' + esc(value || '#1E40AF') + '">'
        + '<input type="text" ' + k + ' value="' + esc(value) + '" placeholder="#1E40AF"></div>';
    case 'file':
      return '<input type="text" ' + k + ' value="' + esc(value) + '"'
        + (f.accept ? ' placeholder="路径（' + esc(f.accept) + '）"' : '') + '>'
        + (f.accept ? '<div class="cf-help">可接受：' + esc(f.accept) + '</div>' : '');
    default:
      return '<input type="text" ' + k + ' value="' + esc(value) + '"'
        + (f.maxlength ? ' maxlength="' + f.maxlength + '"' : '') + ph + '>';
  }
}

function listItemControl(f, value, path) {
  var t = f.item_type || 'text';
  if (t === 'bool') return '<input type="checkbox" data-item="' + esc(path) + '"' + (value ? ' checked' : '') + '>';
  if (t === 'number') return '<input type="number" data-item="' + esc(path) + '" value="' + esc(value) + '" style="flex:1">';
  if (t === 'select') return '<select data-item="' + esc(path) + '" style="flex:1"><option value="">（未设置）</option>' + optHtml(f.options) + '</select>';
  return '<input type="text" data-item="' + esc(path) + '" value="' + esc(value) + '" style="flex:1">';
}

function listHtml(f, values, path) {
  var rows = values.map(function (v, i) {
    return '<div class="cf-rowitem">' + listItemControl(f, v, path + '[' + i + ']')
      + '<button class="mini" type="button" onclick="cfgListDel(this)">删除</button></div>';
  }).join('');
  return '<div class="cf-rows" data-list="' + esc(path) + '" data-item-type="' + (f.item_type || 'text') + '">'
    + rows + '<div><button class="mini" type="button" onclick="cfgListAdd(this)">+ 添加一项</button></div></div>';
}

/* 群号选择器：群列表由**外壳**提供（每个项目的取群方式不同），拿不到就退化成手填，
   不能因为接口挂了把用户卡死在配置页。 */
function groupSelect(f, value, path) {
  var vals = Array.isArray(value) ? value.map(String)
    : (value == null || value === '' ? [] : [String(value)]);
  var provider = global.CFGCTL && global.CFGCTL.groupSelectProvider;
  var info = (typeof provider === 'function' ? provider() : null) || {};
  var groups = info.groups || [];
  var err = info.error || '';
  if (err) {
    return '<input type="text" ' + (f.multiple !== false ? 'data-multi-text' : 'data-k') + '="' + esc(path) + '"'
      + ' value="' + esc(vals.join(',')) + '" placeholder="群号，多个用英文逗号分隔">'
      + '<div class="cf-help">此刻拉不到群列表（' + esc(err) + '），可手填群号</div>';
  }
  var opts = groups.map(function (g) {
    var id = String(g.group_id || g.id || '');
    var nm = g.group_name || g.name || '';
    return '<option value="' + esc(id) + '"' + (vals.indexOf(id) >= 0 ? ' selected' : '') + '>'
      + esc(nm ? (nm + '（' + id + '）') : id) + '</option>';
  }).join('');
  /* 已选但不在列表里的群（机器人退群了）也必须显示，否则一保存就丢 */
  var extra = vals.filter(function (v) {
    return !groups.some(function (g) { return String(g.group_id || g.id || '') === v; });
  }).map(function (v) {
    return '<option value="' + esc(v) + '" selected>' + esc(v) + '（当前列表里没有）</option>';
  }).join('');
  return '<select ' + (f.multiple !== false ? 'multiple size="5"' : '') + ' data-multi-select="' + esc(path) + '">'
    + extra + opts + '</select><div class="cf-help">从机器人已加入的群拉取'
    + (f.multiple !== false ? '（可多选，按住 Ctrl/⌘）' : '（单选）')
    + '　<button class="mini" type="button" onclick="CFGCTL.refreshGroups()">刷新群列表</button></div>';
}

/* 一个字段 = 标签 + 控件 + 说明 + 错误位 */
function fieldHtml(f) {
  /* unset：插件声明了这一项，但配置文件里还没有它（插件内置默认在生效）。
     面板如实说明，并且保持默认值保存不会把它写进配置。 */
  var unset = f.unset
    ? '<div class="cf-help">配置里当前没有这一项（插件内置默认值生效中）；保持默认值保存不会写入它。</div>'
    : '';
  return '<div class="cf-field" data-field="' + esc(f.name) + '">'
    + '<label class="cf-label">' + esc(f.label || f.name)
    + (f.required ? ' <span style="color:var(--cf-danger,#dc2626)">*</span>' : '')
    /* 类型徽标用 cf-type：`.cf-help` 要留给字段自身的说明（面板与测试都按"第一个
       .cf-help 是说明"来读，别把徽标塞进去） */
    + '<span class="cf-type"> · ' + esc(f.type) + '</span></label>'
    + control(f, f.value, f.name)
    + (f.help ? '<div class="cf-help">' + esc(f.help) + '</div>' : '')
    + unset
    + '<div class="cf-err" hidden></div></div>';
}

/* 渲染整张表单：按 group 分段，advanced 折叠；没有可配置项时给出下一步 */
function renderForm(box, payload, opts) {
  opts = opts || {};
  var fields = (payload && payload.fields) || [];
  if (!fields.length) {
    box.innerHTML = opts.emptyHtml || ('<div class="cf-help" style="padding:10px 0">这个插件没有可配置项。'
      + '需要的话可以在插件里声明 <code>__config_schema__</code>，或切到 JSON 页签直接编辑。</div>');
    return;
  }
  var html = '', lastGroup = null, advOpen = false;
  for (var i = 0; i < fields.length; i++) {
    var f = fields[i];
    if (f.advanced && !advOpen) { html += '<details class="cf-advanced"><summary>高级选项</summary>'; advOpen = true; }
    var g = f.group || '';
    if (!f.advanced && g && g !== lastGroup) { html += '<div class="cf-group">' + esc(g) + '</div>'; lastGroup = g; }
    html += fieldHtml(f);
  }
  if (advOpen) html += '</details>';
  box.innerHTML = html;
  bindLive(box);
}

/* 颜色控件联动 + 开关文字；纯展示，不影响提交值 */
function bindLive(root) {
  root.querySelectorAll('[data-color]').forEach(function (el) {
    el.oninput = function () {
      var t = el.parentNode.querySelector('input[type=text]');
      if (t) t.value = el.value;
    };
  });
  root.querySelectorAll('input[type=checkbox][data-k]').forEach(function (el) {
    el.onchange = function () {
      var s = el.parentNode.querySelector('span');
      if (s) s.textContent = el.checked ? '已开启' : '已关闭';
    };
  });
}

/* ---------------------------------------------------------------- 交互 */
function peek(btn) {
  var inp = btn.parentNode.querySelector('input');
  var show = inp.type === 'password';
  inp.type = show ? 'text' : 'password';
  btn.textContent = show ? '隐藏' : '显示';
}
function listAdd(btn) {
  var box = btn.closest('[data-list]');
  var t = box.dataset.itemType || 'text';
  var div = document.createElement('div');
  div.className = 'cf-rowitem';
  div.innerHTML = listItemControl({ item_type: t, options: [] }, '', box.dataset.list + '[new]')
    + '<button class="mini" type="button" onclick="cfgListDel(this)">删除</button>';
  box.insertBefore(div, box.lastElementChild);
}
function listDel(btn) { btn.closest('.cf-rowitem').remove(); }
function refreshGroups() {
  if (typeof global.CFGCTL.onGroupRefresh === 'function') global.CFGCTL.onGroupRefresh();
}

/* ---------------------------------------------------------------- 取值 */
function readOne(el) {
  if (el.type === 'checkbox') return el.checked;
  if (el.type === 'number') return el.value === '' ? 0 : Number(el.value);
  return el.value;
}
/* 收集表单 → 提交对象（键 = 字段名；未被控件接管的配置按**扁平路径**原样带回）*/
function collect(root, payload) {
  var out = {}, handled = {};
  root.querySelectorAll('[data-k]').forEach(function (el) {
    out[el.dataset.k] = readOne(el); handled[el.dataset.k] = 1;
  });
  root.querySelectorAll('[data-multi]').forEach(function (el) {
    var k = el.dataset.multi;
    if (!out[k]) out[k] = [];
    handled[k] = 1;
    if (el.checked) out[k].push(el.value);
  });
  root.querySelectorAll('[data-multi-select]').forEach(function (el) {
    out[el.dataset.multiSelect] = Array.from(el.selectedOptions).map(function (o) { return o.value; });
    handled[el.dataset.multiSelect] = 1;
  });
  root.querySelectorAll('[data-multi-text]').forEach(function (el) {
    out[el.dataset.multiText] = String(el.value || '').split(/[,，\s]+/).filter(Boolean);
    handled[el.dataset.multiText] = 1;
  });
  root.querySelectorAll('[data-list]').forEach(function (box) {
    out[box.dataset.list] = Array.from(box.querySelectorAll('.cf-rowitem')).map(function (row) {
      var el = row.querySelector('[data-item]');
      if (!el) return '';
      return el.type === 'checkbox' ? el.checked : readOne(el);
    });
    handled[box.dataset.list] = 1;
  });
  /* 表单没渲染到的配置原样带回。必须用扁平路径 + 跳过控件的整段父级：
     否则嵌套配置（settings/commands/…）会把整段旧字典写回去，**覆盖刚改的值**。 */
  var paths = ((payload && payload.fields) || []).map(fieldPath);
  var flat = (payload && payload.flat) || {};
  Object.keys(flat).forEach(function (k) {
    if (handled[k]) return;
    for (var i = 0; i < paths.length; i++) {
      var p = paths[i];
      if (p === k || p.indexOf(k + '.') === 0) return;   // 已被控件接管，或 k 是它的父级段
    }
    out[k] = flat[k];
  });
  return out;
}

/* ---------------------------------------------------------------- 错误标注 */
function clearErrors(root) {
  root.querySelectorAll('.cf-bad').forEach(function (el) { el.classList.remove('cf-bad'); });
  root.querySelectorAll('.cf-err').forEach(function (el) { el.hidden = true; });
}
function fieldError(root, name, msg) {
  var box = root.querySelector('[data-field="' + (global.CSS && CSS.escape ? CSS.escape(name) : name) + '"]');
  if (!box) return;
  box.classList.toggle('cf-bad', !!msg);
  var e = box.querySelector('.cf-err');
  if (e) { e.hidden = !msg; e.textContent = msg || ''; }
}

global.CFGCTL = {
  esc: esc, getPath: getPath, setPath: setPath, fieldPath: fieldPath,
  optHtml: optHtml, control: control, listItemControl: listItemControl,
  listHtml: listHtml, fieldHtml: fieldHtml, renderForm: renderForm,
  bindLive: bindLive, peek: peek, listAdd: listAdd, listDel: listDel,
  refreshGroups: refreshGroups, readOne: readOne, collect: collect,
  clearErrors: clearErrors, fieldError: fieldError,
  /* 群列表由外壳注入：provider() -> {groups:[], error:''}；onGroupRefresh 由外壳实现 */
  groupSelectProvider: null, onGroupRefresh: null
};
/* 模板里用的是内联 onclick，保留这三个全局名（两端的老调用点都不用改） */
global.cfgPeek = peek;
global.cfgListAdd = listAdd;
global.cfgListDel = listDel;
})(window);

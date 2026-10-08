import os
import sys
import json
import signal
import subprocess
import time
import hashlib
from functools import wraps
from flask import Flask, jsonify, request, send_from_directory, session

# ====== 路径 ======
STATIC_DIR = os.path.dirname(os.path.abspath(__file__))
# 添加项目根目录到 Python 路径（使 import utils.* 可用）
_PROJECT_ROOT = os.path.dirname(STATIC_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# 面板自身目录（config_schema / ui_pages 与 api.py 同目录）
if STATIC_DIR not in sys.path:
    sys.path.insert(0, STATIC_DIR)
import config_schema as _cs      # 插件配置 schema（与 Windows 端 AsterCore 同一份实现）
import ui_pages as _ui           # 面板页面片段（页面内容由后端生成，前端只挂载）

# ====== 鉴权配置 ======
CONFIG_PATH = '/etc/mybot-panel/config.json'

def load_auth_config():
    try:
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    except Exception as e:
        print('加载配置文件失败:', e)
        return {}

auth_config = load_auth_config()
PASSWORDS = auth_config.get('passwords', {})

app = Flask(__name__, static_folder=STATIC_DIR)
app.secret_key = auth_config.get('secret_key', os.urandom(24).hex())

@app.after_request
def add_cache_headers(resp):
    """缓存策略：
    - 静态页面框架（HTML/CSS/JS）：允许浏览器缓存（刷新秒开，改版后强刷生效）
    - API 数据接口：禁止缓存（内容每次实时获取）
    """
    if request.path.startswith('/api/'):
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
    else:
        # 静态框架：浏览器缓存（5 分钟，刷新秒开；改版后 Ctrl+F5 强刷生效）
        resp.headers['Cache-Control'] = 'public, max-age=300'
    return resp
app.permanent_session_lifetime = 86400  # 24小时过期

# ====== 登录限流 ======
LOGIN_ATTEMPTS = {}  # ip -> [timestamp, ...]
MAX_LOGIN_ATTEMPTS = 5
LOGIN_BLOCK_SECONDS = 900  # 15分钟

def _check_login_rate_limit(ip):
    now = time.time()
    if ip in LOGIN_ATTEMPTS:
        # 清理过期记录
        LOGIN_ATTEMPTS[ip] = [t for t in LOGIN_ATTEMPTS[ip] if now - t < LOGIN_BLOCK_SECONDS]
        if len(LOGIN_ATTEMPTS[ip]) >= MAX_LOGIN_ATTEMPTS:
            return False, int(LOGIN_BLOCK_SECONDS - (now - LOGIN_ATTEMPTS[ip][0]))
    return True, 0

def _record_login_attempt(ip, success):
    if success:
        LOGIN_ATTEMPTS.pop(ip, None)
    else:
        LOGIN_ATTEMPTS.setdefault(ip, [])
        LOGIN_ATTEMPTS[ip].append(time.time())

# ====== CSRF 防护 ======
def _check_csrf():
    """检查请求来源，防止跨站请求伪造"""
    # AJAX 请求必须带 X-Requested-With 头
    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        # 对 POST/PUT/DELETE 请求强制检查
        if request.method in ('POST', 'PUT', 'DELETE'):
            # 允许同源请求（从页面发起的表单提交）
            origin = request.headers.get('Origin', '')
            referer = request.headers.get('Referer', '')
            allowed = False
            if origin and 'xn--kivt1l.online' in origin:
                allowed = True
            if referer and 'xn--kivt1l.online' in referer:
                allowed = True
            if not allowed:
                return False
    return True

# ====== 鉴权装饰器 ======
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('authenticated'):
            return jsonify({'error': '未登录', 'need_login': True}), 401
        # 会话自动续期
        session.permanent = True
        session.modified = True

        if not _check_csrf():
            return jsonify({'error': '请求来源无效，拒绝操作'}), 403
        return f(*args, **kwargs)
    return decorated

# install.sh 的实例注册/目录规范（脚本目录下 instances/）
# 新布局：<项目根>/instances/<QQ>（项目） + <项目根>/instances/registry/<QQ>.sh（注册）
# 旧布局（兼容）：/tmp/napbot_instances/<QQ>.sh + /root/mybot_<QQ>
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTANCES_ROOT = os.path.join(_BASE_DIR, 'instances')
INSTANCES_DIR = os.path.join(INSTANCES_ROOT, 'registry')
LEGACY_INSTANCES_DIR = "/tmp/napbot_instances"
INST_PROJECT_PREFIX = "/root/mybot_"

# 实例动态发现：仓库不内置任何具体实例（依星/羽笙等），
# 由 install.sh 部署时创建 instances/<QQ> 注册，或本地 registry 文件注册；
# 没有任何实例时提供示例实例（123456）供演示
BOTS = {}
CURRENT_BOT = None

# 示例实例（仅当未发现任何实例时展示）
EXAMPLE_BOT = {
    'name': '示例机器人',
    'screen': 'bot_123456',
    'dir': os.path.join(INSTANCES_ROOT, '123456'),
    'qq': '123456',
    'master': '',
    'napcat_port': 3000,
    'example': True,
}


def _parse_napcat_port(http_url):
    """从 INST_HTTP 解析 NapCat HTTP 端口（http://127.0.0.1:3000 → 3000）"""
    try:
        from urllib.parse import urlparse
        return urlparse(http_url).port or 3000
    except Exception:
        return 3000


def _read_master_qq(project_dir):
    """读取实例项目 config.json 的 MASTER_QQ"""
    cfg = read_json(os.path.join(project_dir, 'config.json'))
    ml = cfg.get('MASTER_QQ', '')
    if isinstance(ml, list):
        return '、'.join(str(m) for m in ml)
    return str(ml or '')


def discover_instances() -> dict:
    """动态发现所有已部署实例，返回 {编号: {name, screen, dir, qq, master, napcat_port}}

    实例来源（去重合并，按 dir 判重）：
    1. BOTS 硬编码（本地生产实例，如 依星/羽笙）
    2. install.sh 注册文件 /tmp/napbot_instances/<QQ>.sh
    3. install.sh 项目目录规范 /root/mybot_<QQ>
    """
    result = {}
    seen_dirs = set()

    def _add(num, inst):
        d = inst.get('dir', '')
        if not d or d in seen_dirs:
            return
        seen_dirs.add(d)
        result[num] = inst

    # 1. 硬编码实例
    for n, b in BOTS.items():
        _add(n, dict(b))

    # 2. install.sh 注册文件（新布局 + 旧布局兼容）
    for reg_dir in (INSTANCES_DIR, LEGACY_INSTANCES_DIR):
        if not os.path.isdir(reg_dir):
            continue
        for fname in sorted(os.listdir(reg_dir)):
            if not fname.endswith('.sh'):
                continue
            qq = fname[:-3]
            if not qq.isdigit():
                continue
            try:
                env = {}
                with open(os.path.join(reg_dir, fname), 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('INST_') and '=' in line:
                            k, _, v = line.partition('=')
                            env[k.strip()] = v.strip().strip('"').strip("'")
            except Exception:
                continue
            project_dir = env.get('INST_PROJECT_DIR', f"{INSTANCES_ROOT}/{qq}")
            if not os.path.isdir(project_dir):
                continue
            if project_dir in seen_dirs:
                continue
            seen_dirs.add(project_dir)
            result[int(qq) if qq.isdigit() else len(result) + 100] = {
                'name': env.get('INST_BOT_NAME') or f"Bot_{qq}",
                'screen': env.get('INST_SCREEN') or f"bot_{qq}",
                'dir': project_dir,
                'qq': qq,
                'master': _read_master_qq(project_dir),
                'napcat_port': _parse_napcat_port(env.get('INST_HTTP', '')),
                'container': env.get('INST_CONTAINER') or f"napcat_{qq}",
                # 可选：NapCat WebUI 访问路径（供面板"打开 NapCat 面板"跳转用）
                'napcat_webui': env.get('INST_NAPCAT_WEBUI', ''),
            }

    # 3. install.sh 项目目录规范（新布局 instances/<QQ> + 旧布局 /root/mybot_<QQ>）
    import glob
    dirs = sorted(glob.glob(os.path.join(INSTANCES_ROOT, '*'))) + sorted(glob.glob(f"{INST_PROJECT_PREFIX}*"))
    for d in dirs:
        if not os.path.isdir(d) or not os.path.exists(os.path.join(d, 'main.py')):
            continue
        if d.startswith(INSTANCES_ROOT + os.sep):
            qq = os.path.basename(d)
        elif d.startswith(INST_PROJECT_PREFIX):
            qq = d[len(INST_PROJECT_PREFIX):]
        else:
            continue
        if not qq.isdigit() or d in seen_dirs:
            continue
        _add(int(qq), {
            'name': f"Bot_{qq}",
            'screen': f"bot_{qq}",
            'dir': d,
            'qq': qq,
            'master': _read_master_qq(d),
            'napcat_port': 3000,
            'container': f"napcat_{qq}",
        })

    # 未发现任何实例时，展示示例实例（123456）
    if not result:
        result[123456] = dict(EXAMPLE_BOT)

    return result


def _container_for(n):
    """获取实例的 NapCat 容器名（BOTS 动态发现，编号为 QQ 号）"""
    b = BOTS.get(n, {})
    c = b.get('container')
    if c:
        return c
    qq = b.get('qq') or str(n)
    return f"napcat_{qq}"


def _napcat_http_info(b):
    """读取实例 config.json 里的 NapCat HTTP 地址与令牌（探测账号在线状态用）"""
    cfg = read_json(os.path.join(b.get('dir', ''), 'config.json'))
    http = cfg.get('NAPCAT_HTTP') or f"http://127.0.0.1:{b.get('napcat_port', 3000)}"
    return str(http).rstrip('/'), str(cfg.get('ACCESS_TOKEN') or '')


def _napcat_online(b):
    """查询 NapCat 的**账号在线状态**（容器在跑 ≠ QQ 在线，必须问 NapCat 本身）

    返回 {online: True/False/None, login: {...}/None, error: str}
    online=None 表示探测失败（接口不可用/超时/未安装 requests），前端按"未知"展示。
    """
    http, token = _napcat_http_info(b)
    out = {'online': None, 'login': None, 'error': ''}
    if not http:
        out['error'] = '未配置 NapCat 地址'
        return out
    try:
        import requests
    except ImportError:
        out['error'] = 'requests 未安装'
        return out
    params = {'access_token': token} if token else {}
    try:
        r = requests.post(f"{http}/get_status", params=params, timeout=5)
        j = r.json() if r.status_code == 200 else {}
        if j.get('status') == 'ok':
            out['online'] = bool((j.get('data') or {}).get('online'))
        else:
            out['error'] = str(j.get('message') or j.get('wording') or f"HTTP {r.status_code}")[:120]
    except Exception as e:
        # 连不上 NapCat（容器未就绪/进程未起/端口不通）→ 账号必然不可用，按离线处理，
        # 前端会显示"离线"并给出重启按钮（比"未知"更贴近实际可用性）
        out['online'] = False
        out['error'] = 'NapCat 接口无响应: ' + str(e)[:80]
    # 登录身份（登录态仍有效时可取，用于展示昵称；掉线时可能取不到）
    try:
        r = requests.post(f"{http}/get_login_info", params=params, timeout=5)
        j = r.json() if r.status_code == 200 else {}
        if j.get('status') == 'ok':
            out['login'] = j.get('data') or None
    except Exception:
        pass
    return out


def _napcat_webui(b):
    """该实例的 NapCat WebUI 地址（来自实例注册文件的 INST_NAPCAT_WEBUI）

    约定用**同源相对路径**（如 /yixing/napcat/），由 Nginx 反代到各容器的 6099；
    未配置则返回空串，前端不显示跳转按钮。
    """
    return str(b.get('napcat_webui') or '')


def _systemd_unit_for(b):
    """该实例对应的 systemd 单元名（按 QQ 派生；存在则由 systemd 托管）"""
    return f"mybot-bot-{b.get('qq')}.service"


def _unit_exists(unit):
    try:
        r = subprocess.run(f"systemctl list-unit-files {unit} --no-legend",
                           shell=True, capture_output=True, text=True, timeout=5)
        return bool((r.stdout or '').strip())
    except Exception:
        return False


def _bot_proc(b):
    """探测 bot 主进程（python3 main.py --bot-name ... --bot-qq ...）的真实状态。
    返回 (running, pid, uptime)。基于进程表而非 screen 会话：
    screen 窗口挂着不代表 bot 进程存活（进程退出/崩溃时 screen 仍在）。"""
    qq = b.get('qq')
    try:
        r = subprocess.run(
            f"ps -eo pid,etimes,args | grep 'main.py --bot-name' | grep -w '{qq}' | grep -v grep | grep -v SCREEN | head -1",
            shell=True, capture_output=True, text=True, timeout=5)
        parts = r.stdout.strip().split()
        if parts:
            pid = parts[0]
            try:
                return True, pid, int(parts[1])
            except (ValueError, IndexError):
                return True, pid, 0
    except Exception:
        pass
    return False, '', 0


def _bot_info(b):
    """Bot 概览数据（页面片段与 /info 接口共用同一份口径）"""
    running, pid, uptime = _bot_proc(b)
    return {'success': True, 'name': b['name'], 'qq': b['qq'], 'master': b['master'],
            'dir': b['dir'], 'screen': b['screen'], 'running': running,
            'status': 'running' if running else 'stopped', 'pid': pid, 'uptime': uptime}


def _toggles_payload(b, plugin_keys):
    """群组开关矩阵 + 群信息（/plugins 与页面片段 groups 共用）"""
    import utils.plugin_toggle as _pt
    group_info = {}
    try:
        import requests as _req
        bc = read_json(os.path.join(b['dir'], 'config.json'))
        nh = bc.get('NAPCAT_HTTP', 'http://127.0.0.1:3000')
        tk = bc.get('ACCESS_TOKEN', '')
        gl = _req.get(f'{nh}/get_group_list', params={'access_token': tk}, timeout=5).json()
        if gl.get('status') == 'ok' and gl.get('data'):
            for g in gl['data']:
                gid = str(g.get('group_id', ''))
                group_info[gid] = {'name': g.get('group_name') or '未知群',
                                   'avatar': f'https://p.qlogo.cn/gh/{gid}/{gid}/'}
    except Exception as e:
        print(f'[API] 获取群列表失败: {e}')
    tg = _pt.get_toggles_matrix(os.path.join(b['dir'], 'data'), list(plugin_keys))
    all_groups = sorted(set(tg['groups'] + sorted(group_info.keys())))
    tg['groups'] = all_groups
    tg['toggles'] = {gid: tg['toggles'].get(gid, {p: False for p in tg['plugins']}) for gid in all_groups}
    tg['groupInfo'] = group_info
    tg['_pluginMeta'] = {k: {'name_cn': v['name_cn'], 'name_en': v['name_en']}
                         for k, v in _pt.get_plugin_meta(None, os.path.join(b['dir'], 'plugins')).items()}
    return tg


def refresh_bots():
    """启动时重建 BOTS：动态发现所有实例（保留现有引用兼容）"""
    global BOTS
    discovered = discover_instances()
    if discovered:
        BOTS = discovered


@app.route('/api/bots')
def api_bots():
    """返回全部实例列表（供门户/面板切换）"""
    items = []
    for n, b in BOTS.items():
        running, pid, uptime = _bot_proc(b)
        items.append({
            'num': n,
            'name': b['name'],
            'qq': b['qq'],
            'dir': b['dir'],
            'screen': b['screen'],
            'running': running,
            'current': (CURRENT_BOT == n),
        })
    return jsonify({'bots': items})

def read_json(path):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}

def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # 原子写入：先写临时文件再替换，避免插件热更新读到半截文件
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

# ====== 插件配置声明（schema）======
# 面板不再靠"猜"配置 JSON 的形状：可配置项**由插件自己声明**（模块级 __config_schema__），
# 面板只实现「字段类型 → 控件」这套映射，所以加插件不用改面板。

def _plugin_source_path(pd, meta):
    """插件源码路径（按 name_en 推导，与主程序的模块名一致）"""
    name_en = (meta or {}).get('name_en') or ''
    p = os.path.join(pd, name_en + '.py') if name_en else ''
    return p if p and os.path.exists(p) else ''


def _read_declared_schema(src_path):
    """读插件源码里的模块级 __config_schema__。

    **用 ast 解析，绝不 import**：老插件导入期有副作用（video_parser 会注册解析器、
    起线程/子进程），面板进程里 import 它们是事故。
    返回 (声明 dict|None, 来源, 错误列表)
    """
    if not src_path:
        return None, '', []
    try:
        with open(src_path, 'r', encoding='utf-8') as fh:
            src = fh.read()
    except Exception as e:
        return None, '', [f'读不到插件源码: {e}']
    try:
        import ast as _ast
        tree = _ast.parse(src)
    except SyntaxError as e:
        return None, '', [f'插件源码语法错误: {e}']
    for node in tree.body:
        targets = list(getattr(node, 'targets', []) or [])
        if getattr(node, 'target', None) is not None:
            targets.append(node.target)
        for t in targets:
            if isinstance(t, getattr(__import__('ast'), 'Name')) and t.id == '__config_schema__':
                try:
                    import ast as _ast2
                    val = _ast2.literal_eval(node.value)
                except Exception as e:
                    return None, '__config_schema__', [f'__config_schema__ 必须是字面量字典: {e}']
                if not isinstance(val, dict):
                    return None, '__config_schema__', ['__config_schema__ 必须是 dict']
                return val, '__config_schema__', []
    return None, '', []


def _plugin_cfg_payload(b, meta, pkey=None):
    """一个插件的完整配置数据：声明字段 + 当前值 + 是否声明 + schema 自身的问题"""
    dd = os.path.join(b['dir'], 'data')
    pd = os.path.join(b['dir'], 'plugins')
    cf = (meta or {}).get('config_file') or ''
    cfg = read_json(os.path.join(dd, cf)) if cf else {}
    declared, declared_by, errs = _read_declared_schema(_plugin_source_path(pd, meta))
    payload = _cs.build_payload(declared, cfg)
    payload['schema_errors'] = list(payload.get('schema_errors') or []) + list(errs or [])
    payload['declared_by'] = declared_by
    payload['plugin'] = pkey or (meta or {}).get('name_en') or ''
    payload['plugin_name'] = (meta or {}).get('name_cn') or payload['plugin']
    payload['config_file'] = cf
    return payload


def _legacy_merge(merged, cfg):
    """未声明 schema 的老插件：沿用历史前缀解码（cmd_/msg_/setting_/cfg_/admins），
    并支持点号路径 —— 与 build_payload 的 flat 视图一致，语义与改动前完全一样。"""
    for k, v in (cfg or {}).items():
        if k == 'admins':
            merged['admins'] = v
        elif k.startswith('cmd_'):
            merged.setdefault('commands', {})[k.replace('cmd_', '', 1)] = v
        elif k.startswith('msg_'):
            merged.setdefault('messages', {})[k.replace('msg_', '', 1)] = v
        elif k.startswith('setting_'):
            key = k.replace('setting_', '', 1)
            old_val = merged.get('settings', {}).get(key)
            # 布尔型设置（开关）：统一转 bool，保证保存后重载仍是开关
            if isinstance(old_val, bool) or str(v).lower() in ('true', 'false'):
                v = (str(v).lower() == 'true')
            elif isinstance(v, str) and v.replace('.', '', 1).replace('-', '', 1).isdigit():
                v2 = float(v) if '.' in v else int(v)
                v = type(old_val)(v2) if isinstance(old_val, (int, float)) else v2
            merged.setdefault('settings', {})[key] = v
        elif k.startswith('cfg_'):
            key = k.replace('cfg_', '', 1)
            if isinstance(v, str) and v.lower() in ('true', 'false'):
                v = (v.lower() == 'true')
            merged[key] = v
        elif '.' in k:
            _cs.set_path(merged, k, v)      # 面板回传的未声明键（扁平路径）
        else:
            merged[k] = v
    return merged


def build_fields_from_cfg(cfg, prefix='cmd'):
    fields = []
    cmds = cfg.get('commands', {})
    replies = cfg.get('replies', {})
    if not cmds and not replies:
        return fields
    for k, v in cmds.items():
        fields.append({'k': prefix + '_cmd_' + k, 'l': '命令「' + k + '」', 't': 'text', 'v': v, 'cfg_file': 'plugins_config.json'})
    for k, v in replies.items():
        field_type = 'textarea' if '{' in v and len(v) > 30 else 'text'
        fields.append({'k': prefix + '_rep_' + k, 'l': '回复「' + k + '」', 't': field_type, 'v': v})
    return fields

# ====== 鉴权接口 ======
def _verify_password(pwd):
    """验证密码，支持明文和MD5两种配置格式
    返回 (成功, bot_name) 或 (False, None)
    """
    pwd_md5 = hashlib.md5(pwd.encode()).hexdigest()
    # 先试明文匹配
    if pwd in PASSWORDS:
        return True, PASSWORDS[pwd]
    # 再试MD5匹配
    if pwd_md5 in PASSWORDS:
        return True, PASSWORDS[pwd_md5]
    return False, None

def _bot_path(bot_name):
    """通用面板路径（仓库不内置具体实例页面）"""
    return 'panel'

@app.route('/api/portal-login', methods=['POST'])
def portal_login():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': '请输入密码'}), 200
    pwd = data.get('password', '').strip()

    # 限流检查
    client_ip = request.remote_addr or '127.0.0.1'
    allowed, wait = _check_login_rate_limit(client_ip)
    if not allowed:
        return jsonify({'success': False, 'message': f'登录尝试过于频繁，请 {wait} 秒后重试'}), 429

    ok, bot_name = _verify_password(pwd)
    if ok:
        _record_login_attempt(client_ip, success=True)
        session.clear()
        session.permanent = True
        session['authenticated'] = True
        session['bot_name'] = bot_name
        # 找到密码对应的实例编号（按名称匹配 BOTS；匹配不到则用当前实例）
        num = None
        for n, b in BOTS.items():
            if b.get('name') == bot_name:
                num = n
                break
        if num is None:
            num = CURRENT_BOT
        path = _bot_path(bot_name)
        return jsonify({'success': True, 'message': f'正在进入{bot_name}面板',
                        'redirect': f'/{path}/?bot={num}'}), 200
    else:
        _record_login_attempt(client_ip, success=False)
        time.sleep(1)  # 防时序攻击
        return jsonify({'success': False, 'message': '密码错误'}), 200

@app.route('/api/check-auth')
def check_auth():
    if session.get('authenticated'):
        return jsonify({'authenticated': True, 'bot': session.get('bot_name')})
    return jsonify({'authenticated': False}), 200

@app.route('/api/logout', methods=['POST'])
def do_logout():
    session.clear()
    return jsonify({'success': True, 'message': '已退出登录'})

# ====== 管理接口（需登录） ======
@app.route('/api/status')
@login_required
def api_status():
    result = {}
    for n, bot in BOTS.items():
        running, pid, uptime = _bot_proc(bot)
        result[n] = {'running': running, 'name': bot['name'], 'status': 'running' if running else 'stopped',
                     'pid': pid, 'uptime': uptime}
    return jsonify({'success': True, 'bot1': result.get(1), 'bot2': result.get(2)})

@app.route('/api/bot/<int:n>/info')
@login_required
def bot_info(n):
    if n not in BOTS: return jsonify({'error': '无效编号'}), 404
    b = BOTS[n]
    running, pid, uptime = _bot_proc(b)
    return jsonify({'success': True, 'name': b['name'], 'qq': b['qq'], 'master': b['master'],
                    'dir': b['dir'], 'screen': b['screen'], 'running': running,
                    'status': 'running' if running else 'stopped',
                    'napcat_port': b['napcat_port'], 'pid': pid, 'uptime': uptime,
                    'container': _container_for(n)})

@app.route('/api/bot/<int:n>/log')
@login_required
def bot_log(n):
    if n not in BOTS: return jsonify({'error': '无效编号'}), 404
    b = BOTS[n]
    log_file = os.path.join(b['dir'], 'runtime.log')
    if not os.path.exists(log_file):
        log_file = os.path.join(b['dir'], 'log.txt')
    # 行数参数（默认 100，上限 1000）
    try:
        n_lines = int(request.args.get('lines', 100))
    except (TypeError, ValueError):
        n_lines = 100
    n_lines = min(max(n_lines, 20), 1000)
    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
            all_lines = f.readlines()
            return jsonify({'log': ''.join(all_lines[-n_lines:]), 'total': len(all_lines)})
    return jsonify({'log': '暂无日志', 'total': 0})

@app.route('/api/bot/<int:n>/napcat-log')
@login_required
def bot_napcat_log(n):
    if n not in BOTS: return jsonify({'error': '无效编号'}), 404
    container = _container_for(n)
    try:
        try:
            n_lines = int(request.args.get('lines', 30))
        except (TypeError, ValueError):
            n_lines = 30
        n_lines = min(max(n_lines, 20), 1000)
        r = subprocess.run(f"docker logs {container} --tail {n_lines} 2>&1", shell=True, capture_output=True, text=True, timeout=8)
        return jsonify({'log': r.stdout or '容器日志为空'})
    except Exception as e:
        return jsonify({'log': '获取失败: ' + str(e)})

@app.route('/api/bot/<int:n>/napcat-status')
@login_required
def napcat_status(n):
    """NapCat 状态 = **账号在线状态**（不再检测容器状态）

    容器在跑不代表账号可用：NTQQ 掉线 / 登录态失效时容器仍是 running，
    但机器人收不到任何消息，所以以 NapCat 上报的账号在线状态为准。
    返回：{online: True/False/None, login: {user_id,nickname}/None, error}
    """
    if n not in BOTS: return jsonify({'error': '无效编号'}), 404
    b = BOTS[n]
    info = _napcat_online(b)
    return jsonify({'online': info.get('online'),
                    'login': info.get('login'),
                    'error': info.get('error') or '',
                    'qq': b.get('qq'),
                    'name': b.get('name'),
                    'webui': _napcat_webui(b)})

@app.route('/api/bot/<int:n>/napcat-qr')
@login_required
def napcat_qr(n):
    if n not in BOTS: return jsonify({'error': '无效编号'}), 404
    container = _container_for(n)
    try:
        r = subprocess.run("docker exec " + container + " cat /app/napcat/cache/qrcode.png 2>/dev/null", shell=True, capture_output=True, timeout=10)
        if r.returncode != 0 or not r.stdout:
            return jsonify({'qr': None, 'error': '暂无二维码，NapCat可能未启动或未生成二维码'})
        import base64
        qr_b64 = base64.b64encode(r.stdout).decode()
        return jsonify({'qr': qr_b64, 'container': container})
    except Exception as e:
        return jsonify({'qr': None, 'error': str(e)})


@app.route('/api/bot/<int:n>/napcat-restart', methods=['POST'])
@login_required
def napcat_restart(n):
    """重启 NapCat 容器（账号离线时的恢复手段）

    离线两类常见原因：① NTQQ 连接坏了 → 重启即恢复；
    ② 登录态失效 → 重启后转等待扫码，需配合「查看二维码」。
    重启后回读一次在线状态，把结果与提示一并返回给前端。
    """
    if n not in BOTS: return jsonify({'error': '无效编号'}), 404
    b = BOTS[n]
    container = _container_for(n)
    try:
        r = subprocess.run("docker restart " + container, shell=True,
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            msg = (r.stderr or r.stdout or '').strip() or 'docker restart 失败'
            return jsonify({'success': False, 'message': 'NapCat 重启失败: ' + msg})
        time.sleep(3)
        info = _napcat_online(b)
        if info.get('online'):
            return jsonify({'success': True, 'online': True,
                            'message': f"{b['name']} NapCat 已重启，账号已在线"})
        return jsonify({'success': True, 'online': False,
                        'message': f"{b['name']} NapCat 已重启，账号仍未在线"
                                   "（登录态可能已失效，请点「查看二维码」扫码登录）"})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bot/<int:n>/<action>', methods=['POST'])
@login_required
def bot_action(n, action):
    """Bot 启停/重启：直接用 screen 操作（BOTS 编号为动态 QQ 号，
    不依赖 bot 命令的固定 1/2 编号，任何实例通用）"""
    if n not in BOTS: return jsonify({'error': '无效编号'}), 404
    b = BOTS[n]
    if action not in ('stop', 'start', 'restart'):
        return jsonify({'error': '未知操作'}), 400
    # 若该实例已交给 systemd 托管（mybot-bot-<QQ>.service），必须用 systemctl 操作：
    # 否则 screen 方式会再起一个重复实例（同一账号双开，消息会重复回复）
    unit = _systemd_unit_for(b)
    if _unit_exists(unit):
        try:
            cmd = {'stop': 'systemctl stop ' + unit,
                   'start': 'systemctl start ' + unit,
                   'restart': 'systemctl restart ' + unit}[action]
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                msg = (r.stderr or r.stdout or '').strip() or 'systemctl 执行失败'
                return jsonify({'success': False, 'message': f"{b['name']} {action} 失败: {msg}"})
            time.sleep(1.5)
            running, pid, _ = _bot_proc(b)
            if action in ('start', 'restart') and not running:
                return jsonify({'success': False,
                                'message': f"{b['name']} {action} 失败: systemd 未拉起进程"})
            return jsonify({'success': True,
                            'message': f"{b['name']} {action} 完成（systemd 托管）"})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    sn = b['screen']
    # 看门狗 screen 名：本地 bot→watchdog1、bot2→watchdog2，动态实例用 watchdog_<QQ>
    if sn == 'bot':
        wsn = 'watchdog1'
    elif sn == 'bot2':
        wsn = 'watchdog2'
    else:
        wsn = f"watchdog_{b['qq']}"
    try:
        if action in ('stop', 'restart'):
            # 注意：screen -S 是前缀匹配！'-S bot' 会同时命中 bot2，
            # 'watchdog1' 会命中 watchdog2。必须先查精确会话名（PID.name）再 quit
            for name in (sn, wsn):
                _quit_screen_exact(name)
        if action in ('start', 'restart'):
            cmd = f"cd {b['dir']} && screen -dmS {sn} python3 main.py --bot-name '{b['name']}' --bot-qq {b['qq']}"
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            time.sleep(1.5)
            # 校验启动是否真正生效（screen 静默失败时返回码可能为 0，需检查进程）
            running, pid, _ = _bot_proc(b)
            if not running:
                msg = (r.stderr or '').strip() or 'screen 启动失败（可能权限受限）'
                return jsonify({'success': False, 'message': f"{b['name']} {action} 失败: {msg}"})
        time.sleep(1)
        return jsonify({'success': True, 'message': f"{b['name']} {action} 完成"})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _quit_screen_exact(name):
    """精确关闭指定名字的 screen 会话（按 PID.name 精确匹配，避免前缀误杀 bot2）"""
    try:
        r = subprocess.run("screen -ls", shell=True, capture_output=True, text=True, timeout=5)
        for line in r.stdout.splitlines():
            # 行格式: "12345.name\t(Detached)"
            parts = line.strip().split('\t')
            if not parts:
                continue
            session = parts[0].strip()
            if '.' not in session:
                continue
            _, sname = session.split('.', 1)
            if sname == name:
                subprocess.run(f"screen -S {session} -X quit", shell=True, timeout=10)
                print(f"[API] 已关闭 screen 会话 {session}")
    except Exception as e:
        print(f"[API] 关闭 screen {name} 失败: {e}")

# ====== 插件配置 API ======
# 常见回复模板键的中文名（Web 面板展示；插件配置 message_labels 优先）
DEFAULT_MSG_LABELS = {
    "usage": "用法提示", "busy": "繁忙提示", "querying": "查询中提示", "no_pdf": "无PDF提示",
    "send_fail": "发送失败提示", "fail": "失败提示", "timeout": "超时提示",
    "pdf_header": "PDF分享标题", "detail_header": "详情标题", "recall_notice": "撤回提醒",
    "sign_success": "签到成功", "sign_already": "今日已签到", "sign_fail": "签到失败",
    "nickname_set": "昵称设置成功", "nickname_fail": "昵称设置失败", "nickname_format_error": "昵称格式错误",
    "nickname_empty": "昵称不能为空", "praise_success": "点赞成功", "praise_already": "今日已点赞",
    "praise_fail": "点赞失败", "rank_empty": "排行榜为空", "rank_title": "排行榜标题",
    "rank_item": "排行条目", "add_step1": "添加词条-步骤1", "add_step2": "添加词条-步骤2",
    "add_step3": "添加词条-步骤3", "add_success_exact": "添加成功(精准)", "add_success_fuzzy": "添加成功(模糊)",
    "add_format_error": "添加格式错误", "add_empty": "添加内容为空", "keyword_empty": "关键词为空",
    "reply_empty": "回复为空", "mode_invalid": "模式无效", "delete_success": "删除成功",
    "delete_reply_success": "删除回复成功", "delete_not_found": "关键词不存在", "delete_idx_invalid": "序号无效",
    "delete_format_error": "删除格式错误", "wordlib_empty": "词库为空", "query_list_title": "词库列表标题",
    "query_list_item": "词库列表项", "query_detail_title": "词库详情标题", "query_detail_item": "词库详情项",
    "query_no_reply": "无回复", "encode_start": "转码开始", "encode_result": "转码结果",
    "encode_timeout": "转码超时", "delete_reply_idx_invalid": "删除回复序号无效",
    "delete_idx_must_number": "删除序号须为数字", "delete_idx_positive": "删除序号须为正数",
    "switch_glm": "切换GLM成功", "switch_gemini": "切换Gemini成功",
    "current_model": "当前模型", "history_cleared": "历史已清除", "all_history_cleared": "全部历史已清除",
    "whats_up": "打招呼", "check_image": "看图提示", "no_reply": "无回复提示",
}

# 常见参数键的中文名（Web 面板设置标签；插件配置 setting_labels 优先）
DEFAULT_SETTING_LABELS = {
    "enabled": "插件开关",
    # JM下载
    "auto_update": "自动更新jmcomic库", "update_interval_hours": "更新检查间隔(小时)",
    "send_pdf": "发送PDF", "delete_after_send": "发送后清理文件",
    "concurrent_image": "并发下载图片数", "concurrent_photo": "并发下载章节数",
    "download_dir": "下载目录", "task_timeout_seconds": "任务超时(秒)",
    "cleanup_delay_seconds": "清理延迟(秒)", "recall_enabled": "消息自动撤回",
    "recall_seconds": "前置消息撤回时间(秒)", "recall_prefix_seconds": "前置消息撤回时间(秒)",
    "recall_pdf_seconds": "PDF提醒撤回时间(秒)", "recall_file_seconds": "PDF文件撤回时间(秒)", "recall_notice": "撤回前提醒",
    "debounce_seconds": "下载防抖间隔(秒,0=关闭)",
    # 结婚
    "success_rate": "结婚成功率(%)", "divorce_cd_hours": "离婚冷却(小时)",
    # 词库
    "favor_add_min": "好感度增加下限", "favor_add_max": "好感度增加上限",
    "favor_minus_min": "好感度扣除下限", "favor_minus_max": "好感度扣除上限",
    "nickname_need_favor": "设置昵称所需好感度", "rank_top_n": "排行榜人数",
    "praise_count": "点赞次数", "encode_timeout": "转码超时(秒)",
    # 伪人
    "current_model": "当前AI模型", "split_count": "消息分段数",
    "split_delay_min": "分段最小延迟(秒)", "split_delay_max": "分段最大延迟(秒)",
    "reply_probability": "回复概率", "random_reply_probability": "随机回复概率",
    "record_group_unrelated": "记录无关群消息", "max_history": "历史消息上限",
    "context_window": "上下文窗口(条)", "temperature": "温度参数",
    "max_tokens": "最大Token数", "api_timeout": "API超时(秒)",
    "health_check_interval": "健康检查间隔(秒)", "default_persona": "默认人设(第一层,留空用内置)",
    "user_persona": "自定义人格(第二层,深度演绎)", "group_model_map": "分群模型映射",
    # 视频解析
    "max_images": "最大图片数", "auto_send_video": "自动发送视频",
    "auto_send_images": "自动发送图片", "show_source": "显示来源",
    "merge_images": "合并图片", "@_reply": "@回复",
    "douyin_cookie": "抖音Cookie", "browser_timeout": "下载超时(秒)",
    # 视频解析 - 新解析核心
    "download_retry_times": "下载重试次数", "download_max_size": "下载大小上限(MB)",
    "download_max_duration": "视频时长上限(秒)", "forward_threshold": "合并转发阈值(段数)",
    "debounce_seconds": "解析防抖间隔(秒,0=关闭)", "show_download_fail_tip": "下载失败提示",
    "audio_to_file": "音频以文件发送", "proxy": "代理地址",
    "bili_video_quality": "B站画质", "bili_video_codec": "B站编码",
    "bili_cookie": "B站Cookie(含SESSDATA,填后重启生效，绕过412风控)",
}


@app.route('/api/bot/<int:num>/plugins')
@login_required
def get_plugins(num):
    if num not in BOTS: return jsonify({'error': '无效编号'}), 404
    b = BOTS[num]
    dd = os.path.join(b['dir'], 'data')
    pd = os.path.join(b['dir'], 'plugins')
    import utils.plugin_toggle as _pt

    plugins = {}

    # 动态扫描插件目录：与主程序实际加载的插件（有 handle()）保持一致
    avail_list = list(_pt.get_available_plugins(pd))

    # 1. 插件元数据（**可配置项由插件自己声明**，见 /plugins/<key>/schema 接口；
    #    这里只给导航与概览用的轻量信息，不再猜配置 JSON 的形状）
    for pkey, meta in avail_list:
        cf = meta.get('config_file')
        decl, _dby, decl_errs = _read_declared_schema(_plugin_source_path(pd, meta))
        plugins[pkey] = {
            'name_cn': meta.get('name_cn') or pkey,
            'display': meta.get('name_cn') or pkey,
            'name_en': meta.get('name_en') or '',
            'description': meta.get('description', ''),
            'version': meta.get('version', ''),
            'author': meta.get('author', ''),
            'config_file': cf or '',
            'has_config': bool(cf and os.path.exists(os.path.join(dd, cf))),
            'declared': bool(decl),
            'declared_fields': len(decl or {}),
            'schema_errors': decl_errs,
        }

    # 2. 群组开关表格数据（helper 与页面片段共用）
    plugins['_toggles'] = _toggles_payload(b, [k for k, _ in avail_list])

    safe_bot = {k: v for k, v in b.items() if k not in ('dir', 'screen', 'napcat_port')}
    return jsonify({'bot': safe_bot, 'plugins': plugins})


def _notify_bot_reload(qq):
    """Web 保存配置后，通知运行中的 bot 进程（SIGUSR1）立即重载配置"""
    try:
        r = subprocess.run(
            f"ps -eo pid,args | grep 'python3 main.py --bot-name' | grep -w '{qq}' | grep -v grep | grep -v SCREEN | awk '{{print $1}}'",
            shell=True, capture_output=True, text=True, timeout=5)
        pids = [p for p in r.stdout.strip().split('\n') if p]
        for pid in pids:
            os.kill(int(pid), signal.SIGUSR1)
        if pids:
            print(f"[API] 已通知 bot {qq} (PID {','.join(pids)}) 重载配置")
        else:
            print(f"[API] 未找到 bot {qq} 进程，跳过重载通知")
    except Exception as e:
        print(f"[API] 通知 bot 重载失败: {e}")


@app.route('/api/bot/<int:num>/plugins/<pkey>/schema')
@login_required
def get_plugin_schema(num, pkey):
    """插件可配置项声明（面板据此渲染表单）。

    没有声明的插件返回按当前值**推断**的字段（declared=false）：面板会注明
    "自动推断"，并永远保留 JSON 原文兜底 —— 不会出现"空页面"。
    """
    if num not in BOTS: return jsonify({'ok': False, 'error': '无效编号'}), 404
    b = BOTS[num]
    pd = os.path.join(b['dir'], 'plugins')
    import utils.plugin_toggle as _pt
    meta = _pt.get_plugin_meta(pkey, pd)
    if not meta:
        return jsonify({'ok': False, 'error': f'未知插件: {pkey}'}), 404
    return jsonify({'ok': True, 'data': _plugin_cfg_payload(b, meta, pkey)})


def _page_ctx(b, num, page):
    """页面片段需要的上下文；只取该页真正要用的东西（少一次请求就快一点）"""
    pd = os.path.join(b['dir'], 'plugins')
    dd = os.path.join(b['dir'], 'data')
    import utils.plugin_toggle as _pt
    avail = list(_pt.get_available_plugins(pd))
    ctx = {'bot_num': num, 'bot': {k: v for k, v in b.items() if k != 'dir'}}
    if page in ('dashboard', 'manage'):
        ctx['info'] = _bot_info(b)
        ctx['napcat'] = _napcat_online(b)
        ctx['napcat']['webui'] = _napcat_webui(b)
    if page == 'dashboard':
        ctx['plugins'] = [{'key': k, 'name_cn': m.get('name_cn'), 'name_en': m.get('name_en'),
                           'declared': bool(_read_declared_schema(_plugin_source_path(pd, m))[0])}
                          for k, m in avail]
        tg = _toggles_payload(b, [k for k, _ in avail])
        ctx['group_count'] = len(tg.get('groups') or [])
    if page == 'groups':
        ctx['toggles'] = _toggles_payload(b, [k for k, _ in avail])
    if page == 'config':
        pkey = request.args.get('plugin') or ''
        if not pkey and avail:
            pkey = avail[0][0]
        meta = _pt.get_plugin_meta(pkey, pd) if pkey else None
        ctx['plugin_key'] = pkey
        ctx['plugin_name'] = (meta or {}).get('name_cn') or pkey
    return ctx


@app.route('/api/bot/<int:num>/ui/page/<page>')
@login_required
def ui_page(num, page):
    """页面内容片段。

    框架（web/panel/index.html）是静态文件、浏览器直接缓存，首屏快；
    页面内容统一由后端生成（web/ui_pages.py），前端只挂载 + 事件委托。
    """
    if num not in BOTS: return jsonify({'ok': False, 'error': '无效编号'}), 404
    if page not in _ui.PAGES:
        return jsonify({'ok': False, 'error': f'未知页面: {page}'}), 404
    return jsonify({'ok': True, 'data': _ui.render_page(page, _page_ctx(BOTS[num], num, page))})


@app.route('/api/bot/<int:num>/ui/status')
@login_required
def ui_status(num):
    """轮询用的状态片段（Bot / NapCat 状态区）：标记只在后端维护一份，前端不拼 HTML"""
    if num not in BOTS: return jsonify({'ok': False, 'error': '无效编号'}), 404
    b = BOTS[num]
    info = _bot_info(b)
    nc = _napcat_online(b)
    nc['webui'] = _napcat_webui(b)
    return jsonify({'ok': True, 'data': {
        # 状态区一律用"元素 id → 内容"的通用形状：两端页面骨架相同，外壳一套代码就能套用
        'html': {
            'botStatusArea': _ui.bot_status_html(info),
            'napcatStatusArea': _ui.napcat_status_html(nc, info),
            'napcatActionArea': _ui.napcat_restart_btn(nc) + _ui.napcat_webui_btn(nc),
            'dashNapcatAction': _ui.napcat_restart_btn(nc, True) + _ui.napcat_webui_btn(nc, True),
        },
        'text': {
            'dashBotVal': '运行中' if info['running'] else '已停止',
            'dashBotDesc': f"{info.get('name') or ''} · PID {info.get('pid') or '-'}",
            'dashNapcatVal': _ui.napcat_text(nc),
            'dashNapcatDesc': _ui.napcat_desc(nc, info.get('qq')),
        },
        'napcat_online': nc.get('online'),
    }})


@app.route('/api/bot/<int:num>/config', methods=['POST'])
@login_required
def save_config(num):
    if num not in BOTS: return jsonify({'error': '无效编号'}), 404
    data = request.get_json() or {}
    plugin = data.get('plugin')
    cfg = data.get('cfg', {})
    raw = bool(data.get('raw'))          # JSON 原文页签：原样写入，不做类型校验


    b = BOTS[num]
    dd = os.path.join(b['dir'], 'data')
    pd = os.path.join(b['dir'], 'plugins')

    import utils.plugin_toggle as _pt
    meta = _pt.get_plugin_meta(plugin, pd)
    if not meta:
        return jsonify({'error': f'未知插件: {plugin}'}), 400

    cf = meta.get('config_file')
    if not cf:
        return jsonify({'ok': True, 'msg': '该插件无需配置'})

    config_path = os.path.join(dd, cf)
    merged = read_json(config_path)

    payload = _plugin_cfg_payload(b, meta, plugin)
    if payload['declared'] and not raw:
        # 插件**自己声明**了配置项 → 按声明做类型转换与校验（path 决定写回哪一段）
        fields = {f['name']: f for f in payload['fields']}
        ok, merged, errs = _cs.validate_and_merge(fields, merged, cfg, strict=True)
        if not ok:
            # 精确到字段的错误：前端能标红到控件，且**一字节都不落盘**
            return jsonify({'ok': False, 'error': '配置校验未通过', 'field_errors': errs}), 400
    else:
        # 未声明（或 JSON 原文页签）：沿用历史语义原样合并
        merged = _legacy_merge(merged, cfg)

    write_json(config_path, merged)
    # 通知 bot 立即重载配置（web 端与插件实际配置保持同步，无需重启/轮询）
    _notify_bot_reload(str(b['qq']))
    return jsonify({'ok': True, 'validated': bool(payload['declared']) and not raw,
                    'msg': '配置已保存并生效'})


@app.route('/api/bot/<int:num>/group-toggles', methods=['POST'])
@login_required
def save_group_toggles(num):
    """批量保存群组开关"""
    if num not in BOTS: return jsonify({'error': '无效编号'}), 404
    data = request.get_json()
    toggles = data.get('toggles', {})
    if not toggles:
        return jsonify({'error': '参数无效'}), 400
    b = BOTS[num]
    import utils.plugin_toggle as _pt
    _pt.set_batch_toggles(toggles, os.path.join(b['dir'], 'data'))
    return jsonify({'ok': True, 'msg': '群组开关已保存'})

@app.route('/api/bot/<int:num>/restart', methods=['POST'])
@login_required
def restart_bot(num):
    """重启 Bot（复用 bot_action 的 screen 逻辑，支持动态实例编号）"""
    return bot_action(num, 'restart')

@app.route('/api/bot/<int:num>/status')
@login_required
def get_status(num):
    if num not in BOTS: return jsonify({'error': '无效编号'}), 404
    b = BOTS[num]
    running, pid, uptime = _bot_proc(b)
    return jsonify({'running': running, 'status': 'running' if running else 'stopped',
                    'pid': pid, 'uptime': uptime})

@app.route('/api/bot/<int:n>/screen-log')
@login_required
def bot_screen_log(n):
    if n not in BOTS: return jsonify({'error': '无效编号'}), 404
    b = BOTS[n]
    log_file = os.path.join(b['dir'], 'runtime.log')
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
            return jsonify({'log': ''.join(lines[-200:])})
        except Exception as e:
            return jsonify({'log': f'读取日志失败: {e}'})
    # fallback: try screen hardcopy
    try:
        tmpfile = f'/tmp/bot_{n}_screen_log.txt'
        subprocess.run(['screen', '-S', b['screen'], '-X', 'hardcopy', tmpfile], timeout=5, capture_output=True)
        if os.path.exists(tmpfile):
            with open(tmpfile, 'r', encoding='utf-8', errors='replace') as f:
                log_content = f.read()
            return jsonify({'log': log_content})
    except:
        pass
    return jsonify({'log': '暂无日志，请先启动机器人'})

# ====== 静态页面路由 ======
@app.route('/')
def login():
    return send_from_directory(STATIC_DIR, 'index.html')

@app.route('/panel/')
def serve_panel():
    return send_from_directory(os.path.join(STATIC_DIR, 'panel'), 'index.html')

@app.route('/panel/config/')
def serve_panel_config():
    return send_from_directory(os.path.join(STATIC_DIR, 'panel', 'config'), 'index.html')

@app.route('/panel/<path:p>')
def serve_panel_static(p):
    return send_from_directory(os.path.join(STATIC_DIR, 'panel'), p)

@app.route('/<path:p>')
def stat(p):
    return send_from_directory(STATIC_DIR, p)

if __name__ == '__main__':
    import argparse
    _parser = argparse.ArgumentParser(description='MyBot Web Panel')
    _parser.add_argument('--host', default='127.0.0.1', help='监听地址（0.0.0.0 开放公网）')
    _parser.add_argument('--port', type=int, default=8080, help='监听端口')
    _parser.add_argument('--bot-dir', default=None, help='单实例模式：指定当前实例项目目录')
    _parser.add_argument('--bot-name', default=None, help='单实例模式：机器人名称')
    _parser.add_argument('--bot-qq', default=None, help='单实例模式：机器人QQ号')
    _parser.add_argument('--bot-screen', default='bot', help='单实例模式：screen会话名')
    _args = _parser.parse_args()

    # 动态发现所有已部署实例（install.sh 注册表 + 项目目录 + 硬编码）
    refresh_bots()

    # 单实例模式：仅保留指定实例并设为当前，但面板仍可通过 /api/bots 看到全部
    if _args.bot_dir:
        only = {
            'name': _args.bot_name or 'Bot',
            'screen': _args.bot_screen,
            'dir': _args.bot_dir,
            'qq': _args.bot_qq or '',
            'master': _read_master_qq(_args.bot_dir),
            'napcat_port': 6099,
        }
        matched = [n for n, b in BOTS.items() if b.get('dir') == _args.bot_dir]
        if matched:
            CURRENT_BOT = matched[0]
            BOTS = {CURRENT_BOT: dict(BOTS[CURRENT_BOT])}
        else:
            CURRENT_BOT = max(BOTS.keys(), default=0) + 1
            BOTS = {CURRENT_BOT: only}
    else:
        # 默认模式：选中第一个在线实例（或第一个实例）
        for n, b in BOTS.items():
            if os.path.exists(os.path.join(b.get('dir', ''), 'main.py')):
                CURRENT_BOT = n
                break
        else:
            CURRENT_BOT = min(BOTS.keys()) if BOTS else None

    app.run(host=_args.host, port=_args.port, debug=False)

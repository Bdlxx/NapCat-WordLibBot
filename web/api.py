import os
import sys
import json
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

BOTS = {
    1: {'name': '依星', 'screen': 'bot', 'dir': '/root/mybot', 'qq': '740979632', 'master': '2840771765', 'napcat_port': 6099},
    2: {'name': '羽笙', 'screen': 'bot2', 'dir': os.path.dirname(STATIC_DIR), 'qq': '2551736206', 'master': '2840771765', 'napcat_port': 6100},
}
# 当前选中的实例编号（单实例模式 / 门户跳转时指定）
CURRENT_BOT = None

# install.sh 的实例注册/目录规范（脚本目录下 instances/）
# 新布局：<项目根>/instances/<QQ>（项目） + <项目根>/instances/registry/<QQ>.sh（注册）
# 旧布局（兼容）：/tmp/napbot_instances/<QQ>.sh + /root/mybot_<QQ>
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTANCES_ROOT = os.path.join(_BASE_DIR, 'instances')
INSTANCES_DIR = os.path.join(INSTANCES_ROOT, 'registry')
LEGACY_INSTANCES_DIR = "/tmp/napbot_instances"
INST_PROJECT_PREFIX = "/root/mybot_"


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
        })

    return result


def refresh_bots():
    """启动时重建 BOTS：动态发现所有实例（保留现有引用兼容）"""
    global BOTS
    discovered = discover_instances()
    if discovered:
        BOTS = discovered


@app.route('/api/bots')
def api_bots():
    """返回全部实例列表（供门户/面板切换）"""
    import subprocess as _sp
    items = []
    for n, b in BOTS.items():
        running = False
        try:
            r = _sp.run(f"screen -list | grep -w {b['screen']}",
                        shell=True, capture_output=True, text=True, timeout=5)
            running = r.returncode == 0
        except Exception:
            pass
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
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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
    """根据bot名称返回路径名"""
    if '星' in bot_name: return 'yixing'
    if '笙' in bot_name: return 'yusheng'
    return bot_name

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
        path = _bot_path(bot_name)
        return jsonify({'success': True, 'message': f'正在进入{bot_name}面板', 'redirect': f'/{path}/'}), 200
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
        r = subprocess.run("screen -list | grep -w " + bot['screen'], shell=True, capture_output=True, text=True, timeout=5)
        running = r.returncode == 0
        result[n] = {'running': running, 'name': bot['name'], 'status': 'running' if running else 'stopped'}
    return jsonify({'success': True, 'bot1': result.get(1), 'bot2': result.get(2)})

@app.route('/api/bot/<int:n>/info')
@login_required
def bot_info(n):
    if n not in BOTS: return jsonify({'error': '无效编号'}), 404
    b = BOTS[n]
    r = subprocess.run("screen -list | grep -w " + b['screen'], shell=True, capture_output=True, text=True, timeout=5)
    running = r.returncode == 0
    return jsonify({'success': True, 'name': b['name'], 'qq': b['qq'], 'master': b['master'], 'dir': b['dir'], 'screen': b['screen'], 'running': running, 'status': 'running' if running else 'stopped', 'napcat_port': b['napcat_port']})

@app.route('/api/bot/<int:n>/log')
@login_required
def bot_log(n):
    if n not in BOTS: return jsonify({'error': '无效编号'}), 404
    b = BOTS[n]
    log_file = os.path.join(b['dir'], 'log.txt')
    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
            return jsonify({'log': ''.join(lines[-50:])})
    return jsonify({'log': '暂无日志'})

@app.route('/api/bot/<int:n>/napcat-log')
@login_required
def bot_napcat_log(n):
    if n not in BOTS: return jsonify({'error': '无效编号'}), 404
    container = 'napcat' if n == 1 else 'napcat2'
    try:
        r = subprocess.run("docker logs " + container + " --tail 30 2>&1", shell=True, capture_output=True, text=True, timeout=5)
        return jsonify({'log': r.stdout or '容器日志为空'})
    except Exception as e:
        return jsonify({'log': '获取失败: ' + str(e)})

@app.route('/api/bot/<int:n>/napcat-status')
@login_required
def napcat_status(n):
    if n not in BOTS: return jsonify({'error': '无效编号'}), 404
    container = 'napcat' if n == 1 else 'napcat2'
    try:
        r = subprocess.run("docker inspect " + container + " --format '{{.State.Status}}'", shell=True, capture_output=True, text=True, timeout=5)
        status = r.stdout.strip()
        running = status == 'running'
        return jsonify({'running': running, 'container': container, 'status': status})
    except Exception as e:
        return jsonify({'running': False, 'container': container, 'status': 'unknown', 'error': str(e)})

@app.route('/api/bot/<int:n>/napcat-qr')
@login_required
def napcat_qr(n):
    if n not in BOTS: return jsonify({'error': '无效编号'}), 404
    container = 'napcat' if n == 1 else 'napcat2'
    try:
        r = subprocess.run("docker exec " + container + " cat /app/napcat/cache/qrcode.png 2>/dev/null", shell=True, capture_output=True, timeout=10)
        if r.returncode != 0 or not r.stdout:
            return jsonify({'qr': None, 'error': '暂无二维码，NapCat可能未启动或未生成二维码'})
        import base64
        qr_b64 = base64.b64encode(r.stdout).decode()
        return jsonify({'qr': qr_b64, 'container': container})
    except Exception as e:
        return jsonify({'qr': None, 'error': str(e)})

@app.route('/api/bot/<int:n>/<action>', methods=['POST'])
@login_required
def bot_action(n, action):
    if n not in BOTS: return jsonify({'error': '无效编号'}), 404
    b = BOTS[n]
    try:
        if action in ('stop', 'start', 'restart'):
            r = subprocess.run(['bot', action, str(n)], capture_output=True, text=True, timeout=15)
            msg = r.stdout.strip() or r.stderr.strip() or f'{b["name"]} {action} 完成'
            return jsonify({'success': r.returncode == 0, 'message': msg})
        else:
            return jsonify({'error': '未知操作'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ====== 插件配置 API ======
@app.route('/api/bot/<int:num>/plugins')
@login_required
def get_plugins(num):
    if num not in BOTS: return jsonify({'error': '无效编号'}), 404
    b = BOTS[num]
    dd = os.path.join(b['dir'], 'data')
    pd = os.path.join(b['dir'], 'plugins')
    import utils.plugin_toggle as _pt

    plugins = {}

    # 1. 动态扫描插件目录：与主程序实际加载的插件（有 handle()）保持一致
    avail_list = list(_pt.get_available_plugins(pd))
    for pkey, meta in avail_list:
        pp = {'name_cn': meta['name_cn'], 'name_en': meta['name_en'], 'fields': [], 'has_config': False}

        cf = meta.get('config_file')
        if cf and os.path.exists(os.path.join(dd, cf)):
            pp['has_config'] = True
            config_data = read_json(os.path.join(dd, cf))

            # 命令段
            for cmd_key, cmd_val in config_data.get('commands', {}).items():
                pp['fields'].append({
                    'k': f'cmd_{cmd_key}', 'l': f'指令「{cmd_key}」',
                    't': 'text', 'v': cmd_val,
                    'hint': f'触发「{meta["name_cn"]}」的{cmd_key}命令',
                })

            # 设置段
            for set_key, set_val in config_data.get('settings', {}).items():
                if isinstance(set_val, bool):
                    pp['fields'].append({
                        'k': f'setting_{set_key}',
                        'l': '插件开关' if set_key == 'enabled' else f'参数「{set_key}」',
                        't': 'sel', 'o': ['true', 'false'],
                        'v': str(set_val).lower(),
                        'hint': '全局开关，关闭后所有人无法使用' if set_key == 'enabled' else '',
                    })
                elif isinstance(set_val, (int, float)):
                    pp['fields'].append({
                        'k': f'setting_{set_key}', 'l': f'参数「{set_key}」',
                        't': 'num', 'v': set_val, 'hint': '',
                    })
                else:
                    pp['fields'].append({
                        'k': f'setting_{set_key}', 'l': f'参数「{set_key}」',
                        't': 'text', 'v': str(set_val) if set_val else '',
                    })

            # 回复段
            for msg_key, msg_val in config_data.get('messages', {}).items():
                is_long = isinstance(msg_val, str) and len(msg_val) > 30
                pp['fields'].append({
                    'k': f'msg_{msg_key}', 'l': f'回复「{msg_key}」',
                    't': 'textarea' if is_long else 'text', 'v': msg_val,
                    'hint': f'触发{msg_key}时的回复',
                })

            # 管理员
            admins = config_data.get('admins')
            if admins is not None:
                pp['fields'].append({
                    'k': 'admins', 'l': '管理员QQ（每行一个）',
                    't': 'textlist', 'v': admins if isinstance(admins, list) else [],
                    'hint': '每行填一个QQ号，管理员可管理插件',
                })

            # 扁平配置兜底：不在 commands/settings/messages 中的其他字段
            handled_cats = {'commands', 'settings', 'messages', 'admins', '_note'}
            for ck in config_data.get('commands', {}): handled_cats.add(ck)
            for sk in config_data.get('settings', {}): handled_cats.add(sk)
            for mk in config_data.get('messages', {}): handled_cats.add(mk)
            for fk, fv in config_data.items():
                if fk in handled_cats: continue
                if isinstance(fv, bool):
                    pp['fields'].append({
                        'k': f'cfg_{fk}', 'l': f'参数「{fk}」',
                        't': 'sel', 'o': ['true', 'false'], 'v': str(fv).lower(),
                    })
                elif isinstance(fv, (int, float)):
                    pp['fields'].append({
                        'k': f'cfg_{fk}', 'l': f'参数「{fk}」',
                        't': 'num', 'v': fv,
                    })
                elif isinstance(fv, str):
                    field_type = 'password' if ('cookie' in fk.lower() or 'key' in fk.lower() or 'token' in fk.lower()) else 'text'
                    pp['fields'].append({
                        'k': f'cfg_{fk}', 'l': f'参数「{fk}」',
                        't': field_type, 'v': fv,
                    })
                elif isinstance(fv, list):
                    pp['fields'].append({
                        'k': f'cfg_{fk}', 'l': f'参数「{fk}」',
                        't': 'textlist', 'v': fv,
                    })

        plugins[pkey] = pp

    # 2. 群组开关表格数据
    import requests as _req
    group_info = {}
    try:
        bc = read_json(os.path.join(b['dir'], 'config.json'))
        nh = bc.get('NAPCAT_HTTP', 'http://127.0.0.1:3000')
        tk = bc.get('ACCESS_TOKEN', '')
        gl = _req.get(f'{nh}/get_group_list', params={'access_token': tk}, timeout=5).json()
        if gl.get('status') == 'ok' and gl.get('data'):
            for g in gl['data']:
                gid = str(g.get('group_id', ''))
                gname = g.get('group_name', '未知群') or '未知群'
                gavatar = f"https://p.qlogo.cn/gh/{gid}/{gid}/"
                group_info[gid] = {'name': gname, 'avatar': gavatar}
    except Exception as e:
        print(f'[API] 获取群列表失败: {e}')

    tg = _pt.get_toggles_matrix(os.path.join(b['dir'], 'data'), [k for k, _ in avail_list])
    # 合并全部群（包括没有开关记录的）
    all_groups = sorted(set(tg['groups'] + sorted(group_info.keys())))
    merged_toggles = {}
    for gid in all_groups:
        merged_toggles[gid] = tg['toggles'].get(gid, {p: False for p in tg['plugins']})
    tg['groups'] = all_groups
    tg['toggles'] = merged_toggles
    tg['groupInfo'] = group_info
    plugins['_toggles'] = tg
    plugins['_toggles']['_pluginMeta'] = {k: {'name_cn': v['name_cn'], 'name_en': v['name_en']} for k, v in _pt.get_plugin_meta(None, pd).items()}

    # 避免暴露服务器路径
    safe_bot = {k: v for k, v in b.items() if k not in ('dir', 'screen', 'napcat_port')}
    return jsonify({'bot': safe_bot, 'plugins': plugins})


@app.route('/api/bot/<int:num>/config', methods=['POST'])
@login_required
def save_config(num):
    if num not in BOTS: return jsonify({'error': '无效编号'}), 404
    data = request.get_json()
    plugin = data.get('plugin')
    cfg = data.get('cfg', {})
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

    for k, v in cfg.items():
        if k == 'admins':
            merged['admins'] = v
        elif k.startswith('cmd_'):
            merged.setdefault('commands', {})[k.replace('cmd_', '', 1)] = v
        elif k.startswith('msg_'):
            merged.setdefault('messages', {})[k.replace('msg_', '', 1)] = v
        elif k.startswith('setting_'):
            key = k.replace('setting_', '', 1)
            if key == 'enabled':
                v = (str(v).lower() == 'true')
            elif isinstance(v, str) and v.replace('.', '', 1).replace('-', '', 1).isdigit():
                v2 = float(v) if '.' in v else int(v)
                old = merged.get('settings', {}).get(key)
                if isinstance(old, (int, float)):
                    v = type(old)(v2)
                else:
                    v = v2
            merged.setdefault('settings', {})[key] = v
        elif k.startswith('cfg_'):
            key = k.replace('cfg_', '', 1)
            if isinstance(v, str) and v.replace('.', '', 1).replace('-', '', 1).isdigit():
                try: v = int(v)
                except: pass
            merged[key] = v
        else:
            merged[k] = v

    write_json(config_path, merged)
    return jsonify({'ok': True, 'msg': '配置已保存，请重启生效'})


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
    if num not in BOTS: return jsonify({'error': '无效编号'}), 404
    b = BOTS[num]
    try:
        r = subprocess.run(['bot', 'restart', str(num)], capture_output=True, text=True, timeout=15)
        msg = r.stdout.strip() or r.stderr.strip() or '已重启 ' + b['name']
        return jsonify({'ok': True, 'msg': msg})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bot/<int:num>/status')
@login_required
def get_status(num):
    if num not in BOTS: return jsonify({'error': '无效编号'}), 404
    b = BOTS[num]
    r = subprocess.run("screen -list | grep -w " + b['screen'], shell=True, capture_output=True, text=True, timeout=5)
    running = r.returncode == 0
    return jsonify({'running': running, 'status': 'running' if running else 'stopped'})

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

@app.route('/yixing/')
def serve_yixing():
    return send_from_directory(os.path.join(STATIC_DIR, 'yixing'), 'index.html')

@app.route('/yixing/<path:p>')
def serve_yixing_static(p):
    return send_from_directory(os.path.join(STATIC_DIR, 'yixing'), p)

@app.route('/yusheng/')
def serve_yusheng():
    return send_from_directory(os.path.join(STATIC_DIR, 'yusheng'), 'index.html')

@app.route('/yusheng/<path:p>')
def serve_yusheng_static(p):
    return send_from_directory(os.path.join(STATIC_DIR, 'yusheng'), p)

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

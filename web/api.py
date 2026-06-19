import os
import json
import subprocess
import time
import hashlib
from functools import wraps
from flask import Flask, jsonify, request, send_from_directory, session

# ====== 路径 ======
STATIC_DIR = os.path.dirname(os.path.abspath(__file__))

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

    if pwd in PASSWORDS:
        _record_login_attempt(client_ip, success=True)
        session.clear()
        session.permanent = True
        session['authenticated'] = True
        session['bot_name'] = PASSWORDS[pwd]
        # 用 bot_name 确定跳转路径，不用密码
        target = PASSWORDS[pwd]
        if target == 'yixing':
            return jsonify({'success': True, 'message': '正在进入依星面板', 'redirect': '/yixing/'}), 200
        elif target == 'yusheng':
            return jsonify({'success': True, 'message': '正在进入羽笙面板', 'redirect': '/yusheng/'}), 200
        else:
            return jsonify({'success': True, 'message': '登录成功', 'redirect': '/' + target + '/'}), 200
    else:
        _record_login_attempt(client_ip, success=False)
        time.sleep(1)  # 防止时序攻击
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
        r = subprocess.run("screen -list | grep " + bot['screen'], shell=True, capture_output=True, text=True, timeout=5)
        running = r.returncode == 0 and bot['screen'] in r.stdout
        result[n] = {'running': running, 'name': bot['name'], 'status': 'running' if running else 'stopped'}
    return jsonify({'success': True, 'bot1': result.get(1), 'bot2': result.get(2)})

@app.route('/api/bot/<int:n>/info')
@login_required
def bot_info(n):
    if n not in BOTS: return jsonify({'error': '无效编号'}), 404
    b = BOTS[n]
    r = subprocess.run("screen -list | grep " + b['screen'], shell=True, capture_output=True, text=True, timeout=5)
    running = r.returncode == 0 and b['screen'] in r.stdout
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
    plugins = {}
    if os.path.exists(os.path.join(pd, 'wordlib.py')):
        wc = read_json(os.path.join(dd, 'wordlib_config.json'))
        a = wc.get('admins', [])
        base_fields = []
        if a is not None:
            base_fields.append({'k': 'admins', 'l': '管理员QQ（每行一个）', 't': 'textlist', 'v': a or [], 'hint': '每行填一个QQ号，管理员可以增删词条'})
        for k, v in wc.get('commands', {}).items():
            base_fields.append({'k': 'wl_cmd_' + k, 'l': '命令「' + k + '」', 't': 'text', 'v': v, 'hint': {
            'add': '向词库添加新词条（关键词+回答）',
            'delete': '从词库删除指定词条',
            'query': '查询词库中的词条或查看列表',
            'encode': '将消息转码为CQ码格式',
            'sign1': '每日签到获取好感度',
            'sign2': '每日签到（备选指令）',
            'nickname': '设置自己的自定义昵称（需好感度）',
            'rank': '查看签到排行榜',
            'praise1': '让机器人给你点赞',
            'add_fuzzy': '添加模糊匹配词条（含有关键词即触发）',
            'enable': '开启词库插件功能',
            'disable': '关闭词库插件功能',
        }.get(k, '')})
        wl_hints = {
            'favor_add_min': '签到最少增加的好感度',
            'favor_add_max': '签到最多增加的好感度',
            'favor_minus_min': '重复签到最少扣除的好感度',
            'favor_minus_max': '重复签到最多扣除的好感度',
            'nickname_need_favor': '设置自定义昵称所需的最低好感度',
            'rank_top_n': '签到排行榜最多显示人数',
            'praise_count': '每次「赞我」增加的点赞次数',
            'encode_timeout': '转码等待超时秒数，超时后自动取消',
        }
        for k, v in wc.get('settings', {}).items():
            if k == 'enabled':
                base_fields.append({'k': 'wl_setting_enabled', 'l': '插件开关', 't': 'sel', 'o': ['true', 'false'], 'v': str(v).lower(), 'hint': '关闭后所有人无法使用词库相关功能'})
            else:
                base_fields.append({'k': 'wl_setting_' + k, 'l': '参数「' + k + '」', 't': 'num', 'v': v, 'hint': wl_hints.get(k, '')})
        wl_msg_hints = {
            'sign_success': '签到成功时的回复，支持[add][favor]变量',
            'sign_already': '重复签到时的回复，支持[minus][favor]变量',
            'nickname_fail': '好感度不足无法设置昵称时的回复，支持[need]变量',
            'nickname_set': '昵称设置成功时的回复，支持[nick]变量',
            'nickname_format_error': '昵称命令格式错误时的提示',
            'nickname_empty': '昵称为空时的提示',
            'praise_success': '点赞成功时的回复，支持[count]变量',
            'praise_already': '今天已点赞过时的提示',
            'praise_fail': '点赞失败时的提示',
            'rank_empty': '签到排行榜为空时的提示',
            'rank_title': '排行榜标题模板，支持[top]变量',
            'rank_item': '排行榜每行格式，支持[idx][name][uid][total]变量',
            'add_step1': '两步式添加词条-第1步（输入关键词）',
            'add_step2': '两步式添加词条-第2步（输入回答）',
            'add_step3': '两步式添加词条-第3步（选择匹配模式）',
            'add_success_exact': '精准词条添加成功时的回复，支持[keyword][count]变量',
            'add_success_fuzzy': '模糊词条添加成功时的回复，支持[keyword][count]变量',
            'add_format_error': '添加词条格式错误时的提示',
            'add_empty': '关键词或回答为空时的提示',
            'keyword_empty': '关键词为空时的提示',
            'reply_empty': '回答为空时的提示',
            'mode_invalid': '匹配模式选择错误时的提示',
            'delete_success': '词条删除成功时的回复，支持[keyword]变量',
            'delete_reply_success': '单条回复删除成功时的回复，支持[keyword][idx][content]变量',
            'delete_not_found': '关键词不存在时的提示',
            'delete_idx_invalid': '删除序号无效时的提示，支持[count]变量',
            'delete_reply_idx_invalid': '回复序号无效时的提示，支持[count]变量',
            'delete_idx_must_number': '序号必须是数字时的提示',
            'delete_idx_positive': '序号必须为正整数时的提示',
            'delete_format_error': '删除命令格式错误时的提示，支持[cmd]变量',
            'wordlib_empty': '词库为空时的提示',
            'query_list_title': '词库列表标题模板，支持[top]变量',
            'query_list_item': '词库列表每行格式，支持[idx][keyword][count]变量',
            'query_detail_title': '关键词详情标题，支持[keyword][count]变量',
            'query_detail_item': '关键词详情每行格式，支持[idx][mode][content]变量',
            'query_no_reply': '关键词暂无回复时的提示',
            'encode_start': '转码开始时的提示',
            'encode_result': '转码结果模板，支持[code]变量',
            'encode_timeout': '转码超时时的提示',
        }
        for k, v in wc.get('messages', {}).items():
            field_type = 'textarea' if len(v) > 30 else 'text'
            base_fields.append({'k': 'wl_msg_' + k, 'l': '回复「' + k + '」', 't': field_type, 'v': v, 'hint': wl_msg_hints.get(k, '')})
        plugins['wordlib'] = {'name': '词库插件', 'fields': base_fields}
    # 分群开关表
    import utils.plugin_toggle as _pt
    gf = {}
    for gid, toggles in _pt.get_all_toggles().items():
        desc = ' '.join(f'{p}={chr(10003) if v else chr(10007)}' for p, v in toggles.items() if v)
        if desc:
            gf[gid] = {'_line': f'群 {gid}: {desc}'}
    if gf:
        plugins['group_toggles'] = {'name': '分群开关', 'fields': gf}
    return jsonify({'bot': b, 'plugins': plugins})

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
    try:
        if plugin == 'marry':
            merged = read_json(os.path.join(dd, 'marry_config.json'))
            for k, v in cfg.items():
                if k.startswith('marry_cmd_'):
                    merged.setdefault('commands', {})[k.replace('marry_cmd_', '')] = v
                elif k.startswith('marry_rep_'):
                    merged.setdefault('replies', {})[k.replace('marry_rep_', '')] = v
                else:
                    merged.setdefault('settings', {})[k] = v
            write_json(os.path.join(dd, 'marry_config.json'), merged)
        elif plugin == 'wordlib':
            wc = read_json(os.path.join(dd, 'wordlib_config.json'))
            for k, v in cfg.items():
                if k.startswith('wl_cmd_'):
                    wc.setdefault('commands', {})[k.replace('wl_cmd_', '')] = v
                elif k.startswith('wl_msg_'):
                    wc.setdefault('messages', {})[k.replace('wl_msg_', '')] = v
                elif k.startswith('wl_setting_'):
                    key = k.replace('wl_setting_', '')
                    if key == 'enabled':
                        v = v == 'true'
                    else:
                        try: v = int(v)
                        except: pass
                    wc.setdefault('settings', {})[key] = v
                elif k == 'admins':
                    wc['admins'] = v
            write_json(os.path.join(dd, 'wordlib_config.json'), wc)
        else:
            return jsonify({'error': '未知插件'}), 400
        return jsonify({'ok': True, 'msg': '配置已保存，请点击重启按钮生效'})
    except Exception as e:
        return jsonify({'error': '保存失败: ' + str(e)}), 500

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
    r = subprocess.run("screen -list | grep " + b['screen'], shell=True, capture_output=True, text=True, timeout=5)
    running = r.returncode == 0 and b['screen'] in r.stdout
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
        subprocess.run(f"screen -S {b['screen']} -X hardcopy {tmpfile}", shell=True, timeout=5, capture_output=True)
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
    _parser.add_argument('--bot-dir', default=None, help='单实例模式：机器人项目目录')
    _parser.add_argument('--bot-name', default=None, help='单实例模式：机器人名称')
    _parser.add_argument('--bot-qq', default=None, help='单实例模式：机器人QQ号')
    _parser.add_argument('--bot-screen', default='bot', help='单实例模式：screen会话名')
    _args = _parser.parse_args()
    # 单实例模式：用传入参数覆盖 BOTS
    if _args.bot_dir:
        BOTS.clear()
        BOTS[1] = {
            'name': _args.bot_name or 'Bot',
            'screen': _args.bot_screen,
            'dir': _args.bot_dir,
            'qq': _args.bot_qq or '',
            'master': '',
            'napcat_port': 6099,
        }
    app.run(host=_args.host, port=_args.port, debug=False)

import os
import json
import subprocess
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

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('authenticated'):
            return jsonify({'error': '未登录', 'need_login': True}), 401
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
    pwd = data.get('password', '').strip().lower()
    if pwd in PASSWORDS:
        session.clear()
        session['authenticated'] = True
        session['bot_name'] = PASSWORDS[pwd]
        return jsonify({'success': True, 'message': '正在进入' + PASSWORDS[pwd] + '面板', 'redirect': '/' + pwd + '/'}), 200
    else:
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
        if action == 'stop':
            subprocess.run("screen -S " + b['screen'] + " -X quit 2>/dev/null", shell=True, timeout=5)
            return jsonify({'success': True, 'message': b['name'] + ' 已停止'})
        elif action == 'start':
            py_cmd = 'python3'
            if os.path.exists(os.path.join(b['dir'], 'venv/bin/python3')):
                py_cmd = './venv/bin/python3'
            subprocess.run("cd " + b['dir'] + " && screen -dmS " + b['screen'] + " " + py_cmd + " main.py", shell=True, timeout=5)
            return jsonify({'success': True, 'message': b['name'] + ' 已启动'})
        elif action == 'restart':
            subprocess.run("screen -S " + b['screen'] + " -X quit 2>/dev/null", shell=True, timeout=5)
            py_cmd = 'python3'
            if os.path.exists(os.path.join(b['dir'], 'venv/bin/python3')):
                py_cmd = './venv/bin/python3'
            subprocess.run("cd " + b['dir'] + " && screen -dmS " + b['screen'] + " " + py_cmd + " main.py", shell=True, timeout=5)
            return jsonify({'success': True, 'message': b['name'] + ' 已重启'})
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
    if os.path.exists(os.path.join(pd, 'marry.py')):
        mc = read_json(os.path.join(dd, 'marry_config.json'))
        fields = [
            {'k': 'success_rate', 'l': '结婚成功率(%)', 't': 'num', 'min': 0, 'max': 100, 'v': mc.get('settings', {}).get('success_rate', 80)},
            {'k': 'divorce_cd_hours', 'l': '离婚CD(小时)', 't': 'num', 'min': 0, 'v': mc.get('settings', {}).get('divorce_cd_hours', 0.25)},
        ]
        plugins['marry'] = {'name': '结婚插件', 'fields': fields + build_fields_from_cfg(mc, 'marry')}
    if os.path.exists(os.path.join(pd, 'wordlib.py')):
        wc = read_json(os.path.join(dd, 'wordlib_config.json'))
        a = wc.get('admins', [])
        base_fields = []
        if a is not None:
            base_fields.append({'k': 'admins', 'l': '管理员QQ（每行一个）', 't': 'textlist', 'v': a or []})
        for k, v in wc.get('commands', {}).items():
            base_fields.append({'k': 'wl_cmd_' + k, 'l': '命令「' + k + '」', 't': 'text', 'v': v})
        for k, v in wc.get('messages', {}).items():
            field_type = 'textarea' if len(v) > 30 else 'text'
            base_fields.append({'k': 'wl_msg_' + k, 'l': '回复「' + k + '」', 't': field_type, 'v': v})
        plugins['wordlib'] = {'name': '词库插件', 'fields': base_fields}
    if num == 2 and os.path.exists(os.path.join(pd, 'pseudo_persona.py')):
        p = read_json(os.path.join(dd, 'persona_config.json'))
        plugins['pseudo'] = {'name': '伪人模式', 'fields': [
            {'k': 'current_model', 'l': '当前模型', 't': 'sel', 'o': ['glm', 'gemini'], 'v': p.get('current_model', 'gemini')},
            {'k': 'reply_probability', 'l': '主动回复概率', 't': 'num', 'min': 0, 'max': 1, 's': 0.1, 'v': p.get('reply_probability', 1.0)},
            {'k': 'max_history', 'l': '最大历史记录', 't': 'num', 'min': 1, 'v': p.get('max_history', 50)},
            {'k': 'context_window', 'l': '上下文窗口', 't': 'num', 'min': 1, 'v': p.get('context_window', 20)},
            {'k': 'split_count', 'l': '消息拆分数量', 't': 'num', 'min': 1, 'v': p.get('split_count', 3)},
            {'k': 'split_delay_min', 'l': '拆分最小延迟(分)', 't': 'num', 'min': 0, 'v': p.get('split_delay_min', 1)},
            {'k': 'split_delay_max', 'l': '拆分最大延迟(分)', 't': 'num', 'min': 1, 'v': p.get('split_delay_max', 3)},
        ]}
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
                elif k == 'admins':
                    wc['admins'] = v
            write_json(os.path.join(dd, 'wordlib_config.json'), wc)
        elif plugin == 'pseudo':
            old = read_json(os.path.join(dd, 'persona_config.json'))
            for k, v in cfg.items():
                old[k] = v
            write_json(os.path.join(dd, 'persona_config.json'), old)
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
        subprocess.run("screen -S " + b['screen'] + " -X quit 2>/dev/null", shell=True, timeout=5)
        py_cmd = 'python3'
        if os.path.exists(os.path.join(b['dir'], 'venv/bin/python3')):
            py_cmd = './venv/bin/python3'
        subprocess.run("cd " + b['dir'] + " && screen -dmS " + b['screen'] + " " + py_cmd + " main.py", shell=True, timeout=5)
        return jsonify({'ok': True, 'msg': '已重启 ' + b['name']})
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
    app.run(host='127.0.0.1', port=5000, debug=False)

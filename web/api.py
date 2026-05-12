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
        settings = mc.get('settings', {})
        fields = [
            {'k': 'success_rate', 'l': '结婚成功率(%)', 't': 'num', 'min': 0, 'max': 100, 'v': settings.get('success_rate', 80), 'hint': '数字越大求婚越容易成功，设为0则必定失败'},
            {'k': 'divorce_cd_hours', 'l': '离婚CD(小时)', 't': 'num', 'min': 0, 'v': settings.get('divorce_cd_hours', 0.25), 'hint': '离婚后需要等待多久才能再次结婚，设为0则无限制'},
            {'k': 'enabled', 'l': '插件开关', 't': 'sel', 'o': ['true', 'false'], 'v': str(settings.get('enabled', True)).lower(), 'hint': '关闭后所有人无法使用结婚相关功能'},
        ]
        marry_cmd_hints = {
    'marry': '随机娶一位群友',
    'marry_t': '娶指定的群友（需@对方）',
    'marry_f': '随机嫁给一位群友',
    'marry_ft': '嫁给指定的群友（需@对方）',
    'divorce': '和今天的对象离婚',
    'my_object': '查看今天你的对象是谁',
    'set_prob': '设置结婚成功率（主人专用）',
    'set_cd': '设置离婚冷却时间（主人专用）',
    'enable': '开启结婚插件',
    'disable': '关闭结婚插件',
}
        marry_rep_hints = {
            'only_group': '非群聊环境下的提示',
            'no_members': '无法获取群成员列表时的提示',
            'already_married': '自己已有对象时的提示',
            'no_one_left': '群内无人可选时的提示',
            'self_marry': '试图娶/嫁自己时的提示',
            'not_in_group': '对方不在本群时的提示',
            'target_married': '对方已有对象时的提示',
            'failed': '求婚失败时的提示',
            'just_married': '刚刚结婚又尝试结婚时的提示',
            'target_just_married': '对方刚刚结婚时的提示',
            'divorce_cooldown': '离婚冷却中提示，支持{hours}{minutes}变量',
            'no_divorce': '没有对象却试图离婚时的提示',
            'divorce_success': '离婚成功时的提示',
            'no_object': '查看对象但今天没有时的提示',
            'master_only': '非主人尝试设置概率时的提示',
            'master_only_cd': '非主人尝试设置CD时的提示',
            'format_prob': '设置概率命令格式错误时的提示',
            'prob_range': '概率超出0-100范围时的提示',
            'prob_set': '概率设置成功时的提示，支持{rate}变量',
            'format_cd': '设置CD命令格式错误时的提示',
            'cd_non_neg': 'CD为负数时的提示',
            'cd_set': 'CD设置成功时的提示，支持{hours}变量',
            'not_number': '输入不是有效数字时的提示',
        }
        def _add_marry_hints(fields):
            for f in fields:
                if f['k'].startswith('marry_cmd_'):
                    key = f['k'].replace('marry_cmd_', '')
                    f['hint'] = marry_cmd_hints.get(key, '触发该功能的聊天关键词')
                if f['k'].startswith('marry_rep_'):
                    key = f['k'].replace('marry_rep_', '')
                    f['hint'] = marry_rep_hints.get(key, '')
            return fields
        plugins['marry'] = {'name': '结婚插件', 'fields': _add_marry_hints(fields + build_fields_from_cfg(mc, 'marry'))}
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
    if os.path.exists(os.path.join(pd, 'pseudo_persona.py')):
        p = read_json(os.path.join(dd, 'persona_config.json'))
        glm_cfg = p.get('glm', {})
        gemini_cfg = p.get('gemini', {})
        plugins['pseudo'] = {'name': '伪人模式', 'fields': [
            {'k': 'enabled', 'l': '插件开关', 't': 'sel', 'o': ['true', 'false'], 'v': str(p.get('enabled', True)).lower(), 'hint': '关闭后机器人不再主动回复任何消息'},
            {'k': 'current_model', 'l': '当前模型', 't': 'sel', 'o': ['glm', 'gemini'], 'v': p.get('current_model', 'gemini'), 'hint': '选择使用哪个AI模型回复消息'},
            {'k': 'reply_probability', 'l': '主动回复概率', 't': 'num', 'min': 0, 'max': 1, 's': 0.1, 'v': p.get('reply_probability', 1.0), 'hint': '被@或提及时回复的概率，1.0=必定回复'},
            {'k': 'random_reply_probability', 'l': '随机回复概率', 't': 'num', 'min': 0, 'max': 1, 's': 0.1, 'v': p.get('random_reply_probability', 0.0), 'hint': '未被提及时主动插话的概率，0=不主动说话'},
            {'k': 'split_count', 'l': '消息拆分数量', 't': 'num', 'min': 1, 'v': p.get('split_count', 3), 'hint': 'AI回复含|#|#|时分段发送，最多拆成这么多条'},
            {'k': 'split_delay_min', 'l': '拆分最小延迟(秒)', 't': 'num', 'min': 0, 'v': p.get('split_delay_min', 1), 'hint': '分段发送时每条消息之间的最短间隔'},
            {'k': 'split_delay_max', 'l': '拆分最大延迟(秒)', 't': 'num', 'min': 1, 'v': p.get('split_delay_max', 3), 'hint': '分段发送时每条消息之间的最长间隔'},
            {'k': 'max_history', 'l': '最大历史记录', 't': 'num', 'min': 1, 'v': p.get('max_history', 50), 'hint': '每个聊天窗口最多保留的消息条数，超出后删除最早的'},
            {'k': 'context_window', 'l': '上下文窗口', 't': 'num', 'min': 1, 'v': p.get('context_window', 20), 'hint': '每次发送给AI的最近消息数量，越大越费钱但上下文更完整'},
            {'k': 'glm_api_url', 'l': 'GLM API地址', 't': 'text', 'v': glm_cfg.get('api_url', ''), 'hint': 'GLM模型兼容OpenAI格式的API地址'},
            {'k': 'glm_api_key', 'l': 'GLM API密钥', 't': 'password', 'v': glm_cfg.get('api_key', ''), 'hint': '调用GLM接口的身份凭证，请保密'},
            {'k': 'glm_model', 'l': 'GLM 模型名', 't': 'text', 'v': glm_cfg.get('model', 'glm-4v-flash'), 'hint': '选择的GLM具体模型名称，如glm-4v-flash'},
            {'k': 'gemini_api_url', 'l': 'Gemini API地址', 't': 'text', 'v': gemini_cfg.get('api_url', ''), 'hint': 'Gemini模型兼容OpenAI格式的API地址'},
            {'k': 'gemini_api_key', 'l': 'Gemini API密钥', 't': 'password', 'v': gemini_cfg.get('api_key', ''), 'hint': '调用Gemini接口的身份凭证，请保密'},
            {'k': 'gemini_model', 'l': 'Gemini 模型名', 't': 'text', 'v': gemini_cfg.get('model', 'gemini-2.5-flash'), 'hint': '选择的Gemini具体模型名称，如gemini-2.5-flash-preview-05-20'},
            {'k': 'temperature', 'l': 'AI 温度(temperature)', 't': 'num', 'min': 0, 'max': 2, 's': 0.1, 'v': p.get('temperature', 0.8), 'hint': 'AI创造力，0=精确保守，1=平衡，2=天马行空'},
            {'k': 'max_tokens', 'l': 'AI 最大输出(max_tokens)', 't': 'num', 'min': 1, 'v': p.get('max_tokens', 500), 'hint': 'AI单次回复最多生成的字数，越长越耗时'},
            {'k': 'api_timeout', 'l': 'API 超时(秒)', 't': 'num', 'min': 10, 'v': p.get('api_timeout', 90), 'hint': '请求AI接口的最大等待秒数，超时后自动切换备用模型'},
            {'k': 'user_persona', 'l': '用户人设(角色设定)', 't': 'textarea', 'v': p.get('user_persona', ''), 'hint': '自定义角色设定，用于修改AI的性格和说话风格，留空使用默认机器人提示词'},
        ] + [{'k': 'cmd_' + k, 'l': '指令「' + k + '」', 't': 'text', 'v': v, 'hint': {
    'enable': '开启/关闭伪人模式的触发词',
    'disable': '开启/关闭伪人模式的触发词',
    'switch_glm': '切换AI模型为GLM',
    'switch_glm_alt': '切换AI模型为GLM（备选指令）',
    'switch_gemini': '切换AI模型为Gemini',
    'switch_gemini_alt': '切换AI模型为Gemini（备选指令）',
    'current_model': '查看当前使用的AI模型',
    'current_model_alt': '查看当前AI模型（备选指令）',
    'clear_history': '清除当前聊天的对话历史',
    'clear_history_alt': '清除当前聊天历史（备选指令）',
    'clear_history_alt2': '清除当前聊天历史（备选指令）',
    'clear_all': '清除所有群/私聊的对话历史',
    'clear_all_alt': '清除所有聊天历史（备选指令）',
    'clear_all_alt2': '清除所有聊天历史（备选指令）',
}.get(k, '触发该功能的聊天关键词')} for k, v in p.get('commands', {}).items()] + [{'k': 'msg_' + k, 'l': '回复「' + k + '」', 't': 'textarea' if len(v) > 20 else 'text', 'v': v, 'hint': {
            'switch_glm': '切换到GLM模型成功时的回复',
            'switch_gemini': '切换到Gemini模型成功时的回复',
            'current_model': '查看当前模型时的回复，支持{model}变量',
            'history_cleared': '清除当前会话历史成功时的回复',
            'all_history_cleared': '清除所有历史成功时的回复',
            'no_reply': 'AI没有返回内容时的保底回复',
            'whats_up': '被@但没有输入文字时的回复',
            'check_image': '被@并发了图片但没有文字时的回复',
        }.get(k, '')} for k, v in p.get('messages', {}).items()]}
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
        elif plugin == 'pseudo':
            old = read_json(os.path.join(dd, 'persona_config.json'))
            for k, v in cfg.items():
                if k.startswith('msg_'):
                    old.setdefault('messages', {})[k.replace('msg_', '')] = v
                elif k.startswith('cmd_'):
                    old.setdefault('commands', {})[k.replace('cmd_', '')] = v
                elif k == 'enabled':
                    old['enabled'] = v == 'true'
                elif k in ('reply_probability', 'random_reply_probability', 'max_history', 'context_window', 'split_count', 'split_delay_min', 'split_delay_max', 'temperature', 'max_tokens', 'api_timeout'):
                    old[k] = float(v) if '.' in str(v) else int(v)
                elif k.startswith('glm_'):
                    old.setdefault('glm', {})[k.replace('glm_', '')] = v
                elif k.startswith('gemini_'):
                    old.setdefault('gemini', {})[k.replace('gemini_', '')] = v
                elif k in ('user_persona', 'current_model'):
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

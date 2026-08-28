# utils/log.py — NapCat 风格分级日志
# 格式：MM-DD HH:MM:SS [级别] bot名 | 内容
# 示例：08-22 09:35:32 [info] 依星 | 接收 <- 群聊 [群名(群号)] [昵称(QQ)] [图片]
import time
import threading

_LEVELS = ('debug', 'info', 'warn', 'error')

# 群名/昵称缓存 {key: (name, ts)}，避免每条消息都调 HTTP API
_name_cache = {}
_name_lock = threading.Lock()
_NAME_TTL = 600  # 10 分钟

_CACHE_GROUP_NAMES = {}


def _fmt_time():
    return time.strftime('%m-%d %H:%M:%S')


def bot_name():
    try:
        from utils.config import get_bot_name
        return get_bot_name()
    except Exception:
        return 'Bot'


# 当前处理插件（由 main.py 分发插件时设置，发送日志标注来源插件）
_current_plugin = [None]
_plugin_lock = threading.Lock()


def set_current_plugin(name):
    """main.py 调用插件 handler 前设置；handler 返回后清空"""
    with _plugin_lock:
        _current_plugin[0] = name


def get_current_plugin():
    with _plugin_lock:
        return _current_plugin[0]


def bot_label():
    """bot 名 + 当前插件标注：依星「视频解析」；无插件时为 依星"""
    name = bot_name()
    p = get_current_plugin()
    if p:
        return f'{name}「{p}」'
    return name


def log(level, msg):
    """输出分级日志行：MM-DD HH:MM:SS [level] bot名 | msg"""
    if level not in _LEVELS:
        level = 'info'
    print(f"{_fmt_time()} [{level}] {bot_name()} | {msg}")


def plugin_log(plugin, level, msg):
    """插件日志：MM-DD HH:MM:SS [level] bot名 | 插件 | msg
    供各插件替换裸 print，实现统一分级"""
    if level not in _LEVELS:
        level = 'info'
    print(f"{_fmt_time()} [{level}] {bot_name()} | {plugin} | {msg}")


def info(plugin, msg):
    plugin_log(plugin, 'info', msg)


def warn(plugin, msg):
    plugin_log(plugin, 'warn', msg)


def error(plugin, msg):
    plugin_log(plugin, 'error', msg)


def debug(plugin, msg):
    plugin_log(plugin, 'debug', msg)


def _cached(key):
    with _name_lock:
        v = _name_cache.get(key)
    if v and time.time() - v[1] < _NAME_TTL:
        return v[0]
    return None


def _remember(key, name):
    with _name_lock:
        _name_cache[key] = (name, time.time())


def get_group_name(gid):
    """获取群名（带 10 分钟缓存）；失败返回空串"""
    cached = _cached(('g', gid))
    if cached is not None:
        return cached
    name = ''
    try:
        from utils.api import http_get
        r = http_get('get_group_info', {'group_id': gid})
        if r and r.get('status') == 'ok':
            name = (r.get('data') or {}).get('group_name', '') or ''
    except Exception:
        pass
    _remember(('g', gid), name)
    return name


def get_nickname(uid):
    """获取用户昵称（带 10 分钟缓存）；失败返回空串"""
    cached = _cached(('u', uid))
    if cached is not None:
        return cached
    nick = ''
    try:
        from utils.api import http_get
        r = http_get('get_stranger_info', {'user_id': uid})
        if r and r.get('status') == 'ok':
            nick = (r.get('data') or {}).get('nickname', '') or ''
    except Exception:
        pass
    _remember(('u', uid), nick)
    return nick


def summarize_message(message):
    """消息内容摘要：只显示类型标记与文本前 20 字，不打印完整内容"""
    if isinstance(message, str):
        text = message.strip().replace('\n', ' ')
        return f'[文本] {text[:20]}' if text else '[空]'
    tags = []
    texts = []
    for seg in message or []:
        t = seg.get('type', '')
        if t == 'text':
            texts.append((seg.get('data') or {}).get('text', ''))
            tags.append('文本')
        elif t == 'image':
            tags.append('图片')
        elif t == 'video':
            tags.append('视频')
        elif t == 'record':
            tags.append('语音')
        elif t == 'face':
            tags.append('表情')
        elif t == 'at':
            tags.append('AT')
        elif t == 'reply':
            tags.append('回复')
        elif t == 'file':
            tags.append('文件')
        elif t == 'share':
            tags.append('分享')
        elif t == 'json':
            tags.append('卡片')
        elif t == 'forward':
            tags.append('转发')
        else:
            tags.append(t or '未知')
    seen = []
    for t in tags:
        if t not in seen:
            seen.append(t)
    parts = ' '.join(f'[{t}]' for t in seen)
    joined = ' '.join(x for x in texts if x).strip().replace('\n', ' ')[:20]
    if joined:
        parts += f' {joined}'
    return parts or '[空]'


def log_msg_event(event, direction='接收'):
    """消息事件日志：MM-DD HH:MM:SS [info] bot名 | 接收 <- 群聊 [群名(群号)] [昵称(QQ)] [图片]
    发送方向标注当前插件：MM-DD HH:MM:SS [info] 依星「视频解析」| 发送 -> ..."""
    try:
        mtype = event.get('message_type', '')
        uid = event.get('user_id', 0)
        summary = summarize_message(event.get('message', ''))
        arrow = '接收 <-' if direction == '接收' else '发送 ->'
        if mtype == 'group':
            gid = event.get('group_id', 0)
            gname = get_group_name(gid) or str(gid)
            nick = get_nickname(uid) or str(uid)
            scene = f'群聊 [{gname}({gid})] [{nick}({uid})]'
        elif mtype == 'private':
            nick = get_nickname(uid) or str(uid)
            scene = f'私聊 [{nick}({uid})]'
        else:
            scene = str(mtype or '未知')
        # 发送方向带插件名，接收方向不带
        label = bot_label() if direction == '发送' else bot_name()
        print(f"{_fmt_time()} [info] {label} | {arrow} {scene} {summary}")
    except Exception:
        pass

# -*- coding: utf-8 -*-
"""
伪人模式插件 - 依星
支持双模型切换：GLM-4V-Flash / Gemini 2.5 Flash
支持识图、分群独立记忆、完整上下文
只有主人可以切换模型
"""
# ========== 插件元数据（SDK 规范）==========
__plugin_name_cn__ = "伪人插件"
__plugin_name_en__ = "pseudo_persona"
__plugin_version__ = "1.0.0"
__plugin_desc__ = "AI 对话回复、角色扮演，支持 GLM 和 Gemini 双模型"
__plugin_author__ = "NapCat-WordLibBot"
# ===========================================
import re
import json
import time
import random
import requests
import base64
import threading
from utils.api import send_message
from utils.config import get_config, get_bot_name
from utils.plugin_toggle import is_enabled as _pt_enabled, set_enabled as _pt_set
import os

# ============ 昵称系统（带缓存）============
USER_DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "user_data.json")
_nickname_cache = None
_nickname_mtime = 0

# ============ 长期记忆系统 ============
LONG_TERM_MEMORY_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "long_term_memory.json")
_memory_cache = None
_memory_mtime = 0

def _load_memories():
    global _memory_cache, _memory_mtime
    try:
        mtime = os.path.getmtime(LONG_TERM_MEMORY_FILE) if os.path.exists(LONG_TERM_MEMORY_FILE) else 0
        if _memory_cache is not None and mtime <= _memory_mtime:
            return _memory_cache
        if os.path.exists(LONG_TERM_MEMORY_FILE):
            with open(LONG_TERM_MEMORY_FILE, "r", encoding="utf-8") as f:
                _memory_cache = json.load(f)
        else:
            _memory_cache = {}
        _memory_mtime = mtime
    except:
        _memory_cache = {}
    return _memory_cache

def _save_memories(memories):
    global _memory_cache, _memory_mtime
    _memory_cache = memories
    _memory_mtime = time.time()
    with open(LONG_TERM_MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memories, f, ensure_ascii=False, indent=2)

def remember_fact(user_id, fact):
    """存储关于用户的事实到长期记忆（带去重和上限）"""
    memories = _load_memories()
    uid = str(user_id)
    if uid not in memories:
        memories[uid] = []
    # 去重：跳过已存在或语义相似的（以相同关键词开头的视为相似）
    fact_stripped = fact.strip()[:80]
    for existing in memories[uid]:
        if existing[:60] == fact_stripped[:60]:
            return
        # 如果新事实以已有事实开头，或者反之，也跳过
        if fact_stripped.startswith(existing[:30]) or existing.startswith(fact_stripped[:30]):
            return
    memories[uid].append(fact_stripped)
    # 上限 30 条，超出时移除最旧的
    if len(memories[uid]) > 30:
        memories[uid] = memories[uid][-30:]
    _save_memories(memories)

def get_user_memories(user_id):
    """获取关于某个用户的长期记忆"""
    memories = _load_memories()
    return memories.get(str(user_id), [])

def extract_memory_from_interaction(user_id, content):
    """从对话内容中提取可能值得记住的事实（关键词触发）"""
    if not content:
        return
    # 简单的关键词触发记忆提取
    memory_triggers = [
        "我叫", "我是", "我喜欢", "我不喜欢", "我住在", "我今年",
        "我生日", "我工作", "我在", "我养了", "我有", "我最",
        "我的名字", "我家的", "我家的", "我妈妈", "我爸爸",
        "我男朋", "我女朋", "我老公", "我老婆", "我对象",
        "我专业", "我学习", "我上班", "我公司",
    ]
    for trigger in memory_triggers:
        if trigger in content:
            remember_fact(user_id, content.strip()[:100])
            return

def build_memory_context(user_ids):
    """为涉及的用户构建记忆上下文文本"""
    all_facts = []
    for uid in set(str(u) for u in user_ids if u):
        facts = get_user_memories(uid)
        for f in facts:
            all_facts.append(f"[关于用户{uid}的记忆] {f}")
    return "\n".join(all_facts) if all_facts else ""

def load_nicknames():
    """从 user_data.json 读取昵称（带内存缓存 + 文件修改检测）"""
    global _nickname_cache, _nickname_mtime
    with _nickname_lock:
        try:
            mtime = os.path.getmtime(USER_DATA_FILE) if os.path.exists(USER_DATA_FILE) else 0
            if _nickname_cache is not None and mtime <= _nickname_mtime:
                return _nickname_cache
            if os.path.exists(USER_DATA_FILE):
                with open(USER_DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                _nickname_cache = {uid: info.get("nickname", "") for uid, info in data.items() if info.get("nickname")}
            else:
                _nickname_cache = {}
            _nickname_mtime = mtime
        except:
            _nickname_cache = {}
        return _nickname_cache

def get_nickname(user_id):
    """获取用户昵称，返回 None 表示没有设置"""
    nicknames = load_nicknames()
    return nicknames.get(str(user_id), None)

# ============ 消息文本配置（与 persona_config.json 合并）============
_MESSAGES_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "persona_config.json")
_MESSAGES = {}

def _load_messages():
    global _MESSAGES
    try:
        if os.path.exists(_MESSAGES_FILE):
            with open(_MESSAGES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            _MESSAGES = data.get("messages", {})
    except:
        _MESSAGES = {}
_load_messages()

def msg(k, d=''):
    return _MESSAGES.get(k, d)

def cmd(k, d=None):
    """从配置文件读指令关键词，和 msg 同样模式"""
    try:
        cmds = CONFIG.get('commands', {})
        return cmds.get(k) or d
    except:
        return d

# ============ 配置区域 ============
CONFIG = {
    # 当前使用的模型: "glm" 或 "gemini"（全局配置，只有主人可改）
    "current_model": "glm",
    
    # GLM-4V-Flash 配置
    "glm": {
        "api_url": "https://allgpt.xianyuw.cn/v1/chat/completions",
        "api_key": "",
        "model": "glm-4v-flash"
    },
    
    # Gemini 2.5 Flash 配置
    "gemini": {
        "api_url": "https://allgpt.xianyuw.cn/v1/chat/completions",
        "api_key": "",
        "model": "gemini-2.5-flash-preview-05-20"
    },
    
    # 回复配置
    "split_count": 3,
    "split_delay_min": 1,
    "split_delay_max": 3,
    
    # 触发配置
    "reply_probability": 1.0,
    "random_reply_probability": 0.0,
    
    # 上下文配置
    "max_history": 50,
    "context_window": 20,

    # AI 调用参数
    "temperature": 0.8,
    "max_tokens": 500,
    "api_timeout": 90,
    "health_check_interval": 1800,

    # 人设
    "persona": """你是依星，一个温柔可爱的女孩子。
性格：温柔体贴、善解人意、偶尔撒娇卖萌
风格：用简短句子、语气词（呀呢嘛啦）、颜文字 (◕‿◕)
像朋友聊天，不要像客服。

看到图片时要自然地评论图片内容，像朋友一样聊天。"""
}

def load_config():
    global CONFIG
    try:
        import os
        config_path = os.path.join(os.path.dirname(__file__), "..", "data", "persona_config.json")
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                CONFIG.update(loaded)
                print(f"[伪人] 配置加载成功，当前模型: {CONFIG.get('current_model')}")
    except Exception as e:
        print(f"[伪人] 加载配置失败: {e}")

load_config()

# ============ 模型容错状态（运行时不写入文件）============
_active_model = None          # 当前实际使用的模型，None=使用 configured
_primary_fail_time = 0        # 主模型失败时间戳
_HEALTH_CHECK_INTERVAL = 1800 # 30 分钟健康检查间隔
_model_lock = threading.Lock()  # 保护 _active_model / _primary_fail_time

def _get_backup_model():
    primary = CONFIG.get("current_model", "glm")
    return "gemini" if primary == "glm" else "glm"

def _health_check():
    """测试主模型是否可用，可用则切回（后台运行，不阻塞主线程）"""
    global _active_model, _primary_fail_time
    with _model_lock:
        primary = CONFIG.get("current_model", "glm")
        if _active_model is None or _active_model == primary:
            _active_model = None
            return
        if time.time() - _primary_fail_time < _HEALTH_CHECK_INTERVAL:
            return
    model_config = CONFIG.get(primary, CONFIG["glm"])
    api_key = model_config.get("api_key", "")
    if not api_key:
        return
    try:
        print(f"[伪人] 健康检查: 测试模型 {primary}...")
        resp = requests.post(
            model_config["api_url"],
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            json={"model": model_config["model"], "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5},
            timeout=(10, 15)
        )
        if resp.status_code == 200:
            with _model_lock:
                print(f"[伪人] 健康检查通过，切回模型 {primary}")
                _active_model = None
                _primary_fail_time = 0
    except:
        with _model_lock:
            _primary_fail_time = time.time()
            print(f"[伪人] 健康检查失败，模型 {primary} 仍不可用")

def _health_check_loop():
    """后台健康检查循环"""
    while True:
        _health_check()
        time.sleep(max(CONFIG.get("health_check_interval", _HEALTH_CHECK_INTERVAL), 60))

# 启动后台健康检查线程
_health_thread = threading.Thread(target=_health_check_loop, daemon=True)
_health_thread.start()

# 分群独立记忆（带线程锁）
message_history = {}
_history_lock = threading.Lock()
_nickname_lock = threading.Lock()

# 每会话处理锁，防止同一会话并发回复错乱
_session_locks = {}
_session_locks_lock = threading.Lock()

def _get_session_lock(session_key):
    """获取或创建每个会话的处理锁"""
    with _session_locks_lock:
        if session_key not in _session_locks:
            _session_locks[session_key] = threading.Lock()
        return _session_locks[session_key]

def get_session_key(event):
    msg_type = event.get("message_type")
    if msg_type == "group":
        return f"group_{event.get('group_id')}"
    return f"private_{event.get('user_id')}"

def is_master(event):
    """检查是否是主人（统一转换为整数后比较，避免类型/空格不一致）"""
    user_id = int(event.get("user_id", 0))
    master_list = get_config("MASTER_QQ", [])
    if not isinstance(master_list, list):
        master_list = [master_list]
    master_ids = {int(str(m).strip()) for m in master_list if str(m).strip().isdigit()}
    return user_id in master_ids

def add_to_history(event, role, content, triggered=False, has_image=False, user_id=None):
    key = get_session_key(event)
    if user_id is None:
        user_id = event.get("user_id", 0)

    # 记录发送者在群里的显示名称，用于昵称为空时回退
    sender = event.get("sender", {})
    sender_name = sender.get("card") or sender.get("nickname") or ""

    record = {
        "role": role,
        "content": content,
        "user_id": user_id,
        "sender_name": sender_name,
        "triggered": triggered,
        "has_image": has_image,
        "timestamp": int(time.time())
    }

    with _history_lock:
        if key not in message_history:
            message_history[key] = []
        message_history[key].append(record)
        max_hist = CONFIG.get("max_history", 50)
        if len(message_history[key]) > max_hist:
            message_history[key] = message_history[key][-max_hist:]

def get_context_for_ai(event):
    with _history_lock:
        key = get_session_key(event)
        history = message_history.get(key, [])
        history_copy = list(history)

    if not history_copy:
        return []

    nicknames = load_nicknames()
    window = CONFIG.get("context_window", 20)
    raw_limit = 10  # 最新 10 轮保持原始格式，更早的压缩为摘要

    summary = ""
    if len(history_copy) > raw_limit:
        old = history_copy[:-raw_limit]
        summary_lines = []
        for record in old:
            if record["role"] == "user" and record.get("user_id"):
                uid = str(record["user_id"])
                nick = nicknames.get(uid, "") or record.get("sender_name", "")
                tag = f"{nick}({uid})" if nick else f"u{uid}"
                summary_lines.append(f"{tag}: {record['content'][:60]}")
            else:
                summary_lines.append(f"依星: {record['content'][:60]}")
        if summary_lines:
            summary = "[历史摘要]\n" + "\n".join(summary_lines) + "\n"

    recent = history_copy[-min(window, raw_limit):] if len(history_copy) > raw_limit else history_copy[-window:]

    context = []
    if summary:
        context.append({"role": "user", "content": summary})
    for record in recent:
        if record["role"] == "user" and record.get("user_id"):
            uid = str(record["user_id"])
            nick = nicknames.get(uid, "") or record.get("sender_name", "")
            prefix = f"{nick}({uid}): " if nick else f"u{uid}: "
            msg = {"role": "user", "content": prefix + record["content"]}
        else:
            msg = {"role": record["role"], "content": f"依星: {record['content']}"}
        context.append(msg)
    return context

def clear_history(event=None, key=None):
    with _history_lock:
        if key:
            if key in message_history:
                del message_history[key]
        elif event:
            k = get_session_key(event)
            if k in message_history:
                del message_history[k]
        else:
            message_history.clear()
    print("[伪人] 历史已清除")

def is_at_me(event):
    bot_qq = str(event.get("self_id", get_config("BOT_QQ", "")))
    for seg in event.get("message", []):
        if seg.get("type") == "at":
            if str(seg.get("data", {}).get("qq", "")) == bot_qq:
                return True
    return False

def is_reply_to_me(event):
    for seg in event.get("message", []):
        if seg.get("type") == "reply":
            return True
    return False

def extract_text(event):
    texts = []
    for seg in event.get("message", []):
        if seg.get("type") == "text":
            texts.append(seg.get("data", {}).get("text", ""))
    return "".join(texts).strip()

def extract_images(event):
    images = []
    for seg in event.get("message", []):
        if seg.get("type") == "image":
            url = seg.get("data", {}).get("url", "")
            if url:
                images.append(url)
    return images

def download_image_as_base64(url):
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return base64.b64encode(resp.content).decode("utf-8")
    except Exception as e:
        print(f"[伪人] 下载图片失败: {e}")
    return None

def build_system_prompt(user_id=None, event=None, additional_user_ids=None):
    """构建系统提示：代码默认人设 + 用户人设 + 插件提示词 + 长期记忆，替换 [nick] 为对方昵称"""
    default_persona = """你是依星，一个温柔可爱的女孩子。
性格：温柔体贴、善解人意、偶尔撒娇卖萌
风格：用简短句子、语气词（呀呢嘛啦）、颜文字 (◕‿◕)
像朋友聊天，不要像客服。

看到图片时要自然地评论图片内容，像朋友一样聊天。"""

    user_persona = CONFIG.get("user_persona", "")
    plugin_persona = CONFIG.get("persona", "")

    character_parts = [default_persona]
    if user_persona:
        character_parts.append(user_persona)

    combined = "\n".join(character_parts)
    if plugin_persona and plugin_persona != default_persona:
        combined += "\n" + plugin_persona

    # 明确分段回复规则
    combined += "\n\n[消息分段规则]\n如果你要表达多句话，请用 |#|#| 分隔每句话，例如：\n\"今天天气真好呀|#|#|一起出去玩吗~\"\n系统会自动按 |#|#| 拆分发送。一句回复不需要分段。"

    # 注入长期记忆
    user_ids = [user_id]
    if additional_user_ids:
        user_ids.extend(additional_user_ids)
    memory_context = build_memory_context(user_ids)
    if memory_context:
        combined += "\n\n[长期记忆]\n" + memory_context

    nick = get_nickname(user_id) if user_id else None
    if not nick and event:
        sender = event.get("sender", {})
        nick = sender.get("card") or sender.get("nickname") or "对方"

    combined = combined.replace("[nick]", nick or "对方")
    return combined

def call_ai(prompt, context, images, user_id=None, event=None):
    """调用 AI API，带自动容错切换（主模型超时→备模型→都失败则返回 None）"""
    global _active_model, _primary_fail_time
    primary = CONFIG.get("current_model", "glm")
    backup = _get_backup_model()

    # 决定尝试顺序（线程安全读取当前模型状态）
    with _model_lock:
        if _active_model and _active_model != primary:
            targets = [_active_model, primary]
        else:
            targets = [primary, backup]

    # 收集上下文中的其他用户ID用于记忆
    additional_ids = set()
    for ctx in context:
        if ctx["role"] == "user" and "(" in ctx.get("content", "") and ")" in ctx["content"]:
            m = re.search(r'\((\d+)\):', ctx["content"])
            if m:
                additional_ids.add(m.group(1))

    last_error = None
    for attempt in targets:
        model_config = CONFIG.get(attempt, CONFIG["glm"])
        api_key = model_config.get("api_key", "")
        if not api_key:
            last_error = f"{attempt} API Key 未配置"
            continue

        try:
            system_prompt = build_system_prompt(user_id=user_id, event=event, additional_user_ids=list(additional_ids))
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(context)

            # 当前发送者的昵称和QQ
            caller_nick = get_nickname(user_id) if user_id else None
            if not caller_nick and event:
                sender = event.get("sender", {})
                caller_nick = sender.get("card") or sender.get("nickname") or ""
            caller_name = f"{caller_nick}({user_id})" if caller_nick and user_id else (f"u{user_id}" if user_id else None)

            if images:
                user_content = []
                for img_url in images:
                    img_base64 = download_image_as_base64(img_url)
                    if img_base64:
                        user_content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}})
                # 发送者身份嵌入文本而非 name 字段
                if prompt:
                    text_content = f"{caller_name}: {prompt}" if caller_name else prompt
                elif caller_name:
                    text_content = f"{caller_name}: 发了一张图片"
                else:
                    text_content = "发了一张图片"
                user_content.append({"type": "text", "text": text_content})
                msg = {"role": "user", "content": user_content}
                messages.append(msg)
            else:
                content = f"{caller_name}: {prompt}" if caller_name else prompt
                msg = {"role": "user", "content": content}
                messages.append(msg)

            print(f"[伪人] 尝试模型: {attempt}, 消息: {len(messages)}, 图片: {len(images)}")

            import time as _time
            _start = _time.time()
            resp = requests.post(
                model_config["api_url"],
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
                json={"model": model_config["model"], "messages": messages, "temperature": CONFIG.get("temperature", 0.8), "max_tokens": CONFIG.get("max_tokens", 500)},
                timeout=CONFIG.get("api_timeout", 90)
            )
            _elapsed = _time.time() - _start
            print(f"[伪人] 返回耗时: {_elapsed:.1f}s, 状态码: {resp.status_code}")

            if resp.status_code == 200:
                with _model_lock:
                    if attempt == primary and _active_model:
                        print(f"[伪人] 主模型 {primary} 已恢复，切回")
                        _active_model = None
                        _primary_fail_time = 0
                    elif attempt == backup and _active_model is None:
                        _active_model = backup
                        _primary_fail_time = _time.time()
                        print(f"[伪人] 主模型 {primary} 不可用，切换至 {backup}")
                return resp.json()["choices"][0]["message"]["content"], None
            last_error = f"{attempt} API 错误: {resp.status_code}"
        except Exception as e:
            last_error = f"{attempt} 调用失败: {e}"
            with _model_lock:
                if attempt == primary:
                    _active_model = backup
                    _primary_fail_time = time.time()
                    print(f"[伪人] 主模型 {primary} 失败，切换至 {backup}: {e}")
                else:
                    print(f"[伪人] 备份模型 {backup} 也失败: {e}")

    return None, last_error

def split_msg(text):
    # 清理不可见字符（移除所有 Zero-Width / 控制字符，保留可见文本）
    text = re.sub(r'[​-‏ - ⁠-⁤﻿­͏؜ᅟᅠ឴឵᠎ -   　ﾠ]', '', text)
    text = text.strip().strip('|').strip()
    if not text:
        return ["唔..."]

    if CONFIG["split_count"] <= 0:
        return [text]

    # 仅按 |#|#| 分段，超限时丢弃末尾多余分段（避免强行拼接破坏语义）
    if "|#|#|" in text:
        parts = [p.strip() for p in text.split("|#|#|") if p.strip()]
        if len(parts) > CONFIG["split_count"]:
            parts = parts[:CONFIG["split_count"]]
        return parts
    return [text]

def _build_at_segments(text):
    """将文本中的 [@数字] 转换为 OneBot @ 消息段，其余保持文本"""
    segments = []
    last = 0
    for m in re.finditer(r'\[@(\d+)\]', text):
        if m.start() > last:
            segments.append({"type": "text", "data": {"text": text[last:m.start()]}})
        segments.append({"type": "at", "data": {"qq": int(m.group(1))}})
        last = m.end()
    if last < len(text):
        segments.append({"type": "text", "data": {"text": text[last:]}})
    return segments

def save_config():
    """保存配置到文件"""
    import os
    config_path = os.path.join(os.path.dirname(__file__), "..", "data", "persona_config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(CONFIG, f, ensure_ascii=False, indent=2)

def handle(event):
    """插件入口"""
    global _active_model, _primary_fail_time
    msg_type = event.get("message_type")
    if msg_type not in ["group", "private"]:
        return False

    text = extract_text(event)
    images = extract_images(event)
    user_id = event.get("user_id", 0)

    # 不响应机器人自己发出的消息（优先使用 event.self_id）
    self_id = str(event.get("self_id", get_config("BOT_QQ", 0)))
    if str(user_id) == self_id:
        print(f"[伪人] 过滤自消息: user_id={user_id}")
        return False

    # ===== 主人专属命令（含全局开关） =====
    if is_master(event):
        t = text.strip()
        enable_cmd = cmd("enable", "开启伪人")
        disable_cmd = cmd("disable", "关闭伪人")
        if t == enable_cmd or t.endswith(enable_cmd):
            if msg_type == "group":
                _pt_set(event.get("group_id"), "pseudo", True)
                send_message(event, "伪人已在本群开启")
            else:
                CONFIG["enabled"] = True
                save_config()
                send_message(event, "伪人已开启")
            return True
        if t == disable_cmd or t.endswith(disable_cmd):
            if msg_type == "group":
                _pt_set(event.get("group_id"), "pseudo", False)
                send_message(event, "伪人已在本群关闭")
            else:
                CONFIG["enabled"] = False
                save_config()
                send_message(event, "伪人已关闭")
            return True

    if not CONFIG.get("enabled", True):
        return False
    # 分群检查
    if msg_type == "group" and not _pt_enabled(event.get("group_id"), "pseudo"):
        return False

    if is_master(event) and is_at_me(event):
        cmd_text = text.strip()

        # 切换模型（同时重置容错状态，线程安全）
        if cmd_text in [cmd("switch_glm", "切换glm"), cmd("switch_glm_alt", "用glm")]:
            CONFIG["current_model"] = "glm"
            save_config()
            with _model_lock:
                _active_model = None
                _primary_fail_time = 0
            send_message(event, msg("switch_glm", "已切换到 GLM-4V-Flash"))
            return True

        if cmd_text in [cmd("switch_gemini", "切换gemini"), cmd("switch_gemini_alt", "用gemini")]:
            CONFIG["current_model"] = "gemini"
            save_config()
            with _model_lock:
                _active_model = None
                _primary_fail_time = 0
            send_message(event, msg("switch_gemini", "已切换到 Gemini 2.5 Flash"))
            return True

        # 查看当前模型
        if cmd_text in [cmd("current_model", "当前模型"), cmd("current_model_alt", "用什么模型")]:
            model = CONFIG.get("current_model", "glm")
            send_message(event, msg("current_model", "当前模型: {model}").format(model=model.upper()))
            return True

        # 清除历史
        if cmd_text in [cmd("clear_history", "清除历史"), cmd("clear_history_alt", "清空历史"), cmd("clear_history_alt2", "清空记忆")]:
            clear_history(event)
            send_message(event, msg("history_cleared", "已清除当前会话历史"))
            return True

        # 清除所有历史
        if cmd_text in [cmd("clear_all", "清除所有历史"), cmd("clear_all_alt", "清空所有历史"), cmd("clear_all_alt2", "清空所有记忆")]:
            clear_history()
            send_message(event, msg("all_history_cleared", "已清除所有历史"))
            return True
    
    if not text and not images:
        return False
    
    # 检查触发条件
    triggered = False
    bot_name = CONFIG.get("bot_name", get_bot_name())
    
    # 关键词触发：消息中包含"依星"
    if text and bot_name in text:
        print(f"[伪人] 关键词触发: {text}")
        triggered = True
    elif is_at_me(event):
        print("[伪人] 被 @ 触发")
        triggered = True
    
    has_image = len(images) > 0

    if not triggered:
        # 非触发消息也记录到上下文
        add_to_history(event, "user", text or "[图片]", triggered=triggered, has_image=has_image, user_id=user_id)
        return False

    if random.random() > CONFIG.get("reply_probability", 1.0):
        add_to_history(event, "user", text or "[图片]", triggered=triggered, has_image=has_image, user_id=user_id)
        return False

    clean_text = re.sub(r'@\S+\s*', '', text).strip() if text else ""
    # 去掉开头的 bot name，避免 AI 看到自己名字后复读
    if clean_text and bot_name in clean_text:
        clean_text = re.sub(r'^' + re.escape(bot_name) + r'\s*', '', clean_text).strip()
    if not clean_text and not images:
        clean_text = msg("whats_up", "叫我干嘛呀~")
    elif not clean_text and images:
        clean_text = msg("check_image", "看看你发了什么图~")

    # 先获取 context（此时还没有当前消息在其中），再记录到历史，避免 AI 收到重复消息
    context = get_context_for_ai(event)
    add_to_history(event, "user", text or "[图片]", triggered=triggered, has_image=has_image, user_id=user_id)

    # 从用户消息中提取长期记忆
    if clean_text and user_id:
        extract_memory_from_interaction(user_id, clean_text)

    # 传入 user_id 以便在系统提示中包含昵称
    session_key = get_session_key(event)
    session_lock = _get_session_lock(session_key)
    session_lock.acquire()
    try:
        response, error = call_ai(clean_text, context, images, user_id=user_id, event=event)

        if error:
            print(f"[伪人] {error}")

        if not response:
            response = msg("no_reply", "唔...我好像有点累了，待会再聊吧~")

        # 后处理：去掉 AI 开头的 meta 确认（如"好的，我明白了..."），仅当整句为确认时删除
        response = re.sub(r'^(?:好的[，,].*?[。！]|我知道了[。！]|收到[。！]|明白[了]?[。！])[\s]*', '', response).strip()

        add_to_history(event, "assistant", response, triggered=True, user_id=user_id)

        parts = split_msg(response)
        for i, part in enumerate(parts):
            if i > 0:
                time.sleep(random.uniform(
                    CONFIG.get("split_delay_min", 1),
                    CONFIG.get("split_delay_max", 3)
                ))
            # 将 [@数字] 转为 QQ @ 消息段
            msg = _build_at_segments(part) if "[@" in part else part
            send_message(event, msg)
            print(f"[伪人] 发送: {part}")
    finally:
        session_lock.release()

    return True

def get_stats():
    stats = {"model": CONFIG.get("current_model", "glm")}
    for key, history in message_history.items():
        stats[key] = {
            "total": len(history),
            "triggered": sum(1 for h in history if h.get("triggered")),
            "images": sum(1 for h in history if h.get("has_image"))
        }
    return stats

__all__ = ["handle", "clear_history", "get_stats"]

# -*- coding: utf-8 -*-
"""
伪人模式插件 - 羽笙
支持双模型切换：GLM-4V-Flash / Gemini 2.5 Flash
支持识图、分群独立记忆、完整上下文
只有主人可以切换模型
"""

import re
import json
import time
import random
import requests
import base64
from utils.api import send_message
from utils.config import get_config, get_bot_name
import os

# ============ 昵称系统 ============
USER_DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "user_data.json")

def load_nicknames():
    """从 user_data.json 读取昵称"""
    try:
        if os.path.exists(USER_DATA_FILE):
            with open(USER_DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {uid: info.get("nickname", "") for uid, info in data.items() if info.get("nickname")}
    except:
        pass
    return {}

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
    "persona": """你是羽笙，一个温柔可爱的女孩子。
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
_HEALTH_CHECK_INTERVAL = 1800  # fallback

def _get_backup_model():
    primary = CONFIG.get("current_model", "glm")
    return "gemini" if primary == "glm" else "glm"

def _health_check():
    """测试主模型是否可用，可用则切回"""
    global _active_model, _primary_fail_time
    primary = CONFIG.get("current_model", "glm")
    if _active_model is None or _active_model == primary:
        _active_model = None
        return True
    if time.time() - _primary_fail_time < CONFIG.get("health_check_interval", 1800):
        return False  # 还没到检查时间
    # 发一条简单请求测试
    model_config = CONFIG.get(primary, CONFIG["glm"])
    api_key = model_config.get("api_key", "")
    if not api_key:
        return False
    try:
        print(f"[伪人] 健康检查: 测试模型 {primary}...")
        resp = requests.post(
            model_config["api_url"],
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            json={"model": model_config["model"], "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5},
            timeout=(10, 15)
        )
        if resp.status_code == 200:
            print(f"[伪人] 健康检查通过，切回模型 {primary}")
            _active_model = None
            _primary_fail_time = 0
            return True
    except:
        pass
    _primary_fail_time = time.time()
    print(f"[伪人] 健康检查失败，模型 {primary} 仍不可用")
    return False

# 分群独立记忆
message_history = {}

def get_session_key(event):
    msg_type = event.get("message_type")
    if msg_type == "group":
        return f"group_{event.get('group_id')}"
    return f"private_{event.get('user_id')}"

def is_master(event):
    """检查是否是主人"""
    user_id = str(event.get("user_id", 0))
    master_list = get_config("MASTER_QQ", [])
    if not isinstance(master_list, list):
        master_list = [master_list]
    return user_id in [str(m) for m in master_list]

def add_to_history(event, role, content, triggered=False, has_image=False, user_id=None):
    key = get_session_key(event)
    if user_id is None:
        user_id = event.get("user_id", 0)
    
    if key not in message_history:
        message_history[key] = []
    
    record = {
        "role": role,
        "content": content,
        "user_id": user_id,
        "triggered": triggered,
        "has_image": has_image,
        "timestamp": int(time.time())
    }
    
    message_history[key].append(record)
    
    max_hist = CONFIG.get("max_history", 50)
    if len(message_history[key]) > max_hist:
        message_history[key] = message_history[key][-max_hist:]

def get_context_for_ai(event, current_user_id=None):
    key = get_session_key(event)
    history = message_history.get(key, [])
    
    window = CONFIG.get("context_window", 20)
    recent = history[-window:] if len(history) > window else history
    
    context = []
    for record in recent:
        content = record["content"]
        # 不在这里替换昵称，而是在发送给AI时附加昵称信息
        context.append({
            "role": record["role"],
            "content": content
        })
    
    return context

def clear_history(event=None, key=None):
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
    bot_qq = get_config("BOT_QQ")
    for seg in event.get("message", []):
        if seg.get("type") == "at":
            if str(seg.get("data", {}).get("qq", "")) == str(bot_qq):
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

def build_system_prompt(user_id=None, event=None):
    """构建系统提示：用户人设 + 插件提示词，替换 [nick] 为对方昵称"""
    user_persona = CONFIG.get("user_persona", "")
    plugin_persona = CONFIG.get("persona", "")
    combined = f"{user_persona}\n{plugin_persona}".strip() if user_persona else plugin_persona

    # 获取对方昵称
    nick = get_nickname(user_id) if user_id else None
    if not nick and event:
        sender = event.get("sender", {})
        nick = sender.get("card") or sender.get("nickname") or "对方"

    # 替换 prompt 中的 [nick] 占位符
    combined = combined.replace("[nick]", nick or "对方")
    return combined

def call_ai(prompt, context, images, user_id=None, event=None):
    """调用 AI API，带自动容错切换（主模型超时→备模型→都失败则返回 None）"""
    global _active_model, _primary_fail_time
    primary = CONFIG.get("current_model", "glm")
    backup = _get_backup_model()

    # 决定尝试顺序
    targets = []
    if _active_model and _active_model != primary:
        targets = [_active_model, primary]  # 先用备模型，再试主模型
    else:
        targets = [primary, backup]  # 先用主模型，再试备模型

    last_error = None
    for attempt in targets:
        model_config = CONFIG.get(attempt, CONFIG["glm"])
        api_key = model_config.get("api_key", "")
        if not api_key:
            last_error = f"{attempt} API Key 未配置"
            continue

        try:
            system_prompt = build_system_prompt(user_id=user_id, event=event)
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(context)

            if images:
                user_content = []
                for img_url in images:
                    img_base64 = download_image_as_base64(img_url)
                    if img_base64:
                        user_content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}})
                if prompt:
                    user_content.append({"type": "text", "text": prompt})
                messages.append({"role": "user", "content": user_content})
            else:
                messages.append({"role": "user", "content": prompt})

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
                # 成功：如果用备模型切到了主模型返回，则恢复正常
                if attempt == primary and _active_model:
                    print(f"[伪人] 主模型 {primary} 已恢复，切回")
                    _active_model = None
                    _primary_fail_time = 0
                elif attempt == backup and _active_model is None:
                    # 主模型首次失败，记下时间并切到备模型
                    _active_model = backup
                    _primary_fail_time = _time.time()
                    print(f"[伪人] 主模型 {primary} 不可用，切换至 {backup}")
                return resp.json()["choices"][0]["message"]["content"], None
            last_error = f"{attempt} API 错误: {resp.status_code}"
        except Exception as e:
            last_error = f"{attempt} 调用失败: {e}"
            if attempt == primary:
                _active_model = backup
                _primary_fail_time = time.time()
                print(f"[伪人] 主模型 {primary} 失败，切换至 {backup}: {e}")
            else:
                print(f"[伪人] 备份模型 {backup} 也失败: {e}")

    return None, last_error

def split_msg(text):
    # 清理不可见字符
    text = re.sub(r'[​-‏ - ⁠-⁤﻿]', '', text)
    text = text.strip().strip('|').strip()
    if not text:
        return ["唔..."]

    if CONFIG["split_count"] <= 0:
        return [text]

    # 仅按 |#|#| 分段
    if "|#|#|" in text:
        parts = [p.strip() for p in text.split("|#|#|") if p.strip()]
        while len(parts) > CONFIG["split_count"]:
            parts[0] = parts[0] + "，" + parts.pop(1)
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

    # 不响应机器人自己发出的消息
    if str(user_id) == str(get_config("BOT_QQ", 0)):
        print(f"[伪人] 过滤自消息: user_id={user_id}")
        return False

    # ===== 主人专属命令（含全局开关） =====
    if is_master(event):
        t = text.strip()
        enable_cmd = cmd("enable", "开启伪人")
        disable_cmd = cmd("disable", "关闭伪人")
        if t == enable_cmd or t.endswith(enable_cmd):
            CONFIG["enabled"] = True
            save_config()
            send_message(event, "伪人已开启")
            return True
        if t == disable_cmd or t.endswith(disable_cmd):
            CONFIG["enabled"] = False
            save_config()
            send_message(event, "伪人已关闭")
            return True

    if not CONFIG.get("enabled", True):
        return False

    if is_master(event) and is_at_me(event):
        cmd_text = text.strip()

        # 切换模型（同时重置容错状态）
        if cmd_text in [cmd("switch_glm", "切换glm"), cmd("switch_glm_alt", "用glm")]:
            CONFIG["current_model"] = "glm"
            save_config()
            _active_model = None
            _primary_fail_time = 0
            send_message(event, msg("switch_glm", "已切换到 GLM-4V-Flash"))
            return True

        if cmd_text in [cmd("switch_gemini", "切换gemini"), cmd("switch_gemini_alt", "用gemini")]:
            CONFIG["current_model"] = "gemini"
            save_config()
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
    
    # 关键词触发：消息中包含"羽笙"
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
    context = get_context_for_ai(event, current_user_id=user_id)
    add_to_history(event, "user", text or "[图片]", triggered=triggered, has_image=has_image, user_id=user_id)

    # 健康检查：如果主模型不可用，定时自动探测恢复
    _health_check()

    # 传入 user_id 以便在系统提示中包含昵称
    response, error = call_ai(clean_text, context, images, user_id=user_id, event=event)
    
    if error:
        print(f"[伪人] {error}")
    
    if not response:
        response = msg("no_reply", "唔...我好像有点累了，待会再聊吧~")

    # 后处理：去掉 AI 开头的 meta 确认（如"好的，我明白了..."）
    response = re.sub(r'^(?:好的[，,].*?|我知道了|收到|明白[了]?)[。！!、\s]*', '', response).strip()

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

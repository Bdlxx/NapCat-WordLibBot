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
from utils.config import get_config
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

# ============ 消息文本配置 ============
_MESSAGES_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "pseudo_messages.json")
_MESSAGES = {}

def _load_messages():
    global _MESSAGES
    try:
        if os.path.exists(_MESSAGES_FILE):
            with open(_MESSAGES_FILE, "r", encoding="utf-8") as f:
                _MESSAGES = json.load(f)
    except:
        _MESSAGES = {}
_load_messages()

def msg(k, d=''):
    return _MESSAGES.get(k, d)

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

def build_system_prompt_with_nickname(user_id, event=None):
    """构建包含用户昵称的系统提示"""
    base_persona = CONFIG.get("persona", "")
    
    # 优先使用自定义昵称，否则使用 QQ 昵称
    nick = get_nickname(user_id)
    if not nick and event:
        # 从事件中获取 QQ 昵称或群名片
        sender = event.get("sender", {})
        nick = sender.get("card") or sender.get("nickname") or None
    
    if nick:
        # 在人设中明确告诉AI对方的昵称
        nickname_instruction = f"\n\n【当前对话对象的昵称】\n对方的名字是「{nick}」，请在回复中使用这个昵称称呼对方。"
        return base_persona + nickname_instruction
    return base_persona

def call_ai(prompt, context, images, user_id=None, event=None):
    """调用 AI API（统一 OpenAI 格式）"""
    model_name = CONFIG.get("current_model", "glm")
    model_config = CONFIG.get(model_name, CONFIG["glm"])
    api_key = model_config.get("api_key", "")
    
    if not api_key:
        return None, "API Key 未配置"
    
    try:
        # 使用包含昵称的系统提示
        system_prompt = build_system_prompt_with_nickname(user_id, event) if user_id else CONFIG["persona"]
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(context)
        
        if images:
            user_content = []
            for img_url in images:
                img_base64 = download_image_as_base64(img_url)
                if img_base64:
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}
                    })
            if prompt:
                user_content.append({"type": "text", "text": prompt})
            messages.append({"role": "user", "content": user_content})
        else:
            messages.append({"role": "user", "content": prompt})
        
        print(f"[伪人] 模型: {model_name}, 消息: {len(messages)}, 图片: {len(images)}")
        
        resp = requests.post(
            model_config["api_url"],
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            },
            json={
                "model": model_config["model"],
                "messages": messages,
                "temperature": 0.8,
                "max_tokens": 500
            },
            timeout=60
        )
        
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"], None
        return None, f"API 错误: {resp.status_code}"
    except Exception as e:
        return None, f"调用失败: {e}"

def split_msg(text):
    if CONFIG["split_count"] <= 0:
        return [text]
    
    parts = re.split(r'([。！？~]+\s*)', text)
    result = []
    current = ""
    
    for p in parts:
        current += p
        if len(current) > 15 and re.search(r'[。！？~]\s*$', current):
            result.append(current.strip())
            current = ""
    
    if current.strip():
        result.append(current.strip())
    
    while len(result) > CONFIG["split_count"]:
        result[0] = result[0] + result.pop(1)
    
    return result if result else [text]

def save_config():
    """保存配置到文件"""
    import os
    config_path = os.path.join(os.path.dirname(__file__), "..", "data", "persona_config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(CONFIG, f, ensure_ascii=False, indent=2)

def handle(event):
    """插件入口"""
    msg_type = event.get("message_type")
    if msg_type not in ["group", "private"]:
        return False
    
    text = extract_text(event)
    images = extract_images(event)
    user_id = event.get("user_id", 0)
    
    # ===== 主人专属命令 =====
    if is_master(event) and is_at_me(event):
        cmd = text.strip()
        
        # 切换模型
        if cmd in ["切换glm", "用glm"]:
            CONFIG["current_model"] = "glm"
            save_config()
            send_message(event, msg("switch_glm", "已切换到 GLM-4V-Flash"))
            return True
        
        if cmd in ["切换gemini", "用gemini"]:
            CONFIG["current_model"] = "gemini"
            save_config()
            send_message(event, msg("switch_gemini", "已切换到 Gemini 2.5 Flash"))
            return True
        
        # 查看当前模型
        if cmd in ["当前模型", "用什么模型"]:
            model = CONFIG.get("current_model", "glm")
            send_message(event, msg("current_model", "当前模型: {model}").format(model=model.upper()))
            return True
        
        # 清除历史
        if cmd in ["清除历史", "清空历史"]:
            clear_history(event)
            send_message(event, msg("history_cleared", "已清除当前会话历史"))
            return True
        
        # 清除所有历史
        if cmd in ["清除所有历史", "清空所有历史"]:
            clear_history()
            send_message(event, msg("all_history_cleared", "已清除所有历史"))
            return True
    
    if not text and not images:
        return False
    
    # 检查触发条件
    triggered = False
    bot_name = "羽笙"
    
    # 关键词触发：消息中包含"羽笙"
    if text and bot_name in text:
        print(f"[伪人] 关键词触发: {text}")
        triggered = True
    elif is_at_me(event):
        print("[伪人] 被 @ 触发")
        triggered = True
    
    has_image = len(images) > 0
    add_to_history(event, "user", text or "[图片]", triggered=triggered, has_image=has_image, user_id=user_id)
    
    if not triggered:
        return False
    
    if random.random() > CONFIG.get("reply_probability", 1.0):
        return False
    
    clean_text = re.sub(r'@\S+\s*', '', text).strip() if text else ""
    if not clean_text and not images:
        clean_text = msg("whats_up", "叫我干嘛呀~")
    elif not clean_text and images:
        clean_text = msg("check_image", "看看你发了什么图~")
    
    context = get_context_for_ai(event, current_user_id=user_id)
    
    # 传入 user_id 以便在系统提示中包含昵称
    response, error = call_ai(clean_text, context, images, user_id=user_id, event=event)
    
    if error:
        print(f"[伪人] {error}")
    
    if not response:
        response = msg("no_reply", "唔...我好像有点累了，待会再聊吧~")
    
    add_to_history(event, "assistant", response, triggered=True, user_id=user_id)
    
    parts = split_msg(response)
    for i, part in enumerate(parts):
        if i > 0:
            time.sleep(random.uniform(
                CONFIG.get("split_delay_min", 1),
                CONFIG.get("split_delay_max", 3)
            ))
        send_message(event, part)
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

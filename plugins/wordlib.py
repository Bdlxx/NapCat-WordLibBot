import json
import os
import random
import re
import time
import requests
import hashlib
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

# ========== 插件元数据（SDK 规范）==========
__plugin_name_cn__ = "词库插件"
__plugin_name_en__ = "wordlib"
__plugin_version__ = "1.0.0"
__plugin_desc__ = "关键词匹配回复、签到好感度、自定义昵称、排行榜、赞我、转码"
__plugin_author__ = "NapCat-WordLibBot"
# ===========================================

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.api import send_message
from utils.config import get_master_qq, get_bot_qq, get_bot_name
from utils.plugin_toggle import is_enabled as _pt_enabled, set_enabled as _pt_set

# ========== 配置 ==========
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)

WORD_DATA_FILE = os.path.join(DATA_DIR, "wordlib_data.json")
MESSAGES_FILE = os.path.join(DATA_DIR, "wordlib_config.json")  # 命令回复配置（messages 字段）

MASTER_QQ = get_master_qq()
BOT_QQ = get_bot_qq()

# ========== 配置加载（从 data/wordlib_messages.json）==========
_CFG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "wordlib_config.json")
_CFG = {}

def _l():
    global _CFG
    if os.path.exists(_CFG_FILE):
        try:
            with open(_CFG_FILE, 'r', encoding='utf-8') as fh:
                _CFG = json.load(fh)
        except:
            _CFG = {}
    else:
        _CFG = {}
_l()

def cmd(k, d=None):
    v = _CFG.get('commands', {}).get(k)
    return v if v is not None else d

def setting(k, d=None):
    v = _CFG.get('settings', {}).get(k)
    return v if v is not None else d

def _save():
    with open(_CFG_FILE, "w", encoding="utf-8") as f:
        json.dump(_CFG, f, ensure_ascii=False, indent=2)

BOT_NAME = get_bot_name()

# 命令前缀配置（可自定义）
ADD_WORD_COMMAND = cmd("add", f"{BOT_NAME}跟我学")
DELETE_WORD_COMMAND = cmd("delete", f"{BOT_NAME}忘掉")
QUERY_WORD_COMMAND = cmd("query", f"{BOT_NAME}回忆一下")
ENCODE_COMMAND = cmd("encode", "转码")  # 转码命令

# 转码状态存储
user_encode_state = {}

# ========== 默认命令回复（可通过 wordlib_messages.json 自定义）==========
DEFAULT_MESSAGES = {
    "sign_success": "签到成功！获得[add]点好感度，当前好感度[favor]",
    "sign_already": "今天已经签到过了，扣除[minus]点好感度，当前好感度[favor]",
    "nickname_fail": "好感度不足，无法设置昵称，还需要[need]点好感度。",
    "nickname_set": "昵称已设置为「[nick]」",
    "nickname_format_error": "格式错误：请发送「设置昵称 你的昵称」",
    "nickname_empty": "昵称不能为空",
    "praise_success": "已为你点赞[count]次！",
    "praise_already": "今天已经给你点过赞了，明天再来吧~",
    "praise_fail": "点赞失败，请稍后再试。",
    "rank_empty": "暂无签到记录",
    "rank_title": "签到排行榜（前[top]名）：n",
    "rank_item": "[idx]. [name]([uid])：[total]次n",
    "add_step1": "请输入词条（关键词）",
    "add_step2": "请输入回答（可使用变量，例如 [name]、[@qq] 等；支持直接发送图片）",
    "add_step3": "请选择匹配模式：n1. 精准匹配n2. 模糊匹配n（回复数字1或2）",
    "add_success_exact": "已为关键词「[keyword]」添加一条精准匹配回复，这是该关键词的第 [count] 条回复。",
    "add_success_fuzzy": "已为关键词「[keyword]」添加一条模糊匹配回复，这是该关键词的第 [count] 条回复。",
    "add_format_error": "格式错误：[cmd] 关键词 答 回复内容",
    "add_empty": "关键词和回复内容不能为空。",
    "keyword_empty": "关键词不能为空，请重新发送。",
    "reply_empty": "回答不能为空，请重新发送。",
    "mode_invalid": "输入错误，请回复1或2。",
    "delete_success": "已删除关键词「[keyword]」及其所有回复。",
    "delete_reply_success": "已删除关键词「[keyword]」的第 [idx] 条回复：[content]",
    "delete_not_found": "关键词「[keyword]」不存在。",
    "delete_idx_invalid": "序号无效，当前共有 [count] 个关键词。",
    "delete_reply_idx_invalid": "序号无效，当前关键词共有 [count] 条回复。",
    "delete_idx_must_number": "序号必须是数字。",
    "delete_idx_positive": "序号必须为正整数。",
    "delete_format_error": "格式错误：[cmd] 关键词 或 [cmd] 关键词 序号 或 [cmd] 序号",
    "wordlib_empty": "词库为空。",
    "query_list_title": "当前词库关键词列表：n",
    "query_list_item": "[idx]. [keyword] ([count]条回复)n",
    "query_detail_title": "关键词「[keyword]」共有 [count] 条回复：n",
    "query_detail_item": "[idx]. [mode]: [content]n",
    "query_no_reply": "关键词「[keyword]」暂无回复。",
    "encode_start": "请发送需要转码的内容（图片、表情、语音等）",
    "encode_result": "转码结果：\n[code]\n\n已复制到剪贴板，可直接粘贴使用",
    "encode_timeout": "转码超时，请重新发送「转码」命令"
}

# ========== 签到/好感度/昵称/排行榜配置 ==========
SIGN_COMMANDS = [v for v in [cmd("sign1"), cmd("sign2")] if v]
FAVOR_ADD_RANGE = (0, setting("favor_add_max", 3))
FAVOR_MINUS_RANGE = (0, setting("favor_minus_max", 2))
NICKNAME_COMMAND = cmd("nickname", f"{BOT_NAME}以后叫我")
NICKNAME_NEED_FAVOR = setting("nickname_need_favor", 10)
RANK_COMMAND = cmd("rank", "签到排行")
RANK_TOP_N = setting("rank_top_n", 10)

# ========== 赞我功能配置 ==========
PRAISE_COMMANDS = [v for v in [cmd("praise1")] if v]
PRAISE_COUNT = setting("praise_count", 10)
# =========================================

# 用户两步式添加状态
user_word_add_state = {}

# ========== 加载命令回复配置 ==========
def load_messages():
    """加载自定义命令回复（从 wordlib_config.json 的 messages 字段），合并默认值"""
    if os.path.exists(MESSAGES_FILE):
        try:
            with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                custom = data.get("messages", {})
                messages = DEFAULT_MESSAGES.copy()
                messages.update(custom)
                return messages
        except:
            pass
    return DEFAULT_MESSAGES.copy()

def get_message(key, **kwargs):
    """获取命令回复并替换变量"""
    messages = load_messages()
    template = messages.get(key, DEFAULT_MESSAGES.get(key, ""))
    # 替换 [var] 格式的变量
    for k, v in kwargs.items():
        template = template.replace(f"[{k}]", str(v))
    return template

# ========== 时间工具函数（北京时间）==========
def beijing_now():
    return datetime.now(ZoneInfo("Asia/Shanghai"))

def get_today_key():
    return beijing_now().date().isoformat()
# =============================================

# ========== 签到/好感度/昵称数据操作 ==========
def load_sign_data():
    file = os.path.join(DATA_DIR, "sign_data.json")
    if os.path.exists(file):
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
                data.pop("_note", None)
                return data
        except:
            return {}
    return {}

def load_praise_data():
    file = os.path.join(DATA_DIR, "praise_data.json")
    if os.path.exists(file):
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
                data.pop("_note", None)
                return data
        except:
            return {}
    return {}

def _write_json(path, data):
    """写入 JSON，保留文件中原有的 _note 备注"""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                note = json.load(f).get("_note")
        except:
            note = None
    else:
        note = None
    if note:
        data["_note"] = note
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def save_praise_data(data):
    _write_json(os.path.join(DATA_DIR, "praise_data.json"), data)

def save_sign_data(data):
    _write_json(os.path.join(DATA_DIR, "sign_data.json"), data)

def load_user_data():
    """读取 user_data.json，自动从旧文件迁移"""
    new_file = os.path.join(DATA_DIR, "user_data.json")
    if os.path.exists(new_file):
        try:
            with open(new_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                data.pop("_note", None)
                return data
        except:
            return {}
    # 迁移旧数据
    old_favor_file = os.path.join(DATA_DIR, "favor_data.json")
    old_nickname_file = os.path.join(DATA_DIR, "nickname_data.json")
    has_old = os.path.exists(old_favor_file) or os.path.exists(old_nickname_file)
    if not has_old:
        return {}
    data = {}
    if os.path.exists(old_favor_file):
        try:
            with open(old_favor_file, "r", encoding="utf-8") as f:
                old_favor = json.load(f)
                for uid, favor in old_favor.items():
                    data.setdefault(uid, {})["favor"] = favor
        except:
            pass
    if os.path.exists(old_nickname_file):
        try:
            with open(old_nickname_file, "r", encoding="utf-8") as f:
                old_nickname = json.load(f)
                for uid, nickname in old_nickname.items():
                    data.setdefault(uid, {})["nickname"] = nickname
        except:
            pass
    save_user_data(data)
    _clean_old_data_files()
    return data

def save_user_data(data):
    _write_json(os.path.join(DATA_DIR, "user_data.json"), data)

def _clean_old_data_files():
    for name in ["favor_data.json", "nickname_data.json"]:
        path = os.path.join(DATA_DIR, name)
        if os.path.exists(path):
            try:
                os.remove(path)
            except:
                pass
# =============================================

def load_wordlib():
    """加载词库，兼容旧格式（字符串列表）"""
    if os.path.exists(WORD_DATA_FILE):
        try:
            with open(WORD_DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                data.pop("_note", None)
                if isinstance(data, dict):
                    new_data = {}
                    for keyword, replies in data.items():
                        if isinstance(replies, list) and replies and not isinstance(replies[0], dict):
                            new_data[keyword] = [{"content": r, "mode": "exact"} for r in replies]
                        else:
                            new_data[keyword] = replies
                    return new_data
                return {}
        except:
            return {}
    return {}

def save_wordlib(wordlib):
    try:
        _write_json(WORD_DATA_FILE, wordlib)
    except Exception as e:
        print(f"保存词库失败: {e}")

def load_admins():
    try:
        if os.path.exists(_CFG_FILE):
            with open(_CFG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                admins = data.get("admins", [])
                if isinstance(admins, list):
                    return admins
    except:
        pass
    return []

def save_admins(admins):
    try:
        if os.path.exists(_CFG_FILE):
            with open(_CFG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {}
        data["admins"] = admins
        _write_json(_CFG_FILE, data)
    except Exception as e:
        print(f"保存管理员列表失败: {e}")

def load_data() -> dict:
    wordlib = load_wordlib()
    admins = load_admins()
    return {"wordlib": wordlib, "admins": admins}

def save_data(data: dict):
    save_wordlib(data.get("wordlib", {}))
    save_admins(data.get("admins", []))

def is_master(user_id: int) -> bool:
    return user_id in MASTER_QQ

def is_admin(user_id: int, data: dict) -> bool:
    return is_master(user_id) or user_id in data.get("admins", [])

# ========== 图片缓存 ==========
CACHE_DIR = os.path.expanduser("~/napcat/cache/images")
CONTAINER_CACHE_PATH = "/app/cache/images"
os.makedirs(CACHE_DIR, exist_ok=True)

def download_image(url):
    if not os.path.exists(CACHE_DIR):
        return url
    url_hash = hashlib.md5(url.encode()).hexdigest()
    ext = os.path.splitext(url.split('?')[0])[1]
    if not ext or ext.lower() not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
        ext = '.jpg'
    filename = url_hash + ext
    filepath = os.path.join(CACHE_DIR, filename)
    container_path = f"{CONTAINER_CACHE_PATH}/{filename}"
    if os.path.exists(filepath):
        return container_path
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=10, stream=True)
        if r.status_code == 200:
            with open(filepath, 'wb') as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)
            return container_path
        else:
            return url
    except Exception as e:
        print(f"下载图片异常: {url} - {e}")
        return url
# ======================================================

def handle_message(event: dict, data: dict) -> bool:
    global re
    raw_msg = event.get("raw_message", "").strip()
    user_id = event.get("user_id")
    wordlib = data["wordlib"]
    admins = data["admins"]

    # ========== 两步式词条添加状态 ==========
    if user_id in user_word_add_state:
        state = user_word_add_state[user_id]
        is_command = any(raw_msg.startswith(cmd) for cmd in [
            ADD_WORD_COMMAND, DELETE_WORD_COMMAND, QUERY_WORD_COMMAND
        ])
        if is_command:
            del user_word_add_state[user_id]
        else:
            if state["step"] == "waiting_keyword":
                keyword = raw_msg
                if not keyword:
                    send_message(event, get_message("keyword_empty"))
                    return True
                user_word_add_state[user_id] = {"step": "waiting_reply", "keyword": keyword}
                send_message(event, get_message("add_step2"))
                return True
            elif state["step"] == "waiting_reply":
                keyword = state["keyword"]
                reply_segments = event.get("message")
                if not reply_segments:
                    send_message(event, get_message("reply_empty"))
                    return True
                user_word_add_state[user_id] = {
                    "step": "waiting_mode",
                    "keyword": keyword,
                    "reply_segments": reply_segments
                }
                send_message(event, get_message("add_step3"))
                return True
            elif state["step"] == "waiting_mode":
                if raw_msg in ["1", "2"]:
                    mode = "exact" if raw_msg == "1" else "fuzzy"
                    keyword = state["keyword"]
                    reply_segments = state["reply_segments"]
                    if keyword not in wordlib:
                        wordlib[keyword] = []
                    wordlib[keyword].append({"content": reply_segments, "mode": mode})
                    save_data(data)
                    type_str = "精准" if mode == "exact" else "模糊"
                    msg_key = "add_success_exact" if mode == "exact" else "add_success_fuzzy"
                    send_message(event, get_message(msg_key, keyword=keyword, count=len(wordlib[keyword])))
                    del user_word_add_state[user_id]
                else:
                    send_message(event, get_message("mode_invalid"))
                return True

    # ========== 转码功能 ==========
    if raw_msg == ENCODE_COMMAND:
        user_encode_state[user_id] = {"step": "waiting_content", "time": time.time()}
        send_message(event, get_message("encode_start"))
        return True
    
    # 处理转码等待状态
    if user_id in user_encode_state:
        state = user_encode_state[user_id]
        if state.get("step") == "waiting_content":
            # 超时检查
            if time.time() - state.get("time", 0) > setting("encode_timeout", 300):
                del user_encode_state[user_id]
                send_message(event, get_message("encode_timeout"))
                return True
            
            # 获取原始消息格式
            raw_message = event.get("raw_message", "")
            message_segments = event.get("message", [])
            
            # 构建转码结果
            encode_result = ""
            for seg in message_segments:
                seg_type = seg.get("type", "")
                data = seg.get("data", {})
                
                if seg_type == "text":
                    encode_result += data.get("text", "")
                elif seg_type == "image":
                    # 图片格式
                    file = data.get("file", data.get("url", ""))
                    if file:
                        encode_result += f"[pic={file}]"
                elif seg_type == "face":
                    # 表情格式
                    face_id = data.get("id", "")
                    if face_id:
                        encode_result += f"[Face{face_id}.gif]"
                elif seg_type == "at":
                    # @人格式
                    qq = data.get("qq", "")
                    if qq:
                        encode_result += f"[at={qq}]"
                elif seg_type == "record":
                    # 语音格式
                    file = data.get("file", "")
                    if file:
                        encode_result += f"[Voi={file}]"
                elif seg_type == "emoji":
                    # emoji格式
                    emoji_id = data.get("id", "")
                    if emoji_id:
                        encode_result += f"[emoji={emoji_id}]"
                else:
                    # 其他类型，直接用raw_message
                    encode_result = raw_message
                    break
            
            if not encode_result:
                encode_result = raw_message
            
            del user_encode_state[user_id]
            send_message(event, get_message("encode_result", code=encode_result))
            return True

    # ========== 签到功能 ==========
    if raw_msg in SIGN_COMMANDS:
        sign_data = load_sign_data()
        user_data = load_user_data()
        today = beijing_now().date().isoformat()
        user_key = str(user_id)
        total = sign_data.get(user_key, {}).get("total", 0)
        last_date = sign_data.get(user_key, {}).get("last_date", "")
        if last_date != today:
            total += 1
            sign_data[user_key] = {"total": total, "last_date": today}
            add = random.randint(*FAVOR_ADD_RANGE)
            favor = user_data.get(user_key, {}).get("favor", 0) + add
            user_data.setdefault(user_key, {})["favor"] = favor
            save_sign_data(sign_data)
            save_user_data(user_data)
            reply = get_message("sign_success", add=add, favor=favor)
        else:
            minus = random.randint(*FAVOR_MINUS_RANGE)
            favor = user_data.get(user_key, {}).get("favor", 0) - minus
            user_data.setdefault(user_key, {})["favor"] = max(favor, 0)
            save_user_data(user_data)
            reply = get_message("sign_already", minus=minus, favor=favor)
        send_message(event, reply)
        return True

    # ========== 赞我功能 ==========
    if raw_msg in PRAISE_COMMANDS:
        praise_data = load_praise_data()
        today = beijing_now().date().isoformat()
        user_key = str(user_id)
        last_date = praise_data.get(user_key, "")
        if last_date != today:
            praise_data[user_key] = today
            save_praise_data(praise_data)
            try:
                from utils.api import http_get
                result = http_get("send_like", {"user_id": user_id, "times": PRAISE_COUNT})
                if result and result.get("status") == "ok":
                    reply = get_message("praise_success", count=PRAISE_COUNT)
                else:
                    reply = get_message("praise_fail")
            except Exception as e:
                print(f"点赞异常: {e}")
                reply = get_message("praise_fail")
        else:
            reply = get_message("praise_already")
        send_message(event, reply)
        return True

    # ========== 自定义昵称 ==========
    if raw_msg.startswith(NICKNAME_COMMAND):
        user_data = load_user_data()
        user_favor = user_data.get(str(user_id), {}).get("favor", 0)
        if user_favor < NICKNAME_NEED_FAVOR:
            need = NICKNAME_NEED_FAVOR - user_favor
            send_message(event, get_message("nickname_fail", need=need))
            return True
        parts = raw_msg.split(maxsplit=1)
        if len(parts) < 2:
            send_message(event, get_message("nickname_format_error"))
            return True
        new_nick = parts[1].strip()
        if not new_nick:
            send_message(event, get_message("nickname_empty"))
            return True
        user_data.setdefault(str(user_id), {})["nickname"] = new_nick
        save_user_data(user_data)
        send_message(event, get_message("nickname_set", nick=new_nick))
        return True

    # ========== 签到排行榜 ==========
    if raw_msg == RANK_COMMAND:
        sign_data = load_sign_data()
        if not sign_data:
            send_message(event, get_message("rank_empty"))
            return True
        sorted_list = sorted(sign_data.items(), key=lambda x: x[1]["total"], reverse=True)[:RANK_TOP_N]
        user_data = load_user_data()
        group_id = event.get("group_id")
        members = []
        if group_id:
            try:
                from utils.api import http_get
                members_data = http_get("get_group_member_list", {"group_id": group_id})
                if members_data and members_data.get("status") == "ok":
                    members = members_data.get("data", [])
            except:
                pass
        member_dict = {str(m["user_id"]): m.get("nickname", "") for m in members}
        msg = get_message("rank_title", top=len(sorted_list))
        for idx, (uid, info) in enumerate(sorted_list, 1):
            custom_nick = user_data.get(uid, {}).get("nickname", "")
            if custom_nick:
                display_name = custom_nick
            else:
                display_name = member_dict.get(uid, uid)
            msg += get_message("rank_item", idx=idx, name=display_name, uid=uid, total=info['total'])
        send_message(event, msg.strip())
        return True

    # ========== 管理员/主人专用命令（管理词条） ==========
    if is_admin(user_id, data):
        # 添加词条（一步式精准）
        if raw_msg.startswith(ADD_WORD_COMMAND):
            if raw_msg == ADD_WORD_COMMAND:
                user_word_add_state[user_id] = {"step": "waiting_keyword"}
                send_message(event, get_message("add_step1"))
                return True
            else:
                remaining = raw_msg[len(ADD_WORD_COMMAND):].strip()
                if '答' not in remaining:
                    send_message(event, get_message("add_format_error", cmd=ADD_WORD_COMMAND))
                    return True
                keyword, reply = remaining.split('答', 1)
                keyword = keyword.strip()
                reply = reply.strip()
                if not keyword or not reply:
                    send_message(event, get_message("add_empty"))
                    return True
                if keyword not in wordlib:
                    wordlib[keyword] = []
                wordlib[keyword].append({"content": reply, "mode": "exact"})
                save_data(data)
                send_message(event, get_message("add_success_exact", keyword=keyword, count=len(wordlib[keyword])))
                return True

        # 添加模糊词条（一步式模糊）
        if raw_msg.startswith(cmd("add_fuzzy", "添加模糊词条")):
            remaining = raw_msg[len(cmd("add_fuzzy", "添加模糊词条")):].strip()
            if '答' not in remaining:
                send_message(event, get_message("add_format_error", cmd=cmd("add_fuzzy", "添加模糊词条")))
                return True
            keyword, reply = remaining.split('答', 1)
            keyword = keyword.strip()
            reply = reply.strip()
            if not keyword or not reply:
                send_message(event, get_message("add_empty"))
                return True
            if keyword not in wordlib:
                wordlib[keyword] = []
            wordlib[keyword].append({"content": reply, "mode": "fuzzy"})
            save_data(data)
            send_message(event, get_message("add_success_fuzzy", keyword=keyword, count=len(wordlib[keyword])))
            return True

        # 删除词条
        if raw_msg.startswith(DELETE_WORD_COMMAND):
            parts = raw_msg.split()
            if len(parts) == 2:
                try:
                    idx_global = int(parts[1]) - 1
                    if idx_global < 0:
                        send_message(event, get_message("delete_idx_positive"))
                        return True
                    sorted_keywords = sorted(wordlib.keys())
                    if not sorted_keywords:
                        send_message(event, get_message("wordlib_empty"))
                        return True
                    if idx_global >= len(sorted_keywords):
                        send_message(event, get_message("delete_idx_invalid", count=len(sorted_keywords)))
                        return True
                    keyword = sorted_keywords[idx_global]
                    del wordlib[keyword]
                    save_data(data)
                    send_message(event, get_message("delete_success", keyword=keyword))
                    return True
                except ValueError:
                    keyword = parts[1]
                    if keyword not in wordlib:
                        send_message(event, get_message("delete_not_found", keyword=keyword))
                        return True
                    del wordlib[keyword]
                    save_data(data)
                    send_message(event, get_message("delete_success", keyword=keyword))
                    return True
            elif len(parts) == 3:
                keyword = parts[1]
                try:
                    idx = int(parts[2]) - 1
                except ValueError:
                    send_message(event, get_message("delete_idx_must_number"))
                    return True
                if keyword not in wordlib:
                    send_message(event, get_message("delete_not_found", keyword=keyword))
                    return True
                if idx < 0 or idx >= len(wordlib[keyword]):
                    send_message(event, get_message("delete_reply_idx_invalid", count=len(wordlib[keyword])))
                    return True
                removed = wordlib[keyword].pop(idx)
                if not wordlib[keyword]:
                    del wordlib[keyword]
                save_data(data)
                content = removed.get("content", "") if isinstance(removed, dict) else removed
                if isinstance(content, list):
                    display = "[图片]" if any(seg.get("type") == "image" for seg in content) else "[复合消息]"
                else:
                    display = content if len(content) <= 30 else content[:27] + "..."
                send_message(event, get_message("delete_reply_success", keyword=keyword, idx=idx+1, content=display))
                return True
            else:
                send_message(event, get_message("delete_format_error", cmd=DELETE_WORD_COMMAND))
                return True

        # 查询词条
        if raw_msg.startswith(QUERY_WORD_COMMAND):
            parts = raw_msg.split(maxsplit=1)
            if len(parts) < 2:
                if not wordlib:
                    send_message(event, get_message("wordlib_empty"))
                    return True
                sorted_keywords = sorted(wordlib.keys())
                msg = get_message("query_list_title")
                for i, kw in enumerate(sorted_keywords, 1):
                    count = len(wordlib[kw])
                    msg += get_message("query_list_item", idx=i, keyword=kw, count=count)
                send_message(event, msg.strip())
                return True
            else:
                keyword = parts[1].strip()
                if keyword not in wordlib or not wordlib[keyword]:
                    send_message(event, get_message("query_no_reply", keyword=keyword))
                    return True
                replies = wordlib[keyword]
                msg = get_message("query_detail_title", keyword=keyword, count=len(replies))
                for i, r in enumerate(replies, 1):
                    content = r.get("content", "") if isinstance(r, dict) else r
                    mode = r.get("mode", "exact") if isinstance(r, dict) else "exact"
                    mode_str = "精准" if mode == "exact" else "模糊"
                    if isinstance(content, list):
                        display = "[图片]" if any(seg.get("type") == "image" for seg in content) else "[复合消息]"
                    else:
                        display = content if len(content) <= 30 else content[:27] + "..."
                    msg += get_message("query_detail_item", idx=i, mode=mode_str, content=display)
                send_message(event, msg.strip())
                return True

    # ========== 随机回复（所有人可触发） ==========
    user_data = load_user_data()
    
    matched_keywords = []
    for keyword, replies in wordlib.items():
        for r in replies:
            mode = r.get("mode", "exact") if isinstance(r, dict) else "exact"
            if mode == "exact":
                if keyword == raw_msg:
                    matched_keywords.append(keyword)
                    break
            else:  # fuzzy
                if keyword in raw_msg:
                    matched_keywords.append(keyword)
                    break

    if matched_keywords:
        chosen = random.choice(matched_keywords)
        replies = wordlib[chosen]
        if replies:
            reply_item = random.choice(replies)
            if isinstance(reply_item, dict):
                reply_content = reply_item.get("content", "")
            else:
                reply_content = reply_item

            if isinstance(reply_content, list):
                send_message(event, reply_content)
                return True

            reply_template = reply_content
            import html
            reply_template = html.unescape(reply_template)

            # 获取自定义昵称
            custom_nick = user_data.get(str(user_id), {}).get("nickname", "")
            
            # 统一使用 [var] 格式的变量
            var_values = {
                "qq": str(user_id),
                "user_id": str(user_id),
                "name": event.get("sender", {}).get("nickname", ""),
                "nickname": event.get("sender", {}).get("nickname", "好友"),
                "time": beijing_now().strftime('%H:%M:%S'),
                "date": beijing_now().strftime('%Y-%m-%d'),
                "datetime": beijing_now().strftime('%Y-%m-%d %H:%M:%S'),
                "group": str(event.get("group_id", "")),
                "group_id": str(event.get("group_id", "")),
                "card": event.get("sender", {}).get("card", ""),
                "nick": custom_nick or event.get("sender", {}).get("nickname", ""),
                "favor": str(user_data.get(str(user_id), {}).get("favor", 0)),
                "r1-100": str(random.randint(1, 100)),
                "r1-1000": str(random.randint(1, 1000)),
                "bot_qq": str(BOT_QQ),
                "message_id": str(event.get("message_id", "")),
                "raw_message": raw_msg
            }
            
            # 替换所有 [var] 格式变量
            reply_text = reply_template
            for k, v in var_values.items():
                reply_text = reply_text.replace(f"[{k}]", v)
            
            # 解析动态随机数 [rX-Y] 格式
            def replace_random(match):
                try:
                    parts = match.group(1).split("-")
                    if len(parts) == 2:
                        min_val = int(parts[0])
                        max_val = int(parts[1])
                        return str(random.randint(min_val, max_val))
                except:
                    pass
                return match.group(0)
            reply_text = re.sub(r"\[r(\d+-\d+)\]", replace_random, reply_text)

            # 解析特殊标记
            pattern = r'\[img:(?P<img>.*?)\]|\[@\[QQ\]\]|\[@qq\]|\[@QQ\]|\[avatar\]|\[next\]'
            segments = []
            last_end = 0
            for match in re.finditer(pattern, reply_text):
                start, end = match.span()
                if start > last_end:
                    segments.append({
                        "type": "text",
                        "data": {"text": reply_text[last_end:start]}
                    })
                if match.group("img"):
                    img_url = match.group("img").strip()
                    if img_url:
                        img_file = download_image(img_url)
                        segments.append({"type": "image", "data": {"file": img_file}})
                elif match.group(0) in ["[@qq]", "[@QQ]", "[@QQ]"]:
                    segments.append({"type": "at", "data": {"qq": str(user_id)}})
                elif match.group(0) == "[avatar]":
                    avatar_url = f"https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640"
                    avatar_file = download_image(avatar_url)
                    segments.append({"type": "image", "data": {"file": avatar_file}})
                elif match.group(0) == "[next]":
                    segments.append({"type": "next"})
                last_end = end
            if last_end < len(reply_text):
                segments.append({
                    "type": "text",
                    "data": {"text": reply_text[last_end:]}
                })

            if not segments:
                segments = [{"type": "text", "data": {"text": reply_text}}]

            # 按 [next] 分割消息
            message_parts = []
            current_part = []
            for seg in segments:
                if seg.get("type") == "next":
                    if current_part:
                        message_parts.append(current_part)
                        current_part = []
                else:
                    current_part.append(seg)
            if current_part:
                message_parts.append(current_part)

            if len(message_parts) == 1:
                send_message(event, message_parts[0])
            else:
                for idx, part in enumerate(message_parts):
                    send_message(event, part)
                    if idx < len(message_parts) - 1:
                        time.sleep(0.5)
            return True

    return False

def handle(event: dict) -> bool:
    raw_msg = event.get("raw_message", "").strip()
    user_id = event.get("user_id")
    post_type = event.get("post_type")

    if post_type == "message":
        _l()
        group_id = event.get("group_id")
        is_group = event.get("message_type") == "group"

        # 主人开关命令（在群内→分群开关，私聊→全局）
        if is_master(user_id):
            enable_cmd = cmd("enable", "开启词库")
            disable_cmd = cmd("disable", "关闭词库")
            if raw_msg == enable_cmd or raw_msg.endswith(enable_cmd):
                if is_group:
                    _pt_set(group_id, "wordlib", True)
                    send_message(event, "词库已在本群开启")
                else:
                    _CFG.setdefault("settings", {})["enabled"] = True
                    _save()
                    send_message(event, "词库已开启")
                return True
            if raw_msg == disable_cmd or raw_msg.endswith(disable_cmd):
                if is_group:
                    _pt_set(group_id, "wordlib", False)
                    send_message(event, "词库已在本群关闭")
                else:
                    _CFG.setdefault("settings", {})["enabled"] = False
                    _save()
                    send_message(event, "词库已关闭")
                return True

        # 全局禁用检查
        if not setting("enabled", True):
            return False
        # 分群检查
        if is_group and not _pt_enabled(group_id, "wordlib"):
            return False
        data = load_data()
        return handle_message(event, data)
    return False

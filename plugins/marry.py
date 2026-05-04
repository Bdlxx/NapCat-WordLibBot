import json
import os
import random
import time
import requests
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.api import send_message
from utils.config import get_master_qq, get_napcat_http, get_access_token

# ========== 可配置命令和回复 ==========
_CFG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "commands_config.json")
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
    return _CFG.get('commands', {}).get(k) or d

def rep(k, d='', **kw):
    r = _CFG.get('replies', {}).get(k) or d
    if r and kw:
        try: return r.format(**kw)
        except: return r
    return r or d


MASTER_QQ = get_master_qq()
NAPCAT_HTTP = get_napcat_http()
ACCESS_TOKEN = get_access_token()

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)

MARRIAGE_FILE = os.path.join(DATA_DIR, "marriage.json")
CD_FILE = os.path.join(DATA_DIR, "marriage_cd.json")
CONFIG_FILE = os.path.join(DATA_DIR, "marriage_config.json")

def load_marriage():
    """加载婚姻数据，并自动修复为双向存储格式"""
    if not os.path.exists(MARRIAGE_FILE):
        return {}
    try:
        with open(MARRIAGE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 修复：将单向数据转换为双向
        repaired = False
        for group_key, days in data.items():
            for date_key, marriages in days.items():
                new_marriages = {}
                for k, v in marriages.items():
                    # 如果已经是双向，直接保留；否则补充反向关系
                    if str(v) in new_marriages:
                        # 已经存在反向关系，跳过
                        new_marriages[k] = v
                    else:
                        new_marriages[k] = v
                        new_marriages[str(v)] = int(k)
                        repaired = True
                if repaired:
                    days[date_key] = new_marriages
        if repaired:
            save_marriage(data)
            print("[修复] 已将婚姻数据转换为双向存储格式")
        return data
    except Exception as e:
        print(f"加载婚姻数据失败: {e}")
        return {}

def save_marriage(data):
    with open(MARRIAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_cd():
    if os.path.exists(CD_FILE):
        try:
            with open(CD_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_cd(data):
    with open(CD_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_config():
    default = {"success_rate": 80, "divorce_cd_hours": 24}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                return {**default, **config}
        except:
            pass
    return default

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def get_today_key():
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")

def get_group_members(group_id):
    try:
        url = f"{NAPCAT_HTTP}/get_group_member_list"
        params = {"group_id": group_id}
        if ACCESS_TOKEN:
            params["access_token"] = ACCESS_TOKEN
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "ok" and data.get("retcode") == 0:
                return data.get("data", [])
        return []
    except Exception as e:
        print(f"获取群成员失败: {e}")
        return []

def is_master(user_id):
    return user_id in MASTER_QQ

def extract_at(event):
    for seg in event.get("message", []):
        if seg.get("type") == "at":
            qq = seg.get("data", {}).get("qq")
            if qq:
                if qq == "all":
                    continue
                return int(qq)
    return None

def handle_marriage(event, target_qq=None):
    user_id = event.get("user_id")
    group_id = event.get("group_id")
    if not group_id:
        send_message(event, rep("only_group", "该功能只能在群内使用。"))
        return True

    members = get_group_members(group_id)
    if not members:
        send_message(event, rep("no_members", "无法获取群成员列表，请稍后再试。"))
        return True

    marriage_data = load_marriage()
    today = get_today_key()
    group_key = str(group_id)
    if group_key not in marriage_data:
        marriage_data[group_key] = {}
    if today not in marriage_data[group_key]:
        marriage_data[group_key][today] = {}

    # 检查自己是否已有伴侣（键存在表示已有伴侣）
    if str(user_id) in marriage_data[group_key][today]:
        send_message(event, rep("already_married", "你今天已经有对象了，不能再次结婚。"))
        return True

    # 确定目标
    if target_qq is None:
        # 随机选择，排除自己，排除已有伴侣的人（即所有键）
        occupied = set(marriage_data[group_key][today].keys())
        available = [m for m in members if m.get("user_id") != user_id and str(m.get("user_id")) not in occupied]
        if not available:
            send_message(event, rep("no_one_left", "群内所有其他成员今天都有对象了，明天再试吧。"))
            return True
        target = random.choice(available)
        target_qq = target.get("user_id")
        target_nick = target.get("nickname", "")
    else:
        if target_qq == user_id:
            send_message(event, rep("self_marry", "不能娶/嫁自己哦。"))
            return True
        target_info = next((m for m in members if m.get("user_id") == target_qq), None)
        if not target_info:
            send_message(event, rep("not_in_group", "对方不在本群，无法结婚。"))
            return True
        target_nick = target_info.get("nickname", "")

        # 检查目标是否已有伴侣（键存在）
        if str(target_qq) in marriage_data[group_key][today]:
            send_message(event, rep("target_married", "对方今天已经有对象了，不能娶/嫁。"))
            return True

    # 概率判定
    config = load_config()
    success_rate = config["success_rate"]
    if random.randint(1, 100) > success_rate:
        send_message(event, rep("failed", "表白失败，对方拒绝了你的求婚。"))
        return True

    # 再次加载最新数据（防止并发）
    marriage_data = load_marriage()
    if group_key not in marriage_data:
        marriage_data[group_key] = {}
    if today not in marriage_data[group_key]:
        marriage_data[group_key][today] = {}

    # 最终检查
    if str(user_id) in marriage_data[group_key][today]:
        send_message(event, rep("just_married", "你刚刚已经结婚了，请稍后再试。"))
        return True
    if str(target_qq) in marriage_data[group_key][today]:
        send_message(event, rep("target_just_married", "对方刚刚有了对象，请稍后再试。"))
        return True

    # 双向存储
    marriage_data[group_key][today][str(user_id)] = target_qq
    marriage_data[group_key][today][str(target_qq)] = user_id
    save_marriage(marriage_data)

    avatar_url = f"https://q1.qlogo.cn/g?b=qq&nk={target_qq}&s=640"
    msg_segments = [
        {"type": "at", "data": {"qq": str(user_id)}},
        {"type": "text", "data": {"text": f" 恭喜你！今天你的对象是 {target_nick}({target_qq}) "}},
        {"type": "image", "data": {"file": avatar_url}},
        {"type": "text", "data": {"text": " 祝你们幸福！"}}
    ]
    send_message(event, msg_segments)
    return True

def handle_divorce(event):
    user_id = event.get("user_id")
    group_id = event.get("group_id")
    if not group_id:
        send_message(event, rep("only_group", "该功能只能在群内使用。"))
        return True

    cd_data = load_cd()
    user_cd = cd_data.get(str(user_id))
    if user_cd and user_cd > time.time():
        remaining = user_cd - time.time()
        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        send_message(event, rep("divorce_cooldown", "你刚刚离过婚，请等待 {hours} 小时 {minutes} 分钟后再离婚。", hours=hours, minutes=minutes))
        return True

    marriage_data = load_marriage()
    today = get_today_key()
    group_key = str(group_id)
    if group_key not in marriage_data or today not in marriage_data[group_key]:
        send_message(event, rep("no_divorce", "你今天都没有对象，离什么婚？"))
        return True

    # 检查用户是否有伴侣（键存在）
    if str(user_id) not in marriage_data[group_key][today]:
        send_message(event, rep("no_divorce", "你今天都没有对象，离什么婚？"))
        return True

    # 获取伴侣QQ
    partner = marriage_data[group_key][today][str(user_id)]
    # 删除双向记录
    del marriage_data[group_key][today][str(user_id)]
    if str(partner) in marriage_data[group_key][today]:
        del marriage_data[group_key][today][str(partner)]
    save_marriage(marriage_data)

    cd_data[str(user_id)] = time.time() + load_config()["divorce_cd_hours"] * 3600
    save_cd(cd_data)

    send_message(event, rep("divorce_success", "离婚成功，你可以重新开始新的恋情了。"))
    return True

def handle_my_object(event):
    user_id = event.get("user_id")
    group_id = event.get("group_id")
    if not group_id:
        send_message(event, rep("only_group", "该功能只能在群内使用。"))
        return True

    marriage_data = load_marriage()
    today = get_today_key()
    group_key = str(group_id)
    if group_key not in marriage_data or today not in marriage_data[group_key] or str(user_id) not in marriage_data[group_key][today]:
        send_message(event, rep("no_object", "你今天还没有对象哦。"))
        return True

    target_qq = marriage_data[group_key][today][str(user_id)]
    members = get_group_members(group_id)
    target_info = next((m for m in members if m.get("user_id") == int(target_qq)), None)
    target_nick = target_info.get("nickname", "") if target_info else "未知"

    avatar_url = f"https://q1.qlogo.cn/g?b=qq&nk={target_qq}&s=640"
    msg_segments = [
        {"type": "at", "data": {"qq": str(user_id)}},
        {"type": "text", "data": {"text": f" 你今天的老婆/老公是 {target_nick}({target_qq}) "}},
        {"type": "image", "data": {"file": avatar_url}}
    ]
    send_message(event, msg_segments)
    return True

def handle_set_prob(event):
    if not is_master(event.get("user_id")):
        send_message(event, rep("master_only", "只有主人才能设置概率。"))
        return True
    parts = event.get("raw_message", "").split()
    if len(parts) != 2:
        send_message(event, rep("format_prob", "格式错误：设置结婚概率 数字"))
        return True
    try:
        rate = int(parts[1])
        if 0 <= rate <= 100:
            config = load_config()
            config["success_rate"] = rate
            save_config(config)
            send_message(event, rep("prob_set", "结婚成功率已设置为 {rate}%", rate=rate))
        else:
            send_message(event, rep("prob_range", "概率必须在0-100之间。"))
    except:
        send_message(event, rep("not_number", "请输入数字。"))
    return True

def handle_set_cd(event):
    if not is_master(event.get("user_id")):
        send_message(event, rep("master_only_cd", "只有主人才能设置CD。"))
        return True
    parts = event.get("raw_message", "").split()
    if len(parts) != 2:
        send_message(event, rep("format_cd", "格式错误：设置离婚CD 小时"))
        return True
    try:
        hours = float(parts[1])
        if hours >= 0:
            config = load_config()
            config["divorce_cd_hours"] = hours
            save_config(config)
            send_message(event, rep("cd_set", "离婚CD已设置为 {hours} 小时", hours=hours))
        else:
            send_message(event, rep("cd_non_neg", "CD必须是非负数。"))
    except:
        send_message(event, rep("not_number", "请输入数字。"))
    return True

def handle(event):
    if event.get("post_type") != "message" or event.get("message_type") != "group":
        return False

    raw_msg = event.get("raw_message", "").strip()

    if raw_msg.startswith(cmd("set_prob", "设置结婚概率")):
        return handle_set_prob(event)
    if raw_msg.startswith(cmd("set_cd", "设置离婚CD")):
        return handle_set_cd(event)

    if raw_msg == cmd("marry", "娶群友"):
        return handle_marriage(event)
    if raw_msg == cmd("marry_f", "嫁群友"):
        return handle_marriage(event)

    at_qq = extract_at(event)
    if raw_msg.startswith(cmd("marry_t", "娶")) and at_qq is not None:
        return handle_marriage(event, at_qq)
    if raw_msg.startswith(cmd("marry_ft", "嫁")) and at_qq is not None:
        return handle_marriage(event, at_qq)

    if raw_msg == cmd("divorce", "闹离婚"):
        return handle_divorce(event)
    if raw_msg == cmd("my_object", "我的对象"):
        return handle_my_object(event)

    return False
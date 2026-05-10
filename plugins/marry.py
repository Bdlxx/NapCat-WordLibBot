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
_CFG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "marry_config.json")
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
        try:
            return r.format(**kw)
        except:
            return r
    return r or d

def setting(k, d=None):
    return _CFG.get('settings', {}).get(k) or d

def _save():
    with open(_CFG_FILE, "w", encoding="utf-8") as f:
        json.dump(_CFG, f, ensure_ascii=False, indent=2)


MASTER_QQ = get_master_qq()
NAPCAT_HTTP = get_napcat_http()
ACCESS_TOKEN = get_access_token()

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)

MARRIAGE_FILE = os.path.join(DATA_DIR, "marriage.json")
CD_FILE = os.path.join(DATA_DIR, "marriage_cd.json")


def _purge_old_days(data):
    today = get_today_key()
    for group_key in list(data.keys()):
        days = data.get(group_key, {})
        for date_key in list(days.keys()):
            if date_key != today:
                del days[date_key]
        if not days:
            del data[group_key]
        else:
            data[group_key] = days
    return data

def load_marriage():
    if not os.path.exists(MARRIAGE_FILE):
        return {}
    try:
        with open(MARRIAGE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        _purge_old_days(data)
        repaired = False
        for group_key, days in data.items():
            for date_key, marriages in days.items():
                new_marriages = {}
                for k, v in marriages.items():
                    if str(v) in new_marriages:
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
    _purge_old_days(data)
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

def handle_marriage(event, target_qq=None, mode="娶"):
    if event.get("message_type") != "group":
        send_message(event, rep("only_group", "该功能只能在群内使用。"))
        return True

    user_id = event.get("user_id")
    group_id = event.get("group_id")

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

    if str(user_id) in marriage_data[group_key][today]:
        send_message(event, rep("already_married", "你今天已经有对象了，不能再次结婚。"))
        return True

    if target_qq is None:
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
        if str(target_qq) in marriage_data[group_key][today]:
            send_message(event, rep("target_married", "对方今天已经有对象了，不能娶/嫁。"))
            return True

    success_rate = setting("success_rate", 80)
    if random.randint(1, 100) > success_rate:
        send_message(event, rep("failed", "表白失败，对方拒绝了你的求婚。"))
        return True

    marriage_data = load_marriage()
    if group_key not in marriage_data:
        marriage_data[group_key] = {}
    if today not in marriage_data[group_key]:
        marriage_data[group_key][today] = {}

    if str(user_id) in marriage_data[group_key][today]:
        send_message(event, rep("just_married", "你刚刚已经结婚了，请稍后再试。"))
        return True
    if str(target_qq) in marriage_data[group_key][today]:
        send_message(event, rep("target_just_married", "对方刚刚有了对象，请稍后再试。"))
        return True

    marriage_data[group_key][today][str(user_id)] = {"qq": target_qq, "mode": mode}
    inverse_mode = "嫁" if mode == "娶" else "娶"
    marriage_data[group_key][today][str(target_qq)] = {"qq": user_id, "mode": inverse_mode}
    save_marriage(marriage_data)

    avatar_url = f"https://q1.qlogo.cn/g?b=qq&nk={target_qq}&s=640"
    if mode == "娶":
        msg_segments = [
            {"type": "at", "data": {"qq": str(user_id)}},
            {"type": "text", "data": {"text": f" 恭喜你！今天你娶了老婆 {target_nick}({target_qq}) "}},
            {"type": "image", "data": {"file": avatar_url}},
            {"type": "text", "data": {"text": " 祝你们幸福！"}}
        ]
    else:
        msg_segments = [
            {"type": "at", "data": {"qq": str(user_id)}},
            {"type": "text", "data": {"text": f" 恭喜你！今天你嫁给了老公 {target_nick}({target_qq}) "}},
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

    if str(user_id) not in marriage_data[group_key][today]:
        send_message(event, rep("no_divorce", "你今天都没有对象，离什么婚？"))
        return True

    partner = marriage_data[group_key][today][str(user_id)]
    partner_qq = partner.get("qq") if isinstance(partner, dict) else partner
    del marriage_data[group_key][today][str(user_id)]
    if str(partner_qq) in marriage_data[group_key][today]:
        del marriage_data[group_key][today][str(partner_qq)]
    save_marriage(marriage_data)

    cd_data[str(user_id)] = time.time() + setting("divorce_cd_hours", 24) * 3600
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
    if isinstance(target_qq, dict):
        mode = target_qq.get("mode", "娶")
        target_qq = target_qq["qq"]
    else:
        mode = "娶"
    members = get_group_members(group_id)
    target_info = next((m for m in members if m.get("user_id") == int(target_qq)), None)
    target_nick = target_info.get("nickname", "") if target_info else "未知"

    caller_role = "老公" if mode == "娶" else "老婆"
    partner_role = "老婆" if mode == "娶" else "老公"

    avatar_url = f"https://q1.qlogo.cn/g?b=qq&nk={target_qq}&s=640"
    msg_segments = [
        {"type": "at", "data": {"qq": str(user_id)}},
        {"type": "text", "data": {"text": f" 今天你的{partner_role}是 {target_nick}({target_qq}) "}},
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
            _l()
            _CFG.setdefault("settings", {})["success_rate"] = rate
            _save()
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
            _l()
            _CFG.setdefault("settings", {})["divorce_cd_hours"] = hours
            _save()
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
        return handle_marriage(event, mode="娶")
    if raw_msg == cmd("marry_f", "嫁群友"):
        return handle_marriage(event, mode="嫁")

    at_qq = extract_at(event)
    if raw_msg.startswith(cmd("marry_t", "娶")) and at_qq is not None:
        return handle_marriage(event, at_qq, mode="娶")
    if raw_msg.startswith(cmd("marry_ft", "嫁")) and at_qq is not None:
        return handle_marriage(event, at_qq, mode="嫁")

    if raw_msg == cmd("divorce", "闹离婚"):
        return handle_divorce(event)
    if raw_msg == cmd("my_object", "我的对象"):
        return handle_my_object(event)

    return False


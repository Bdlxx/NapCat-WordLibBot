"""
看门狗 - 监听"重启"命令，重启主程序
独立进程运行（screen），不依赖主程序

工作流程：
1. 连接 NapCat WebSocket，监听消息
2. 收到主人/管理员的"重启"命令时，执行 bot restart
3. 主程序重启完成后发送"重启完成"通知
"""

import json
import os
import subprocess
import sys
import threading
import time
import requests
import websocket

# ====== 配置加载 ======
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[看门狗] 读取配置失败: {e}")
        sys.exit(1)

config = load_config()
WS_URL = config.get("WS_URL", "")
MASTER_QQ = [str(q) for q in config.get("MASTER_QQ", [])]
BOT_QQ = str(config.get("BOT_QQ", "0"))
NAPCAT_HTTP = config.get("NAPCAT_HTTP", "http://127.0.0.1:3000")
ACCESS_TOKEN = config.get("ACCESS_TOKEN", "")
BOT_NAME = config.get("BOT_NAME", "Bot")
DATA_DIR = os.path.join(BASE_DIR, "data")

# 根据 BOT_QQ 判断编号（1=依星 2=羽笙）
BOT_NUM = "2" if BOT_QQ == "2551736206" else "1"
BOT_SCRIPT = "/usr/local/bin/bot"

print(f"[看门狗] 启动 {BOT_NAME}(QQ:{BOT_QQ}), 编号={BOT_NUM}")
print(f"[看门狗] WS={WS_URL}, 主人={MASTER_QQ}")


def load_admins():
    """从词库配置加载管理员列表"""
    wordlib_cfg = os.path.join(DATA_DIR, "wordlib_config.json")
    if os.path.exists(wordlib_cfg):
        try:
            with open(wordlib_cfg, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            admins = cfg.get("admins", [])
            return [str(a) for a in admins]
        except Exception as e:
            print(f"[看门狗] 读取管理员配置失败: {e}")
    return []


def is_authorized(user_id):
    """检查用户是否有重启权限（主人或管理员）"""
    uid = str(user_id)
    if uid in MASTER_QQ:
        return True
    try:
        admins = load_admins()
        if uid in admins:
            return True
    except:
        pass
    return False


def send_group_msg(group_id, text):
    """通过 NapCat HTTP API 发送群消息"""
    payload = {
        "group_id": group_id,
        "message": [{"type": "text", "data": {"text": text}}]
    }
    params = {"access_token": ACCESS_TOKEN} if ACCESS_TOKEN else {}
    try:
        r = requests.post(f"{NAPCAT_HTTP}/send_group_msg", params=params, json=payload, timeout=10)
        print(f"[看门狗] 发送消息到群 {group_id}: HTTP {r.status_code}")
        return r.ok
    except Exception as e:
        print(f"[看门狗] 发送消息失败: {e}")
        return False


def send_private_msg(user_id, text):
    """通过 NapCat HTTP API 发送私聊消息"""
    payload = {
        "user_id": user_id,
        "message": [{"type": "text", "data": {"text": text}}]
    }
    params = {"access_token": ACCESS_TOKEN} if ACCESS_TOKEN else {}
    try:
        r = requests.post(f"{NAPCAT_HTTP}/send_private_msg", params=params, json=payload, timeout=10)
        return r.ok
    except:
        return False


def reply(event, text):
    """根据事件类型发送回复"""
    if event.get("message_type") == "private":
        send_private_msg(event.get("user_id"), text)
    elif event.get("message_type") == "group":
        send_group_msg(event.get("group_id"), text)


def is_bot_running():
    """检查主程序是否在运行"""
    screen_name = "bot" if BOT_NUM == "1" else "bot2"
    try:
        result = subprocess.run(
            ["screen", "-list"],
            capture_output=True, text=True, timeout=5
        )
        return screen_name in result.stdout
    except:
        return False


def do_restart(event):
    """重启主程序"""
    user_id = event.get("user_id")
    group_id = event.get("group_id")

    print(f"[看门狗] 收到重启命令: user={user_id}, group={group_id}")
    reply(event, f"🔄 {BOT_NAME} 正在重启中...")

    # 执行脚本重启
    time.sleep(1)
    print(f"[看门狗] 执行: {BOT_SCRIPT} restart {BOT_NUM}")
    try:
        result = subprocess.run(
            [BOT_SCRIPT, "restart", BOT_NUM],
            timeout=30,
            capture_output=True, text=True
        )
        print(f"[看门狗] 重启结果: {result.stdout.strip()}")
    except subprocess.TimeoutExpired:
        print(f"[看门狗] 重启超时")
        reply(event, f"⚠️ {BOT_NAME} 重启超时，请检查状态")
        return
    except Exception as e:
        print(f"[看门狗] 重启异常: {e}")
        reply(event, f"❌ {BOT_NAME} 重启失败: {e}")
        return

    # 等待主程序启动
    time.sleep(3)
    if is_bot_running():
        print(f"[看门狗] {BOT_NAME} 已重启成功")
        reply(event, f"✅ {BOT_NAME} 重启完成！")
    else:
        print(f"[看门狗] {BOT_NAME} 重启后未运行")
        reply(event, f"⚠️ {BOT_NAME} 重启启动失败，请检查日志")


def on_message(ws, message):
    try:
        event = json.loads(message)
        # 跳过 API 响应
        if "echo" in event:
            return
        if event.get("post_type") != "message":
            return

        raw = event.get("raw_message", "").strip()
        user_id = event.get("user_id")
        message_type = event.get("message_type")

        # 检查是否为重启命令（群聊或私聊）
        if raw in ("重启", f"重启{BOT_NAME}", f"重启{BOT_NAME}机器人"):
            print(f"[看门狗] 收到 {message_type} 消息: user={user_id}, msg='{raw}'")
            if is_authorized(user_id):
                do_restart(event)
            else:
                print(f"[看门狗] 无权限: user={user_id}")

    except json.JSONDecodeError:
        pass
    except Exception as e:
        print(f"[看门狗] 处理消息异常: {e}")


def on_error(ws, error):
    print(f"[看门狗] WebSocket 错误: {error}")


def on_close(ws, close_status_code, close_msg):
    print(f"[看门狗] 连接关闭 ({close_status_code}): {close_msg}")
    time.sleep(3)


def on_open(ws):
    print(f"[看门狗] ✅ WebSocket 已连接，开始监听...")


def connect():
    """建立 WebSocket 连接（自动重连）"""
    print(f"[看门狗] 连接 WebSocket: {WS_URL}")
    ws = websocket.WebSocketApp(
        WS_URL,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open,
    )
    ws.run_forever(reconnect=5)


if __name__ == "__main__":
    print(f"[看门狗] ═══════════════════════════")
    print(f"[看门狗]    {BOT_NAME} 看门狗 v1.0")
    print(f"[看门狗]    主人QQ: {', '.join(MASTER_QQ)}")
    print(f"[看门狗]    机器人: #{BOT_NUM}")
    print(f"[看门狗] ═══════════════════════════")

    while True:
        try:
            connect()
        except Exception as e:
            print(f"[看门狗] 连接异常: {e}")
        print(f"[看门狗] 5 秒后重连...")
        time.sleep(5)

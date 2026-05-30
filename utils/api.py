# utils/api.py
import json
import time
import requests
import utils.ws
from utils.config import get_napcat_http, get_access_token

HTTP_URL = get_napcat_http()
ACCESS_TOKEN = get_access_token()

def send_message(event, message):
    """通过 WebSocket 发送消息，message 可以是字符串或消息段列表"""
    msg_type = event.get("message_type")
    user_id = event.get("user_id")
    group_id = event.get("group_id") if msg_type == "group" else None

    if msg_type == "private":
        action = "send_private_msg"
        params = {"user_id": user_id}
    elif msg_type == "group":
        action = "send_group_msg"
        params = {"group_id": group_id}
    else:
        return

    params["message"] = message

    request = {
        "action": action,
        "params": params,
        "echo": str(time.time())
    }

    request_str = json.dumps(request, ensure_ascii=False)
    print(f"发送请求: {request_str}")

    if utils.ws.ws:
        utils.ws.ws.send(request_str)
        print(f"通过 WebSocket 发送消息: {action}")
    else:
        print("WebSocket 未连接，无法发送")

# 如果你还需要通过 HTTP 主动调用 API（如获取群成员列表），可保留以下函数
def http_get(action, params=None):
    """通过 HTTP GET 调用 NapCat API（用于主动查询）"""
    url = f"{HTTP_URL}/{action}"
    if ACCESS_TOKEN:
        if params is None:
            params = {}
        params["access_token"] = ACCESS_TOKEN
    try:
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"HTTP请求失败: {resp.status_code}")
            return None
    except Exception as e:
        print(f"HTTP请求异常: {e}")
        return None
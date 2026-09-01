# utils/api.py
import json
import time
import threading
import requests
import utils.ws
from utils.config import get_napcat_http, get_access_token

HTTP_URL = get_napcat_http()
ACCESS_TOKEN = get_access_token()

# ====== WS 发送回调（echo → message_id）======
# 插件通过 ws_send 发送带 echo 的请求，NapCat 返回响应时由主程序
# handle_ws_echo 分发到回调（如拿 message_id 调度撤回）
_echo_callbacks = {}
_echo_lock = threading.Lock()


def ws_send(event, message, on_ok=None, echo=None):
    """通过 WebSocket 发送消息，NapCat 返回响应时调用 on_ok(data)。
    data 含 message_id（真实发送成功的标识）。返回 True 表示已发送。"""
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
        return False

    params["message"] = message
    if echo is None:
        echo = f"ws_{time.time()}_{id(message)}"
    request = {"action": action, "params": params, "echo": echo}
    request_str = json.dumps(request, ensure_ascii=False)

    if not utils.ws.ws:
        print("WebSocket 未连接，无法发送")
        return False

    if on_ok is not None:
        with _echo_lock:
            _echo_callbacks[echo] = on_ok
    utils.ws.ws.send(request_str)
    # NapCat 风格发送日志（不打印完整 JSON）
    try:
        from utils.log import log, log_msg_event
        log_msg_event(event, "发送", msg_content=message)
        log('debug', f'发送详情 <- {request_str}')
    except Exception:
        print(f"通过 WebSocket 发送消息: {action}")
    return True


def handle_ws_echo(event):
    """main.py on_message 收到带 echo 的 API 响应时调用，分发到已注册回调"""
    echo = event.get("echo")
    if not echo:
        return
    with _echo_lock:
        cb = _echo_callbacks.pop(echo, None)
    if cb:
        try:
            cb(event)
        except Exception as e:
            print(f"[WS回调] 执行异常: {e}")


def ws_delete_msg(message_id):
    """通过 WebSocket 调用 delete_msg 撤回消息"""
    if not utils.ws.ws:
        print("WebSocket 未连接，无法撤回")
        return False
    request = {
        "action": "delete_msg",
        "params": {"message_id": message_id},
        "echo": f"del_{message_id}_{time.time()}",
    }
    utils.ws.ws.send(json.dumps(request, ensure_ascii=False))
    return True


def send_forward_msg(event, nodes, news=None):
    """发送合并转发消息（通过 WebSocket）
    nodes: [{"name": "昵称", "uin": "QQ号", "content": [消息段列表]}, ...]
    news: 可选，自定义卡片外显文字列表 [{"text": "..."}, ...]
          （NapCat ForwardMsgBuilder 支持，控制合并转发卡片每行显示）
    """
    msg_type = event.get("message_type")
    user_id = event.get("user_id")
    group_id = event.get("group_id") if msg_type == "group" else None

    if msg_type == "private":
        action = "send_private_forward_msg"
        params = {"user_id": user_id}
    elif msg_type == "group":
        action = "send_group_forward_msg"
        params = {"group_id": group_id}
    else:
        return

    messages = []
    for node in nodes:
        messages.append({
            "type": "node",
            "data": {
                "name": node.get("name", "机器人"),
                "uin": node.get("uin", ""),
                "content": node.get("content", [])
            }
        })

    params["messages"] = messages
    if news:
        params["news"] = news

    request = {
        "action": action,
        "params": params,
        "echo": str(time.time())
    }

    request_str = json.dumps(request, ensure_ascii=False)

    if utils.ws.ws:
        utils.ws.ws.send(request_str)
        try:
            from utils.log import log
            log('info', f'发送 -> 合并转发 ({len(nodes)} 条)')
            # 完整节点内容归入 debug 级
            log('debug', f'转发详情 <- {request_str}')
        except Exception:
            print(f"通过 WebSocket 发送合并转发: {action}")
    else:
        print("WebSocket 未连接，无法发送")


def send_message(event, message):
    """通过 WebSocket 发送消息，message 可以是字符串或消息段列表。
    含 forward（合并转发）段时自动改用 send_forward_msg（QQ 合并转发需
    send_group_forward_msg 动作，send_group_msg 无法解析 forward 段）"""
    msg_type = event.get("message_type")
    user_id = event.get("user_id")
    group_id = event.get("group_id") if msg_type == "group" else None

    # 检测合并转发段：message 是列表且含 type=forward，或本身就是 forward 列表
    if isinstance(message, list) and any(
        isinstance(m, dict) and m.get("type") == "forward" for m in message
    ):
        forward_seg = next(m for m in message if isinstance(m, dict) and m.get("type") == "forward")
        fdata = forward_seg.get("data", {})
        nodes = fdata.get("messages") or []
        news = fdata.get("news")
        # 转为 send_forward_msg 期望的节点格式
        node_list = []
        for n in nodes:
            nd = n.get("data", {})
            node_list.append({
                "name": nd.get("name", "机器人"),
                "uin": nd.get("uin", ""),
                "content": nd.get("content", []),
            })
        send_forward_msg(event, node_list, news=news)
        return

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

    if utils.ws.ws:
        utils.ws.ws.send(request_str)
        # NapCat 风格发送日志（不打印完整 JSON）
        try:
            from utils.log import log, log_msg_event
            log_msg_event(event, "发送", msg_content=message)
            # 完整请求体归入 debug 级（默认不显示，切「全部/仅调试」可见）
            log('debug', f'发送详情 <- {request_str}')
        except Exception:
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
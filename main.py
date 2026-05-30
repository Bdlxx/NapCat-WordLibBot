import importlib
import pkgutil
import time
import websocket
import json
import threading
import sys
import os
import argparse
import plugins
import utils.ws

# ====== 命令行参数（机器人昵称 + QQ，各插件直接调用 config 模块读取）======
parser = argparse.ArgumentParser(description="NapCat 机器人")
parser.add_argument("--bot-name", default=None, help="机器人昵称（如 羽笙/依星）")
parser.add_argument("--bot-qq", default=None, help="机器人 QQ 号")
args = parser.parse_args()

from utils.config import set_cli_params
set_cli_params(bot_name=args.bot_name, bot_qq=args.bot_qq)

# ====== 日志文件 ======
LOG_FILE = os.path.join(os.path.dirname(__file__), "runtime.log")
log_file = open(LOG_FILE, "a", encoding="utf-8", buffering=1)

class Tee:
    def write(self, msg):
        log_file.write(msg)
        sys.__stdout__.write(msg)
    def flush(self):
        log_file.flush()
        sys.__stdout__.flush()

sys.stdout = Tee()
sys.stderr = Tee()
# ===========================

# WebSocket 连接地址
from utils.config import get_config as _get_cfg
from utils.command_table import build_command_table
from utils.api import send_message

WS_URL = _get_cfg("WS_URL", "ws://127.0.0.1:3003/?access_token=pdlKE8P2vfQD0nVZ")

def _is_master(user_id):
    ml = _get_cfg("MASTER_QQ", [])
    if not isinstance(ml, list):
        ml = [ml]
    return str(user_id) in [str(m) for m in ml]

# 加载所有插件
plugin_handlers = []
for finder, name, ispkg in pkgutil.iter_modules(plugins.__path__):
    module = importlib.import_module(f"plugins.{name}")
    if hasattr(module, "handle"):
        plugin_handlers.append(module.handle)
        print(f"加载插件: {name}")

def on_message(ws, message):
    try:
        event = json.loads(message)
        if "echo" in event:
            return

        # 主人私聊「命令表」命令
        if (event.get("post_type") == "message"
                and event.get("message_type") == "private"
                and _is_master(event.get("user_id"))):
            raw = event.get("raw_message", "").strip()
            if raw == "命令表":
                bot_name = _get_cfg("BOT_NAME", "羽笙")
                table = build_command_table(bot_name=bot_name)
                paragraphs = table.split("\n\n")
                for para in paragraphs:
                    chunk = para.strip()
                    if chunk:
                        send_message(event, chunk)
                        time.sleep(0.5)
                print(f"[命令表] 已发送 {len(paragraphs)} 段给主人")
                return

        for handler in plugin_handlers:
            if handler(event):
                break
    except Exception as e:
        import traceback
        print(f"处理事件出错: {e}")
        traceback.print_exc()  # 输出完整堆栈

def on_error(ws, error):
    print(f"连接错误: {error}")

def on_close(ws, close_status_code, close_msg):
    print("连接已关闭")
    utils.ws.ws = None  # 清空全局 WebSocket 对象

def on_open(ws):
    print("WebSocket 连接成功，等待事件...")
    utils.ws.ws = ws  # 设置全局 WebSocket 对象

if __name__ == "__main__":
    ws = websocket.WebSocketApp(WS_URL,
                                on_open=on_open,
                                on_message=on_message,
                                on_error=on_error,
                                on_close=on_close)
    wst = threading.Thread(target=ws.run_forever, kwargs={"reconnect": 5})
    wst.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        ws.close()
import importlib
import pkgutil
import time
import websocket
import json
import threading
import sys
import os
import plugins
import utils.ws

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
# ===========================  # 用于存储全局 WebSocket 对象

# WebSocket 连接地址（根据你的 NapCat 配置修改，已包含 token）
from utils.config import get_config as _get_cfg
WS_URL = _get_cfg("WS_URL", "ws://127.0.0.1:3003/?access_token=pdlKE8P2vfQD0nVZ")

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
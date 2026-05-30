import json
import os

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "..", "config.json")

# CLI 传入的系统参数（由 main.py 在启动时设置，优先于 config.json）
CLI_BOT_NAME = None
CLI_BOT_QQ = None

def set_cli_params(bot_name=None, bot_qq=None):
    """由 main.py 在启动时调用，将命令行参数写入模块全局变量"""
    global CLI_BOT_NAME, CLI_BOT_QQ
    if bot_name is not None:
        CLI_BOT_NAME = bot_name
    if bot_qq is not None:
        CLI_BOT_QQ = bot_qq

def load_config():
    """加载配置文件，返回字典；如果文件不存在或解析失败，返回空字典"""
    if not os.path.exists(CONFIG_FILE):
        print("警告：配置文件 config.json 不存在，将使用默认值（空字典）。")
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"读取配置文件失败: {e}")
        return {}

def get_config(key, default=None):
    """获取指定配置项的值，若不存在则返回 default"""
    config = load_config()
    return config.get(key, default)

# 常用配置项的便捷函数
def get_bot_name():
    """优先返回 CLI 参数 --bot-name，其次 config.json 的 BOT_NAME"""
    return CLI_BOT_NAME if CLI_BOT_NAME else get_config("BOT_NAME", "羽笙")

def get_master_qq():
    return get_config("MASTER_QQ", [])

def get_bot_qq():
    """优先返回 CLI 参数 --bot-qq，其次 config.json 的 BOT_QQ"""
    qq = CLI_BOT_QQ if CLI_BOT_QQ else get_config("BOT_QQ", 0)
    try:
        return int(qq)
    except (ValueError, TypeError):
        return 0

def get_napcat_http():
    return get_config("NAPCAT_HTTP", "http://127.0.0.1:3000")

def get_access_token():
    return get_config("ACCESS_TOKEN", "")
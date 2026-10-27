#!/usr/bin/env python3
"""面板「设置」页（主人 QQ / 管理员 QQ）的测试。

覆盖：入参规整/校验、读写落盘（config.json 的 MASTER_QQ + wordlib_config.json 的 admins）、
「校验不过就一个字节都不写」、未装词库插件时跳过管理员、以及页面片段真的带出当前值。

跑法：cd /root/mybot2 && python3 -m unittest tests.test_panel_settings -v
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (ROOT, os.path.join(ROOT, "web")):
    if path not in sys.path:
        sys.path.insert(0, path)

import api as panel_api          # noqa: E402  web/api.py（测试里不真的起服务）

CSRF = {"X-Requested-With": "XMLHttpRequest"}


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def _make_instance(wordlib=True, wordlib_cfg=True, master=(2840771765,), admins=("245524106",)):
    """造一个最小实例目录：config.json + data/wordlib_config.json + plugins/wordlib.py"""
    d = tempfile.mkdtemp(prefix="panel-settings-")
    with open(os.path.join(d, "config.json"), "w", encoding="utf-8") as f:
        json.dump({"BOT_NAME": "测试bot", "BOT_QQ": 740979632,
                   "MASTER_QQ": list(master)}, f, ensure_ascii=False, indent=2)
    os.makedirs(os.path.join(d, "data"), exist_ok=True)
    os.makedirs(os.path.join(d, "plugins"), exist_ok=True)
    if wordlib:
        with open(os.path.join(d, "plugins", "wordlib.py"), "w", encoding="utf-8") as f:
            f.write("# 占位\n")
    if wordlib_cfg:
        with open(os.path.join(d, "data", "wordlib_config.json"), "w", encoding="utf-8") as f:
            json.dump({"admins": list(admins), "commands": {"sign1": "签到"}},
                      f, ensure_ascii=False, indent=2)
    return d


class QQInputTest(unittest.TestCase):
    def test_qq_list_normalizes(self):
        self.assertEqual(panel_api.qq_list("1,2 3\n4"), ["1", "2", "3", "4"])
        self.assertEqual(panel_api.qq_list("2840771765，245524106、2840771765"), ["2840771765", "245524106"])
        self.assertEqual(panel_api.qq_list([740979632, " 1 ", "", 740979632]), ["740979632", "1"])
        self.assertEqual(panel_api.qq_list(None), [])
        self.assertEqual(panel_api.qq_list(123), [])

    def test_is_qq(self):
        self.assertTrue(panel_api.is_qq("2840771765"))
        self.assertTrue(panel_api.is_qq("12345"))
        self.assertFalse(panel_api.is_qq("1234"))          # 太短
        self.assertFalse(panel_api.is_qq("1234567890123"))  # 太长
        self.assertFalse(panel_api.is_qq("abc"))
        self.assertFalse(panel_api.is_qq("123a"))
        self.assertFalse(panel_api.is_qq(12345))


class SettingsApiTest(unittest.TestCase):
    num = 987654          # 假实例编号，别撞真实例

    def setUp(self):
        self.dir = _make_instance()
        self.bot = {"name": "测试bot", "qq": "740979632", "dir": self.dir, "master": "2840771765"}
        panel_api.BOTS[self.num] = self.bot
        self._notify = panel_api._notify_bot_reload
        panel_api._notify_bot_reload = lambda qq: None      # 单测不真的给进程发信号
        self.client = panel_api.app.test_client()
        with self.client.session_transaction() as sess:
            sess["authenticated"] = True

    def tearDown(self):
        panel_api.BOTS.pop(self.num, None)
        panel_api._notify_bot_reload = self._notify
        shutil.rmtree(self.dir, ignore_errors=True)

    # ---------- 读 ----------
    def test_get_returns_current_values(self):
        r = self.client.get(f"/api/bot/{self.num}/settings")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()["data"]
        self.assertEqual(data["master"], ["2840771765"])
        self.assertEqual(data["admins"], ["245524106"])
        self.assertTrue(data["has_wordlib_plugin"])

    # ---------- 写 ----------
    def test_save_writes_master_and_admins(self):
        r = self.client.post(f"/api/bot/{self.num}/settings", json={
            "master": ["2840771765", "10001"], "admins": "245524106，10002",
        }, headers=CSRF)
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        self.assertTrue(r.get_json()["ok"])

        cfg = _read_json(os.path.join(self.dir, "config.json"))
        self.assertEqual(cfg["MASTER_QQ"], [2840771765, 10001])       # 与现网一致存整数
        wl = _read_json(os.path.join(self.dir, "data", "wordlib_config.json"))
        self.assertEqual(wl["admins"], ["245524106", "10002"])       # admins 存字符串
        self.assertEqual(wl["commands"], {"sign1": "签到"})           # 其它配置一字节不动
        self.assertEqual(self.bot["master"], "2840771765、10001")     # 面板显示同步更新

    def test_save_empty_admins_clears_them(self):
        r = self.client.post(f"/api/bot/{self.num}/settings",
                             json={"master": ["2840771765"], "admins": ""}, headers=CSRF)
        self.assertEqual(r.status_code, 200)
        wl = _read_json(os.path.join(self.dir, "data", "wordlib_config.json"))
        self.assertEqual(wl["admins"], [])

    def test_invalid_input_writes_nothing(self):
        before_cfg = _read_bytes(os.path.join(self.dir, "config.json"))
        before_wl = _read_bytes(os.path.join(self.dir, "data", "wordlib_config.json"))

        r = self.client.post(f"/api/bot/{self.num}/settings",
                             json={"master": [], "admins": ["245524106"]}, headers=CSRF)
        self.assertEqual(r.status_code, 400)
        self.assertIn("master", r.get_json()["field_errors"])

        r = self.client.post(f"/api/bot/{self.num}/settings",
                             json={"master": ["2840771765"], "admins": ["abc"]}, headers=CSRF)
        self.assertEqual(r.status_code, 400)
        self.assertIn("admins", r.get_json()["field_errors"])

        self.assertEqual(_read_bytes(os.path.join(self.dir, "config.json")), before_cfg)
        self.assertEqual(_read_bytes(os.path.join(self.dir, "data", "wordlib_config.json")), before_wl)

    def test_without_wordlib_plugin_admins_skipped(self):
        shutil.rmtree(os.path.join(self.dir, "plugins"))
        os.makedirs(os.path.join(self.dir, "plugins"))
        os.remove(os.path.join(self.dir, "data", "wordlib_config.json"))
        r = self.client.post(f"/api/bot/{self.num}/settings",
                             json={"master": ["2840771765"], "admins": ["10002"]}, headers=CSRF)
        self.assertEqual(r.status_code, 200)
        self.assertIn("跳过", r.get_json()["msg"])
        self.assertFalse(os.path.exists(os.path.join(self.dir, "data", "wordlib_config.json")))

    def test_unknown_bot_404(self):
        r = self.client.post("/api/bot/123123123/settings",
                             json={"master": ["2840771765"]}, headers=CSRF)
        self.assertEqual(r.status_code, 404)


class SettingsPageTest(unittest.TestCase):
    num = 987655

    def setUp(self):
        self.dir = _make_instance()
        panel_api.BOTS[self.num] = {"name": "测试bot", "qq": "740979632",
                                    "dir": self.dir, "master": "2840771765"}
        self.client = panel_api.app.test_client()
        with self.client.session_transaction() as sess:
            sess["authenticated"] = True

    def tearDown(self):
        panel_api.BOTS.pop(self.num, None)
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_page_fragment_has_current_values(self):
        r = self.client.get(f"/api/bot/{self.num}/ui/page/settings")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()["data"]
        self.assertEqual(data["page"], "settings")
        self.assertIn("save", data["actions"])
        html = data["html"]
        self.assertIn('id="setMasterQQ"', html)
        self.assertIn('id="setAdmins"', html)
        self.assertIn("2840771765", html)          # 当前主人
        self.assertIn("245524106", html)           # 当前管理员
        self.assertIn("测试bot", data["action_title"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""B站推送插件（plugins/haruka.py）的单元测试。

覆盖的都是"不联网也应当成立"的性质：输入解析、wbi 签名、动态/直播数据归一化、
轮询的状态迁移与基线语义、订阅存储、推送路由与模板渲染、以及**面板 schema 的完整性**。

跑法：cd /root/mybot2 && python3 -m unittest tests.test_haruka -v
"""
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (ROOT, os.path.join(ROOT, "web")):
    if path not in sys.path:
        sys.path.insert(0, path)

# 插件导入期会读配置、建数据目录、起后台线程 —— 测试里全部替换掉：
#   1) 数据目录指到临时目录（别碰仓库/实例的 data/）
#   2) HARUKA_NO_POLL=1 关掉轮询线程（导入不该产生网络活动）
#   3) utils.config 指向临时 config.json（避免刷“config.json 不存在”的警告）
_TMP = tempfile.mkdtemp(prefix="haruka-test-")
os.environ["HARUKA_DATA_DIR"] = _TMP
os.environ["HARUKA_NO_POLL"] = "1"

import utils.config as ucfg                                    # noqa: E402

ucfg.CONFIG_FILE = os.path.join(_TMP, "config.json")
with open(ucfg.CONFIG_FILE, "w", encoding="utf-8") as _fh:
    json.dump({"MASTER_QQ": [10001], "ADMIN_QQ": [10003], "BOT_QQ": 10002,
               "BOT_NAME": "测试bot"}, _fh)

import plugins.haruka as hb                                    # noqa: E402
import config_schema as cs                                     # noqa: E402

# 单测没有真实 WS 连接：别让 _send_push 每次等 10 秒
hb._wait_ws_ready = lambda *args, **kwargs: None


def _leaf_paths(node, prefix=""):
    """展开配置默认值的全部叶子路径（dict 递归，其它类型即叶子）"""
    if isinstance(node, dict) and node:
        for key, value in node.items():
            yield from _leaf_paths(value, f"{prefix}.{key}" if prefix else key)
    else:
        yield prefix


class SchemaTest(unittest.TestCase):
    """面板表单靠 __config_schema__ 生成：声明必须能解析、且覆盖全部默认项"""

    def setUp(self):
        self.fields, self.errors = cs.normalize_schema(hb.__config_schema__)

    def test_schema_parses_without_error(self):
        self.assertEqual(self.errors, [])

    def test_every_default_leaf_is_declared(self):
        declared = {f.get("path") or name for name, f in self.fields.items()}
        missing = [p for p in _leaf_paths(hb._DEFAULTS)
                   if p not in declared and p != "command_labels"]
        self.assertEqual(missing, [], f"这些配置项没有在面板上声明：{missing}")

    def test_declared_defaults_match_code_defaults(self):
        for name, field in self.fields.items():
            path = field.get("path") or name
            if path == "command_labels":
                continue
            self.assertTrue(cs.has_path(hb._DEFAULTS, path), f"{name} 的 path {path} 不存在")
            self.assertEqual(field.get("default"), cs.get_path(hb._DEFAULTS, path),
                             f"{name} 的 default 与 _DEFAULTS 不一致（改一处就得改两处）")

    def test_no_duplicate_paths(self):
        paths = [(f.get("path") or n) for n, f in self.fields.items()]
        self.assertEqual(len(paths), len(set(paths)), "schema 里有两个字段指向同一个配置项")


class InputTest(unittest.TestCase):
    def test_normalize_raw_strips_cq_and_whitespace(self):
        self.assertEqual(hb.normalize_raw("[CQ:at,qq=10002]  关注  546195 "), "关注 546195")
        self.assertEqual(hb.normalize_raw("　关注\n546195\u200b"), "关注 546195")
        self.assertEqual(hb.normalize_raw("[[CQ:image,file=x]]"), "[]")

    def test_extract_uid_forms(self):
        cases = {
            "546195": "546195",
            "  546195 ": "546195",
            "UID:546195": "546195",
            "uid：546195": "546195",
            "https://space.bilibili.com/546195/dynamic": "546195",
            "space.bilibili.com/546195": "546195",
            "https://m.bilibili.com/space/546195": "546195",
            "“546195”": "546195",
        }
        for raw, expected in cases.items():
            self.assertEqual(hb.extract_uid(raw), expected, raw)

    def test_extract_uid_rejects_non_uid(self):
        for raw in ("", "老番茄", "https://www.bilibili.com/video/BV1xx", "12a34"):
            self.assertEqual(hb.extract_uid(raw), "", raw)

    def test_arg_after(self):
        self.assertEqual(hb.arg_after("关注 546195", "关注"), "546195")
        self.assertEqual(hb.arg_after("关注：546195", "关注"), "546195")
        self.assertEqual(hb.arg_after("关注", "关注"), "")
        self.assertEqual(hb.arg_after("关注列表", "关注列表"), "")


class WbiTest(unittest.TestCase):
    def test_mixin_key_length(self):
        key = hb.wbi_mixin_key("7cd084941338484aae1ad9425b84077c",
                               "4932caff0ff746eab6f01bf08b70ac45")
        self.assertEqual(len(key), 32)

    def test_sign_is_deterministic_and_time_dependent(self):
        params = {"host_mid": 546195, "features": "itemOpusStyle"}
        first = hb.wbi_sign(params, "img", "sub", wts=1700000000)
        again = hb.wbi_sign(params, "img", "sub", wts=1700000000)
        later = hb.wbi_sign(params, "img", "sub", wts=1700000001)
        self.assertEqual(first, again)
        self.assertNotEqual(first["w_rid"], later["w_rid"])
        self.assertEqual(str(first["wts"]), "1700000000")   # wbi 把全部值字符串化
        self.assertEqual(set(first), {"host_mid", "features", "wts", "w_rid"})

    def test_sign_strips_illegal_characters(self):
        signed = hb.wbi_sign({"q": "a!b'c(d)e*f"}, "img", "sub", wts=1)
        self.assertEqual(signed["q"], "abcdef")


class DynamicTest(unittest.TestCase):
    def test_full_item_with_draw(self):
        item = {
            "id_str": "1232186887046692873",
            "type": "DYNAMIC_TYPE_DRAW",
            "modules": {
                "module_author": {"mid": 546195, "name": "老番茄", "pub_ts": 1700000000},
                "module_dynamic": {
                    "desc": {"text": "今天发个图"},
                    "major": {"draw": {"items": [{"src": "https://i0.hdslb.com/a.jpg"}]}},
                },
            },
        }
        normalized = hb.normalize_dynamic_full(item)
        self.assertEqual(normalized["id"], "1232186887046692873")
        self.assertEqual(normalized["name"], "老番茄")
        self.assertEqual(normalized["kind"], "发布了新图文动态")
        self.assertEqual(normalized["text"], "今天发个图")
        self.assertEqual(normalized["cover"], "https://i0.hdslb.com/a.jpg")
        self.assertEqual(normalized["url"], "https://t.bilibili.com/1232186887046692873")
        self.assertEqual(normalized["ts"], 1700000000)

    def test_full_item_archive_title_and_cover(self):
        item = {
            "id_str": "42",
            "type": 8,
            "modules": {
                "module_author": {"mid": 1, "name": "UP"},
                "module_dynamic": {"major": {"archive": {"title": "新视频", "cover": "c.jpg"}}},
            },
        }
        normalized = hb.normalize_dynamic_full(item)
        self.assertEqual(normalized["kind"], "发布了新投稿")
        self.assertEqual(normalized["title"], "新视频")
        self.assertEqual(normalized["cover"], "c.jpg")

    def test_full_item_opus_summary_fallback(self):
        item = {
            "id_str": "7",
            "type": "DYNAMIC_TYPE_WORD",
            "modules": {
                "module_author": {},
                "module_dynamic": {"major": {"opus": {"summary": {"text": "摘要正文"},
                                                     "pics": [{"url": "p.jpg"}]}}},
            },
        }
        normalized = hb.normalize_dynamic_full(item)
        self.assertEqual(normalized["text"], "摘要正文")
        self.assertEqual(normalized["cover"], "p.jpg")

    def test_full_item_invalid(self):
        self.assertIsNone(hb.normalize_dynamic_full(None))
        self.assertIsNone(hb.normalize_dynamic_full({}))
        self.assertIsNone(hb.normalize_dynamic_full({"id_str": "abc"}))

    def test_opus_item(self):
        normalized = hb.normalize_dynamic_opus({
            "opus_id": "1232186887046692873",
            "content": "图文内容",
            "cover": {"url": "https://i0.hdslb.com/b.jpg"},
        })
        self.assertEqual(normalized["id"], "1232186887046692873")
        self.assertEqual(normalized["kind"], "发布了新图文动态")
        self.assertEqual(normalized["cover"], "https://i0.hdslb.com/b.jpg")
        self.assertIsNone(hb.normalize_dynamic_opus({"opus_id": ""}))

    def test_merge_dedupes_and_sorts(self):
        full = [{"id_str": "20", "modules": {"module_author": {"name": "A"},
                                             "module_dynamic": {"desc": {"text": "full"}}}}]
        opus = [{"opus_id": "20", "content": "opus-dup"},
                {"opus_id": "21", "content": "opus-new"}]
        merged = hb.merge_dynamics(full, opus)
        self.assertEqual([d["id"] for d in merged], ["20", "21"])
        self.assertEqual(merged[0]["text"], "full")   # 完整接口优先
        self.assertEqual(merged[1]["text"], "opus-new")

    def test_kind_text(self):
        self.assertEqual(hb.kind_text(1), "转发了一条动态")
        self.assertEqual(hb.kind_text("DYNAMIC_TYPE_AV"), "发布了新投稿")
        self.assertEqual(hb.kind_text(999999), "发布了新动态")


class LiveTest(unittest.TestCase):
    def test_norm_live_status_treats_loop_as_offline(self):
        self.assertEqual(hb.norm_live_status(2), 0)
        self.assertEqual(hb.norm_live_status(1), 1)
        self.assertEqual(hb.norm_live_status("x"), 0)

    def test_live_transition(self):
        self.assertEqual(hb.live_transition(0, 1), "on")
        self.assertEqual(hb.live_transition(1, 0), "off")
        self.assertEqual(hb.live_transition(1, 2), "off")   # 2=轮播，视为下播
        self.assertIsNone(hb.live_transition(1, 1))
        self.assertIsNone(hb.live_transition(0, 0))

    def test_parse_live_time(self):
        stamp = hb.parse_live_time("2026-10-27 14:00:00")
        self.assertGreater(stamp, 0)
        self.assertEqual(hb.parse_live_time(0), 0)
        self.assertEqual(hb.parse_live_time(""), 0)
        self.assertEqual(hb.parse_live_time("not-a-time"), 0)

    def test_human_duration(self):
        self.assertEqual(hb.human_duration(45), "45 秒")
        self.assertEqual(hb.human_duration(600), "10 分钟")
        self.assertEqual(hb.human_duration(3600), "1 小时")
        self.assertEqual(hb.human_duration(3720), "1 小时 2 分钟")
        self.assertEqual(hb.human_duration(0), "")
        self.assertEqual(hb.human_duration("x"), "")


class FormatTest(unittest.TestCase):
    def test_truncate(self):
        self.assertEqual(hb.truncate_text("", 10), "（无正文）")
        self.assertEqual(hb.truncate_text("abcdef", 0), "abcdef")
        self.assertEqual(hb.truncate_text("abcdef", 3), "abc…")
        self.assertEqual(hb.truncate_text("  abc  ", 10), "abc")

    def test_format_falls_back_on_bad_placeholder(self):
        tpl = "{name} 开播了 {unknown}"
        self.assertEqual(hb.format_push(tpl, name="A"), tpl)      # 未知占位符 → 原文
        self.assertEqual(hb.format_push("{name} 开播了", name="A"), "A 开播了")


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(prefix="haruka-store-"), "data.json")
        self.store = hb._Store(self.path)

    def test_add_and_remove_and_persist(self):
        target = ("group", "123")
        self.assertTrue(self.store.add_sub(target, "546195", "老番茄"))
        self.assertTrue(self.store.has_sub(target, "546195"))
        self.assertEqual(self.store.name("546195"), "老番茄")
        self.assertEqual(self.store.uids_for("live"), ["546195"])
        self.assertEqual(self.store.uids_for("dynamic"), ["546195"])

        reloaded = hb._Store(self.path).load()
        self.assertIn("546195", reloaded["subs"]["group:123"])

        self.assertTrue(self.store.remove_sub(target, "546195"))
        self.assertFalse(self.store.has_sub(target, "546195"))
        self.assertFalse(self.store.remove_sub(target, "546195"))
        self.assertEqual(self.store.uids_for("live"), [])

    def test_flags_scope_by_target(self):
        group, private = ("group", "1"), ("private", "2")
        self.store.add_sub(group, "9", "A")
        self.store.add_sub(private, "9", "A")
        self.store.set_flag(group, "9", "live", False)
        self.assertEqual(self.store.uids_for("live"), ["9"])       # 私聊仍要直播推送
        self.assertEqual(len(self.store.targets_for("9", "live")), 1)
        self.assertFalse(self.store.set_flag(group, "8", "live", True))

    def test_dynamic_baseline_semantics(self):
        self.assertIsNone(self.store.dynamic_last("5"))            # None=待建基线
        self.store.set_dynamic_last("5", "1234")
        self.assertEqual(self.store.dynamic_last("5"), "1234")

    def test_live_state_only_written_when_changed(self):
        self.assertIsNone(self.store.live_state("7"))
        state = {"status": 1, "since": 100, "title": "t", "ts": 200}
        self.assertTrue(self.store.set_live_state("7", state))
        self.assertFalse(self.store.set_live_state("7", dict(state)))
        self.assertEqual(self.store.live_state("7")["status"], 1)

    def test_group_permission_default_on_and_drop_group(self):
        self.assertTrue(self.store.group_perm("123"))               # 默认仅管理员
        self.store.set_group_perm("123", False)
        self.assertFalse(self.store.group_perm("123"))
        self.store.add_sub(("group", "123"), "1", "A")
        self.store.add_sub(("group", "123"), "2", "B")
        self.assertEqual(self.store.drop_group("123"), 2)
        self.assertEqual(self.store.drop_group("123"), 0)

    def test_corrupted_file_is_survivable(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        store = hb._Store(self.path)
        store.load()
        self.assertEqual(store.uids_for("live"), [])


class PollTest(unittest.TestCase):
    """轮询语义：先建基线、按 id 增量推送、状态迁移只在变化时触发"""

    def setUp(self):
        self.store = hb._Store(os.path.join(tempfile.mkdtemp(prefix="haruka-poll-"), "d.json"))
        self._old_store, hb._store = hb._store, self.store
        self._old_mem = dict(hb._live_mem)
        hb._live_mem.clear()
        self.sent = []
        self._old_push_dyn = hb.push_dynamic
        self._old_push_on = hb.push_live_on
        self._old_push_off = hb.push_live_off
        self._old_fetch = hb.fetch_dynamics
        self._old_live = hb._client.live_status
        hb.push_dynamic = lambda uid, item: self.sent.append(("dyn", uid, item["id"])) or 1
        hb.push_live_on = lambda uid, info, name=None: self.sent.append(("on", uid, info.get("title"))) or 1
        hb.push_live_off = lambda uid, info, since=0, name=None: self.sent.append(("off", uid, since)) or 1

    def tearDown(self):
        hb._store = self._old_store
        hb._live_mem.clear()
        hb._live_mem.update(self._old_mem)
        hb.push_dynamic = self._old_push_dyn
        hb.push_live_on = self._old_push_on
        hb.push_live_off = self._old_push_off
        hb.fetch_dynamics = self._old_fetch
        hb._client.live_status = self._old_live

    def test_dynamic_baseline_then_incremental(self):
        self.store.add_sub(("group", "1"), "546195", "老番茄")
        hb.fetch_dynamics = lambda uid: [{"id": "10", "text": "a"}, {"id": "11", "text": "b"}]
        hb.poll_dynamic()
        self.assertEqual(self.sent, [])                              # 首轮只建基线
        self.assertEqual(self.store.dynamic_last("546195"), "11")

        hb.fetch_dynamics = lambda uid: [{"id": "10"}, {"id": "11"}, {"id": "12"}]
        hb.poll_dynamic()
        self.assertEqual(self.sent, [("dyn", "546195", "12")])
        self.assertEqual(self.store.dynamic_last("546195"), "12")

    def test_dynamic_pushes_at_most_max_new_per_poll(self):
        self.store.add_sub(("group", "1"), "546195", "A")
        self.store.set_dynamic_last("546195", "10")
        hb.fetch_dynamics = lambda uid: [{"id": str(i)} for i in range(11, 21)]
        hb.poll_dynamic()
        self.assertEqual([x[2] for x in self.sent], ["11", "12", "13"])
        self.assertEqual(self.store.dynamic_last("546195"), "13")

        hb.poll_dynamic()                                             # 剩下的下一轮继续推
        self.assertEqual([x[2] for x in self.sent][3:], ["14", "15", "16"])

    def test_live_transitions(self):
        self.store.add_sub(("group", "1"), "546195", "A")
        info = {"uid": 546195, "live_status": 0, "title": "T", "uname": "A",
                "live_time": 0, "room_id": 999}
        hb._client.live_status = lambda uids: {"546195": dict(info, live_status=0)}
        hb.poll_live()                                                # 首轮建基线
        self.assertEqual(self.sent, [])

        hb._client.live_status = lambda uids: {"546195": dict(info, live_status=1)}
        hb.poll_live()
        self.assertEqual(self.sent, [("on", "546195", "T")])

        hb._client.live_status = lambda uids: {"546195": dict(info, live_status=1)}
        hb.poll_live()                                                # 状态没变不重复推
        self.assertEqual(len(self.sent), 1)

        hb._client.live_status = lambda uids: {"546195": dict(info, live_status=0)}
        hb.poll_live()
        self.assertEqual(self.sent[-1][0], "off")

    def test_restart_after_long_downtime_stays_silent(self):
        self.store.add_sub(("group", "1"), "546195", "A")
        self.store.set_live_state("546195", {"status": 0, "since": 0, "title": "",
                                             "ts": int(hb.time.time()) - hb._DOWNTIME_TOLERANCE - 60})
        hb._client.live_status = lambda uids: {"546195": {"live_status": 1, "title": "T",
                                                          "uname": "A", "live_time": 0}}
        hb.poll_live()
        self.assertEqual(self.sent, [])
        self.assertEqual(self.store.live_state("546195")["status"], 1)


class RoutingTest(unittest.TestCase):
    """推送路由：群开关当总闸；@全体只在要求时出现；模板渲染正确"""

    def setUp(self):
        self.store = hb._Store(os.path.join(tempfile.mkdtemp(prefix="haruka-route-"), "d.json"))
        self._old_store, hb._store = hb._store, self.store
        self.sent = []
        self._old_send = hb.send_message
        self._old_toggle = hb._pt_enabled
        hb.send_message = lambda event, message: self.sent.append((event, message))
        hb._pt_enabled = lambda gid, plugin: str(gid) == "123"
        self.store.add_sub(("group", "123"), "546195", "老番茄")
        self._cfg = hb._CFG
        hb._CFG = hb._deep_merge(hb._DEFAULTS, {})

    def tearDown(self):
        hb._store = self._old_store
        hb.send_message = self._old_send
        hb._pt_enabled = self._old_toggle
        hb._CFG = self._cfg

    def test_dynamic_push_segments(self):
        item = {"id": "1", "kind": "发布了新图文动态", "text": "正文",
                "cover": "https://i0.hdslb.com/x.jpg", "url": "https://t.bilibili.com/1"}
        sent = hb.push_dynamic("546195", item)
        self.assertEqual(sent, 1)
        event, segments = self.sent[0]
        self.assertEqual(event, {"message_type": "group", "group_id": 123})
        self.assertEqual(segments[0]["type"], "text")
        self.assertIn("老番茄", segments[0]["data"]["text"])
        self.assertIn("https://t.bilibili.com/1", segments[0]["data"]["text"])
        self.assertEqual(segments[1], {"type": "image",
                                       "data": {"file": "https://i0.hdslb.com/x.jpg"}})

    def test_group_toggle_off_blocks_push(self):
        hb._pt_enabled = lambda gid, plugin: False
        item = {"id": "1", "kind": "发布了新动态", "text": "正文", "cover": "", "url": "u"}
        self.assertEqual(hb.push_dynamic("546195", item), 0)
        self.assertEqual(self.sent, [])

    def test_live_push_at_all_only_when_flag_on(self):
        self.store.set_flag(("group", "123"), "546195", "at", True)
        info = {"title": "直播标题", "area_v2_parent_name": "游戏", "area_v2_name": "单机",
                "room_id": 999, "cover_from_user": "https://i0.hdslb.com/c.jpg", "uname": "老番茄"}
        hb.push_live_on("546195", info)
        self.assertEqual(self.sent[0][1][0]["type"], "text")        # 默认不 @全体

        hb._CFG["push"]["live_at"] = True
        self.sent.clear()
        hb.push_live_on("546195", info)
        self.assertEqual(self.sent[0][1][0], {"type": "at", "data": {"qq": "all"}})
        self.assertIn("游戏 / 单机", self.sent[0][1][1]["data"]["text"])
        self.assertIn("https://live.bilibili.com/999", self.sent[0][1][1]["data"]["text"])

    def test_live_off_includes_duration(self):
        hb.push_live_off("546195", {"room_id": 1}, since=int(hb.time.time()) - 3720)
        text = self.sent[0][1][0]["data"]["text"]
        self.assertIn("下播了", text)
        self.assertIn("1 小时 2 分钟", text)

    def test_private_target_uses_user_id(self):
        self.store.add_sub(("private", "555"), "546195", "老番茄")
        hb.push_live_off("546195", {"room_id": 1}, since=0)
        events = [event for event, _msg in self.sent]
        self.assertIn({"message_type": "private", "user_id": 555}, events)
        self.assertIn({"message_type": "group", "group_id": 123}, events)


class EventTest(unittest.TestCase):
    def setUp(self):
        self.store = hb._Store(os.path.join(tempfile.mkdtemp(prefix="haruka-event-"), "d.json"))
        self._old_store, hb._store = hb._store, self.store
        self.sent = []
        self._old_send = hb.send_message
        self._old_admin = hb._is_group_admin
        hb.send_message = lambda event, message: self.sent.append((event, message))
        hb._is_group_admin = lambda gid, uid: False          # 单测不查 NapCat

    def tearDown(self):
        hb._store = self._old_store
        hb.send_message = self._old_send
        hb._is_group_admin = self._old_admin

    def test_non_message_events_are_ignored(self):
        self.assertFalse(hb.handle({"post_type": "meta_event"}))
        self.assertFalse(hb.handle({"post_type": "message", "message_type": "guild"}))
        self.assertFalse(hb.handle({"post_type": "message", "message_type": "private",
                                    "sub_type": "group", "raw_message": "关注 1"}))
        self.assertFalse(hb.handle({"post_type": "message", "message_type": "group",
                                    "raw_message": "今天天气不错"}))

    def test_kick_me_cleans_group_subscriptions(self):
        self.store.add_sub(("group", "888"), "546195", "老番茄")
        handled = hb.handle({
            "post_type": "notice", "notice_type": "group_decrease",
            "group_id": 888, "user_id": 10002, "self_id": 10002, "sub_type": "kick_me",
        })
        self.assertTrue(handled)
        self.assertEqual(self.store.uids_for("live"), [])
        # 别人退群不该清订阅
        self.store.add_sub(("group", "888"), "546195", "老番茄")
        self.assertFalse(hb.handle({
            "post_type": "notice", "notice_type": "group_decrease",
            "group_id": 888, "user_id": 12345, "self_id": 10002, "sub_type": "leave",
        }))
        self.assertEqual(self.store.uids_for("live"), ["546195"])

    def test_list_command_respects_group_permission(self):
        hb._ADMIN_CACHE.clear()
        hb._CFG = hb._deep_merge(hb._DEFAULTS, {})
        group_msg = {"post_type": "message", "message_type": "group", "group_id": 123,
                     "user_id": 999, "self_id": 10002}

        # ① 普通成员、群权限开着：@了机器人 → 回权限不足
        hb.handle({**group_msg, "raw_message": "[CQ:at,qq=10002] 关注列表"})
        self.assertEqual(self.sent[-1][1], hb._DEFAULTS["replies"]["no_perm"])

        # ② 普通成员、群权限开着、没 @：静默放行（普通聊天「关注列表」不该被吃掉）
        before = len(self.sent)
        self.assertFalse(hb.handle({**group_msg, "raw_message": "关注列表"}))
        self.assertEqual(len(self.sent), before)

        # ③ 关掉群权限后，普通成员可看（空列表提示）
        self.store.set_group_perm(123, False)
        hb.handle({**group_msg, "raw_message": "关注列表"})
        self.assertEqual(self.sent[-1][1], hb._DEFAULTS["replies"]["list_empty"])

    def test_require_at_gate(self):
        hb._CFG = hb._deep_merge(hb._DEFAULTS, {"require_at": True})
        self.store.set_group_perm(123, False)          # 权限放开，只看 @ 门禁
        group_msg = {"post_type": "message", "message_type": "group", "group_id": 123,
                     "user_id": 999, "self_id": 10002}

        self.assertFalse(hb.handle({**group_msg, "raw_message": "关注列表"}))
        self.assertEqual(self.sent, [])

        hb.handle({**group_msg, "raw_message": "[CQ:at,qq=10002] 关注列表"})
        self.assertEqual(self.sent[-1][1], hb._DEFAULTS["replies"]["list_empty"])

        # 以机器人名开头也认（BOT_NAME=测试bot）
        hb.handle({**group_msg, "raw_message": "测试bot 关注列表"})
        self.assertEqual(self.sent[-1][1], hb._DEFAULTS["replies"]["list_empty"])
        hb._CFG = hb._deep_merge(hb._DEFAULTS, {})

    def test_help_and_usage(self):
        hb._CFG = hb._deep_merge(hb._DEFAULTS, {})
        self.store.set_group_perm(123, False)
        hb.handle({"post_type": "message", "message_type": "group", "group_id": 123,
                   "user_id": 999, "raw_message": hb.cfgv("commands.sub", "关注")})
        self.assertIn("用法", self.sent[-1][1])

        hb.handle({"post_type": "message", "message_type": "group", "group_id": 123,
                   "user_id": 999, "raw_message": hb.cfgv("commands.help", "B站帮助")})
        self.assertIn("B站推送", self.sent[-1][1])


class PrivilegeTest(unittest.TestCase):
    """管理员 = 全插件通用（config.json 的 ADMIN_QQ）；主人仍最高"""

    def test_admin_is_privileged(self):
        self.assertTrue(hb._is_master("10001"))
        self.assertFalse(hb._is_master("10003"))
        self.assertTrue(hb._is_admin("10003"))
        self.assertTrue(hb._is_privileged("10003"))
        self.assertFalse(hb._is_admin("999"))
        self.assertFalse(hb._is_privileged("999"))

    def test_admin_can_run_plugin_commands(self):
        store = hb._Store(os.path.join(tempfile.mkdtemp(prefix="haruka-admin-"), "d.json"))
        old_store, hb._store = hb._store, store
        sent = []
        old_send, old_admin = hb.send_message, hb._is_group_admin
        hb.send_message = lambda event, message: sent.append((event, message))
        hb._is_group_admin = lambda gid, uid: False       # 不是群管理员，只是"全局管理员"
        hb._CFG = hb._deep_merge(hb._DEFAULTS, {})
        try:
            handled = hb.handle({"post_type": "message", "message_type": "group",
                                 "group_id": 123, "user_id": 10003,
                                 "raw_message": "关注列表"})
            self.assertTrue(handled)
            self.assertEqual(sent[-1][1], hb._DEFAULTS["replies"]["list_empty"])
        finally:
            hb._store = old_store
            hb.send_message = old_send
            hb._is_group_admin = old_admin


class ConfigTest(unittest.TestCase):
    def test_deep_merge_keeps_missing_defaults(self):
        merged = hb._deep_merge({"a": {"b": 1, "c": 2}, "d": 3}, {"a": {"b": 9}})
        self.assertEqual(merged, {"a": {"b": 9, "c": 2}, "d": 3})

    def test_cfgv_paths(self):
        hb._CFG = hb._deep_merge(hb._DEFAULTS, {"poll": {"live_interval": 90}})
        self.assertEqual(hb.cfgv("poll.live_interval"), 90)
        self.assertEqual(hb.cfgv("poll.dynamic_interval", 0), 180)
        self.assertEqual(hb.cfgv("nope.nothing", "x"), "x")


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""插件配置 schema：点号路径（path）语义与"空改动保存不改坏配置"的回归测试。

跑法：cd /root/mybot2 && python3 -m unittest tests.test_config_schema_path -v
"""
import copy
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'web'))
import config_schema as cs          # noqa: E402

DECL = {
    "enabled": {"type": "bool", "label": "启用", "path": "settings.enabled"},
    "rank_top_n": {"type": "number", "label": "排行条数", "path": "settings.rank_top_n",
                   "min": 1, "max": 100},
    "sign1": {"type": "text", "label": "签到指令", "path": "commands.sign1"},
    "sign_success": {"type": "textarea", "label": "签到回复", "path": "messages.sign_success"},
    "glm_key": {"type": "password", "label": "GLM Key", "path": "glm.api_key"},
    "aliases": {"type": "list", "item_type": "text", "label": "管理员", "path": "admins"},
}
CUR = {
    "_note": "别动我",
    "settings": {"enabled": True, "rank_top_n": 10},
    "commands": {"sign1": "依星签到"},
    "messages": {"sign_success": "签到成功！[favor]"},
    "command_labels": {"依星签到": "每日签到"},
    "glm": {"api_key": "sk-xxx", "model": "glm-4v-flash"},
    "admins": ["245524106"],
}


class PathTest(unittest.TestCase):
    def setUp(self):
        self.fields, errs = cs.normalize_schema(DECL)
        self.assertEqual(errs, [])

    def test_values_read_from_path(self):
        p = cs.build_payload(DECL, CUR)
        got = {f['name']: f['value'] for f in p['fields']}
        self.assertEqual(got['enabled'], True)
        self.assertEqual(got['rank_top_n'], 10)
        self.assertEqual(got['sign1'], '依星签到')
        self.assertEqual(got['glm_key'], 'sk-xxx')
        self.assertTrue(all(not f['unset'] for f in p['fields']))

    def test_missing_path_marks_unset_and_uses_default(self):
        p = cs.build_payload({"new_num": {"type": "number", "path": "settings.new_num", "min": 5}}, CUR)
        f = p['fields'][0]
        self.assertTrue(f['unset'])
        self.assertEqual(f['value'], 5, '数值默认值必须落在 min 内，否则"直接保存"就报越界')

    def test_write_back_keeps_unknown_keys(self):
        ok, merged, errs = cs.validate_and_merge(
            self.fields, CUR, {'enabled': 'false', 'rank_top_n': '25', 'sign1': '签到啦',
                               'glm_key': 'sk-new', 'extra_top': 1}, strict=True)
        self.assertTrue(ok, errs)
        self.assertFalse(merged['settings']['enabled'])
        self.assertEqual(merged['settings']['rank_top_n'], 25)
        self.assertEqual(merged['commands']['sign1'], '签到啦')
        self.assertEqual(merged['glm']['api_key'], 'sk-new')
        # 未声明的键与未被控件接管的兄弟键都要原样保留
        self.assertEqual(merged['_note'], '别动我')
        self.assertEqual(merged['command_labels'], {'依星签到': '每日签到'})
        self.assertEqual(merged['glm']['model'], 'glm-4v-flash')
        self.assertEqual(merged['extra_top'], 1)

    def test_original_dict_not_mutated(self):
        snapshot = copy.deepcopy(CUR)
        cs.validate_and_merge(self.fields, CUR, {'rank_top_n': 99}, strict=True)
        self.assertEqual(CUR, snapshot, '必须深拷贝：否则会改到调用方持有的子字典')

    def test_range_violation_reported_per_field(self):
        ok, _merged, errs = cs.validate_and_merge(self.fields, CUR, {'rank_top_n': '999'}, strict=True)
        self.assertFalse(ok)
        self.assertIn('rank_top_n', errs)

    def test_empty_save_is_byte_identical(self):
        """面板"什么都不改直接保存"不得改变配置文件（含未声明键与段结构）"""
        p = cs.build_payload(DECL, CUR)
        submitted = {f['name']: f['value'] for f in p['fields']}
        ok, merged, errs = cs.validate_and_merge(self.fields, CUR, submitted, strict=True)
        self.assertTrue(ok, errs)
        self.assertEqual(json.dumps(merged, ensure_ascii=False, sort_keys=True),
                         json.dumps(CUR, ensure_ascii=False, sort_keys=True))

    def test_unset_field_default_is_not_materialized(self):
        """声明了但配置里没有的键，保持默认值保存不得把它塞进配置"""
        decl = dict(DECL)
        decl['timeout'] = {"type": "number", "path": "settings.timeout", "min": 5, "default": 30}
        fields, _ = cs.normalize_schema(decl)
        p = cs.build_payload(decl, CUR)
        submitted = {f['name']: f['value'] for f in p['fields']}
        ok, merged, errs = cs.validate_and_merge(fields, CUR, submitted, strict=True)
        self.assertTrue(ok, errs)
        self.assertNotIn('timeout', merged.get('settings', {}))
        # 用户真的改了值就要写进去
        submitted['timeout'] = 45
        ok, merged2, _ = cs.validate_and_merge(fields, CUR, submitted, strict=True)
        self.assertEqual(merged2['settings']['timeout'], 45)

    def test_required_missing_is_reported(self):
        """required 的语义（与桌面端一致）：合并后没有值就报错，不管配置里原本有没有"""
        decl = {"ghost": {"type": "text", "path": "settings.ghost", "required": True},
                "sign1": {"type": "text", "path": "commands.sign1", "required": True}}
        fields, _ = cs.normalize_schema(decl)
        ok, _m, errs = cs.validate_and_merge(fields, CUR, {'sign1': '签到啦'}, strict=True)
        self.assertFalse(ok)
        self.assertIn('ghost', errs)
        ok2, _m2, errs2 = cs.validate_and_merge(fields, CUR, {'sign1': '   '}, strict=True)
        self.assertFalse(ok2)
        self.assertIn('sign1', errs2)

    def test_bad_path_is_reported_not_crash(self):
        fields, errs = cs.normalize_schema({"x": {"type": "text", "path": "settings..y"}})
        self.assertEqual(fields, {})
        self.assertTrue(errs)


class RealPluginDeclTest(unittest.TestCase):
    """真实插件的声明必须一直可用：能解析、无错、且"空改动保存"与现有配置一致"""

    DECLS = {'wordlib': 'wordlib', 'marry': 'marry', 'pseudo': 'pseudo_persona',
             'jm_downloader': 'jm_downloader', 'video_parser': 'video_parser'}
    CFG = {'wordlib': 'wordlib_config.json', 'marry': 'marry_config.json',
           'pseudo': 'persona_config.json', 'jm_downloader': 'jm_downloader_config.json',
           'video_parser': 'video_parser_config.json'}
    INSTS = ('740979632', '2551736206')

    def _decl(self, path):
        import ast
        src = open(path, encoding='utf-8').read()
        for node in ast.parse(src).body:
            for t in getattr(node, 'targets', []):
                if getattr(t, 'id', '') == '__config_schema__':
                    return ast.literal_eval(node.value)
        return None

    def test_declared_in_plugin_sources(self):
        for qq in self.INSTS:
            for pkey, name in self.DECLS.items():
                plugin = os.path.join(ROOT, 'instances', qq, 'plugins', name + '.py')
                if not os.path.exists(plugin):
                    self.skipTest(f'实例 {qq} 不存在')
                raw = self._decl(plugin)
                self.assertIsInstance(raw, dict, f'{qq}/{name} 没有 __config_schema__')
                fields, errs = cs.normalize_schema(raw)
                self.assertEqual(errs, [], f'{qq}/{name} 声明有问题')
                self.assertGreater(len(fields), 5, f'{qq}/{name} 字段太少')

    def test_empty_save_keeps_config_unchanged(self):
        for qq in self.INSTS:
            for pkey, name in self.DECLS.items():
                plugin = os.path.join(ROOT, 'instances', qq, 'plugins', name + '.py')
                cfg_path = os.path.join(ROOT, 'instances', qq, 'data', self.CFG[pkey])
                if not (os.path.exists(plugin) and os.path.exists(cfg_path)):
                    continue
                fields, _ = cs.normalize_schema(self._decl(plugin))
                cfg = json.load(open(cfg_path, encoding='utf-8'))
                p = cs.build_payload(self._decl(plugin), cfg)
                submitted = {f['name']: f['value'] for f in p['fields']}
                ok, merged, errs = cs.validate_and_merge(fields, cfg, submitted, strict=True)
                self.assertTrue(ok, f'{qq}/{name} 空改动保存报错: {errs}')
                self.assertEqual(json.dumps(merged, ensure_ascii=False, sort_keys=True),
                                 json.dumps(cfg, ensure_ascii=False, sort_keys=True),
                                 f'{qq}/{name} 空改动保存改变了配置')


if __name__ == '__main__':
    unittest.main()

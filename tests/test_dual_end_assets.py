#!/usr/bin/env python3
"""两端共用资产的一致性测试（双端对齐铁律）。

共用文件必须是**同一份字节**，否则 Linux 面板与 Windows 桌面面板的行为会慢慢分叉：

| 资产 | Linux（主本） | Windows 桌面（副本） |
|---|---|---|
| 插件配置 schema 引擎 | `web/config_schema.py` | `src/astercore/core/config_schema.py` |
| 两端逐字相同的页面片段 | `web/panel_pages.py` | `src/astercore/web/panel_pages.py` |
| 面板外壳（骨架 + 通用交互） | `web/panel/panel.js` | `src/astercore/web/static/panel.js` |
| 面板外壳样式 | `web/panel/panel.css` | `src/astercore/web/static/panel.css` |
| 表单控件映射 + 取值 | `web/panel/cfg_form.js` | `src/astercore/web/static/cfg_form.js` |
| 表单控件样式 | `web/panel/cfg_form.css` | `src/astercore/web/static/cfg_form.css` |

Windows 端仓库不在本机时自动跳过（公开仓库的其他人跑测试不该因此失败）。
跑法：cd /root/mybot2 && python3 -m unittest tests.test_dual_end_assets -v
"""
import hashlib
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIN = '/root/astercore'

PAIRS = [
    ('web/config_schema.py', 'src/astercore/core/config_schema.py'),
    ('web/panel_pages.py', 'src/astercore/web/panel_pages.py'),
    ('web/panel/panel.js', 'src/astercore/web/static/panel.js'),
    ('web/panel/panel.css', 'src/astercore/web/static/panel.css'),
    ('web/panel/cfg_form.js', 'src/astercore/web/static/cfg_form.js'),
    ('web/panel/cfg_form.css', 'src/astercore/web/static/cfg_form.css'),
]


def md5(path):
    with open(path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


class DualEndAssetTest(unittest.TestCase):
    def test_pairs_exist_on_linux_side(self):
        for linux_rel, _win_rel in PAIRS:
            self.assertTrue(os.path.exists(os.path.join(ROOT, linux_rel)), linux_rel)

    def test_byte_identical_with_windows_side(self):
        if not os.path.isdir(WIN):
            self.skipTest('本机没有 Windows 端仓库（/root/astercore）')
        for linux_rel, win_rel in PAIRS:
            lf = os.path.join(ROOT, linux_rel)
            wf = os.path.join(WIN, win_rel)
            if not os.path.exists(wf):
                self.skipTest(f'Windows 端还没放这份资产: {win_rel}')
            self.assertEqual(md5(lf), md5(wf),
                             f'{linux_rel} 与 {win_rel} 不一致 —— 双端共用文件必须同步拷贝')

    def test_shared_js_has_no_project_specific_code(self):
        """共用表单模块里不许出现具体插件名或某一端的接口路径（否则就又耦合了）"""
        js = open(os.path.join(ROOT, 'web/panel/cfg_form.js'), encoding='utf-8').read()
        for bad in ('wordlib', 'marry', 'pseudo', 'jm_downloader', 'video_parser',
                    '/api/accounts', '/api/bot'):
            self.assertNotIn(bad, js, f'cfg_form.js 里不该出现 {bad}')
        # 外壳通过这两个钩子注入群列表，共用模块自己不去请求
        self.assertIn('groupSelectProvider', js)
        self.assertIn('onGroupRefresh', js)

    def test_shared_shell_has_no_end_specific_code(self):
        """共用外壳（panel.js）里不许写死某一端的接口路径或插件名。

        接口地址一律由各端 index.html 注入 `PANEL.endpoints`，外壳只按名字取；
        写死就会让"双端同一套界面"在另一端静默失效。
        """
        js = open(os.path.join(ROOT, 'web/panel/panel.js'), encoding='utf-8').read()
        for bad in ('/api/bot', '/api/accounts', 'instances/', 'wordlib', 'marry',
                    'pseudo_persona', 'jm_downloader', 'video_parser'):
            self.assertNotIn(bad, js, f'panel.js 里不该出现端专属内容 {bad}')
        self.assertIn('P.endpoints.', js,
                      '外壳必须通过注入的 endpoints 取接口地址，而不是自己拼')

    def test_schema_engine_has_no_project_paths(self):
        """引擎代码里不许出现某一端的真实路径（注释里提"栖星 AsterCore/Linux 版"是说明文字，不算）"""
        code = []
        for line in open(os.path.join(ROOT, 'web/config_schema.py'), encoding='utf-8').read().split('\n'):
            code.append('' if line.lstrip().startswith('#') else line)
        text = '\n'.join(code)
        for bad in ('/root/', 'mybot2', 'instances/', 'src/astercore', 'web/config_schema'):
            self.assertNotIn(bad, text, f'config_schema.py 的代码里不该出现项目路径 {bad}')


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
"""校验：插件 __config_schema__ 里声明的 default 与实例配置文件里的**当前值**是否一致。

为什么需要：面板的「默认值」来自插件声明，而配置的实际值在 data/*.json。
两者不一致时（新建实例最容易踩：插件是从别的实例复制来的，default 里写着
另一个机器人的名字），用户"什么都没改就点保存"会把配置改成别的实例的值。

用法：python3 tools/check_schema_defaults.py instances/<QQ> [instances/<QQ2> ...]
退出码：0 = 全部一致；1 = 有不一致（会列出前 15 处）
"""
import ast
import json
import os
import sys

PLUGIN_CFG = {
    'wordlib.py': 'wordlib_config.json',
    'marry.py': 'marry_config.json',
    'pseudo_persona.py': 'persona_config.json',
    'jm_downloader.py': 'jm_downloader_config.json',
    'video_parser.py': 'video_parser_config.json',
}


def get_path(d, path):
    cur = d
    for part in str(path).split('.'):
        if not isinstance(cur, dict) or part not in cur:
            return (False, None)
        cur = cur[part]
    return (True, cur)


def load_schema(pyfile):
    """只做 ast.literal_eval，绝不 import 插件（导入期有副作用）"""
    src = open(pyfile, encoding='utf-8').read()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, 'id', '') == '__config_schema__' for t in node.targets):
            return ast.literal_eval(node.value)
    return None


def main(inst):
    inst = os.path.abspath(inst)
    bad = checked = 0
    for py, cfgname in PLUGIN_CFG.items():
        pyfile = os.path.join(inst, 'plugins', py)
        cfgfile = os.path.join(inst, 'data', cfgname)
        if not (os.path.exists(pyfile) and os.path.exists(cfgfile)):
            continue
        schema = load_schema(pyfile)
        if not schema:
            continue
        cfg = json.load(open(cfgfile, encoding='utf-8'))
        for fname, spec in schema.items():
            if not isinstance(spec, dict) or 'default' not in spec:
                continue
            path = spec.get('path') or fname
            present, cur = get_path(cfg, path)
            if not present:
                continue
            dflt = spec['default']
            checked += 1
            if cur == dflt or str(cur) == str(dflt):
                continue
            bad += 1
            if bad <= 15:
                print(f"  ✗ {py}:{fname} (path={path})\n"
                      f"      配置值  = {cur!r}\n      声明默认= {dflt!r}")
    print(f"{inst}: 比对 {checked} 个字段，不一致 {bad} 个")
    return 1 if bad else 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    rc = 0
    for a in sys.argv[1:]:
        rc |= main(a)
    sys.exit(rc)

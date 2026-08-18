"""
通用指令注册表 —— 插件指令集中定义与分发

把散落在 handle() 里的 if/elif 指令判断，改为集中注册的指令表：
每个指令包含 名称 / 触发词 / 描述 / 处理函数 / 权限，一眼可读：
  指令是什么、怎么触发、做什么、谁能用。

用法：
    from utils.command_registry import CommandRegistry

    reg = CommandRegistry("伪人插件")

    def _cmd_switch_glm(event, raw, kw):
        ...  # 处理逻辑
        return True

    reg.register(
        name="切换GLM模型",
        keywords=["切换glm", "用glm"],
        desc="把 AI 模型切换为 GLM",
        handler=_cmd_switch_glm,
        master_only=True,
        kind="exact",   # exact=全等 / suffix=后缀匹配 / prefix=前缀匹配
    )

    # handle() 中统一分发：
    if reg.dispatch(event, raw, is_master(event)):
        return True

    # 生成指令说明表（命令表/帮助用）：
    reg.commands_table()
"""

import threading


class Command:
    """一条指令定义"""

    def __init__(self, name, keywords, desc, handler, master_only=False, kind="exact"):
        self.name = name              # 指令中文名（说明用）
        self.keywords = list(keywords) if isinstance(keywords, (list, tuple)) else [keywords]
        self.desc = desc              # 功能描述
        self.handler = handler        # 处理函数 handler(event, raw, matched_kw) -> bool
        self.master_only = master_only  # 是否仅主人可用
        self.kind = kind              # exact / suffix / prefix

    def match(self, raw):
        for kw in self.keywords:
            if not kw:
                continue
            if self.kind == "exact" and raw == kw:
                return kw
            if self.kind == "suffix" and raw.endswith(kw):
                return kw
            if self.kind == "prefix" and raw.startswith(kw):
                return kw
        return None


class CommandRegistry:
    """指令注册表：集中注册 + 统一匹配分发"""

    def __init__(self, plugin_name=""):
        self.plugin_name = plugin_name
        self._commands = []
        self._lock = threading.Lock()

    def register(self, name, keywords, desc, handler, master_only=False, kind="exact"):
        """注册一条指令"""
        cmd = Command(name, keywords, desc, handler, master_only=master_only, kind=kind)
        with self._lock:
            self._commands.append(cmd)
        return cmd

    def match(self, raw):
        """匹配指令，返回 (command, matched_keyword)，未命中返回 (None, None)"""
        if not raw:
            return None, None
        with self._lock:
            for c in self._commands:
                kw = c.match(raw)
                if kw is not None:
                    return c, kw
        return None, None

    def dispatch(self, event, raw, is_master, master_cmds_only=False):
        """匹配并分发：命中且权限满足则调用 handler，返回 True 表示已处理
        master_cmds_only=True 时仅匹配主人指令（用于早期开关类分发）"""
        c, kw = self.match(raw)
        if c is None:
            return False
        if c.master_only and not is_master:
            return False
        if master_cmds_only and not c.master_only:
            return False
        try:
            return bool(c.handler(event, raw, kw))
        except Exception:
            import traceback
            traceback.print_exc()
            return True  # 已匹配即视为处理，避免继续向下传递

    def commands_table(self, title=None):
        """生成指令说明表文本（用于命令表/帮助）"""
        lines = []
        if title:
            lines.append(f"【{title}】")
        elif self.plugin_name:
            lines.append(f"【{self.plugin_name}指令】")
        for c in self._commands:
            perm = "仅主人" if c.master_only else "所有人"
            lines.append(f"  {'/'.join(c.keywords)}  — {c.name}：{c.desc}（{perm}）")
        return "\n".join(lines)

    def all(self):
        """返回全部指令定义（供检查/调试）"""
        return list(self._commands)

    def labels(self):
        """返回 {触发词: 指令中文名} 映射，供 Web 面板/配置展示可读指令名"""
        labels = {}
        with self._lock:
            for c in self._commands:
                for kw in c.keywords:
                    labels[kw] = c.name
        return labels

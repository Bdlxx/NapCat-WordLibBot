#!/usr/bin/env python3
"""不许把凭据写进仓库 —— 本仓是**公开**的，写进去等于公开。

背景（2026-09-28 真实事故）：`main.py` 把羽笙的 WS access_token 写成 `_get_cfg`
的默认值，从 Initial commit 起就躺在公开仓库里 —— 远端/缓存/他人克隆都留着，
**进了 git 历史就删不掉，只能轮换作废**。所以要在"还没提交"这一层拦住。

检查范围 = `git ls-files --cached --others --exclude-standard`
（已跟踪 + 未被 .gitignore 忽略的未跟踪文件）——这些正是"下一次 git add 会带上去"的文件。
用**形状**匹配；真实凭据不写进本文件（写了就是又泄露一次）。

跑法：cd /root/mybot2 && python3 -m unittest tests.test_no_secrets -v
"""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SELF = Path(__file__).resolve()

# 形状（不是具体值）
PATTERNS = [
    # access_token=<字面量> —— 必须从实例 config.json 读（config.json 已 gitignore）
    (re.compile(r"access_token=[A-Za-z0-9_~.-]{8,}"), "URL 里硬编码 access_token"),
    # Authorization: Bearer <字面量>
    (re.compile(r"Bearer\s+[A-Za-z0-9_~.-]{16,}"), "硬编码 Bearer 令牌"),
    # GitHub 凭据
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{16,}"), "GitHub token"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "GitHub PAT"),
    # 私钥 PEM
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "私钥"),
]

SKIP_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".zip", ".pyc",
               ".so", ".pyd", ".dll", ".pdf", ".woff", ".woff2", ".mp4", ".png"}
# 这些文件本身就带示例/占位说明，允许出现形状词（仍不允许真值）
ALLOW_HINT = ("占位", "<token>", "****", "xxxx", "EXAMPLE", "masked")


def _files():
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, capture_output=True).stdout.decode("utf-8", "replace")
    for rel in filter(None, out.split("\0")):
        p = ROOT / rel
        try:
            if p.resolve() == SELF or p.suffix.lower() in SKIP_SUFFIX or not p.is_file():
                continue
        except OSError:
            continue
        yield rel, p


class NoSecretsTest(unittest.TestCase):
    def test_no_credentials_in_committable_files(self):
        bad = []
        for rel, p in _files():
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for rx, why in PATTERNS:
                m = rx.search(text)
                if not m:
                    continue
                if any(h in m.group(0) for h in ALLOW_HINT):
                    continue
                line = text[:m.start()].count("\n") + 1
                bad.append(f"{rel}:{line} {why}")
        self.assertEqual(bad, [], "发现疑似凭据（改成从 config.json 读，别写进代码）：\n  - "
                         + "\n  - ".join(bad))


if __name__ == "__main__":
    unittest.main()

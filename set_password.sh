#!/bin/bash
# 设置 Web 面板登录密码（MD5 存储）
# 用法: bash set_password.sh <bot名称> <密码>
# 示例: bash set_password.sh 依星 123456

if [ $# -lt 2 ]; then
    echo "用法: bash set_password.sh <bot名称> <密码>"
    echo "示例: bash set_password.sh 依星 123456"
    echo "      bash set_password.sh 羽笙 abcdef"
    exit 1
fi

NAME="$1"
PASS="$2"
CONFIG="/etc/mybot-panel/config.json"

MD5=$(echo -n "$PASS" | md5sum | cut -d' ' -f1)

python3 -c "
import json
with open('$CONFIG') as f:
    c = json.load(f)
c['passwords']['$MD5'] = '$NAME'
with open('$CONFIG', 'w') as f:
    json.dump(c, f, indent=2, ensure_ascii=False)
print('✅ 密码已设置')
print('  Bot: $NAME')
print('  MD5: $MD5')
"

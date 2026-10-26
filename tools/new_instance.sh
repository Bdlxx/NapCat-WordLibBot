#!/usr/bin/env bash
# =============================================================================
# new_instance.sh —— 用脚本新建一个 bot 实例（Linux 端 /root/mybot2）
#
# 做的事（全部可重复执行，已存在的东西会跳过而不是覆盖）：
#   1. instances/<QQ>/        实例目录：main.py + utils + plugins + venv + data（从源实例复制）
#                             · 插件与配置里的实例名（如「依星」）按本实例名改写，保证
#                               __config_schema__ 的 default 与本实例配置一致
#                             · 只复制**配置类** json，签到/婚姻/昵称等运行时数据不复制（从零开始）
#   2. instances/registry/<QQ>.sh   注册文件（面板据此发现实例）
#   3. /etc/systemd/system/mybot-bot-<QQ>.service  单元 + enable --now（父进程 PID 1，与会话无关）
#   4. /root/napcat<N>/       独立 NapCat 目录 + 新容器（bridge，端口映射到 127.0.0.1）
#   5. nginx 站点（NapCat WebUI 域名 + 面板域名）  + nginx -t + reload
#   6. systemctl restart mybot-api（面板启动时读注册文件）
#
# 用法示例：
#   tools/new_instance.sh --qq 123456789 --name 凛紫 \
#       --napcat-domain linzi.xn--kivt1l.online \
#       --panel-domain  linzi-bot.xn--kivt1l.online
#
#   # 单个域名同时挂 NapCat（根）与面板（/panel/）：
#   tools/new_instance.sh --qq ... --name ... --napcat-domain linzi.xn--kivt1l.online --panel-path /panel
#
#   # 只准备实例（不碰宿主机）：
#   tools/new_instance.sh --qq ... --name ... --skip-napcat --skip-nginx --skip-systemd
#
# 说明：DSH 沙箱里 /etc、systemctl 不可直接访问，脚本会自动改用 privileged 容器
#       chroot 到宿主机执行主机侧动作（等价 root，但不是新起服务）。
# =============================================================================
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTANCES_ROOT="$REPO_ROOT/instances"
REGISTRY_DIR="$INSTANCES_ROOT/registry"
HELPER_IMAGE="alpine:latest"
NAPCAT_IMAGE="mlikiowa/napcat-docker:latest"

QQ=""
NAME=""
SOURCE_QQ=""
MASTER_QQ=""
NAP_CONTAINER=""
NAP_DIR=""
HTTP_PORT=""
WS_PORT=""
WEBUI_PORT=""
WEBUI_TOKEN=""
NAP_DOMAIN=""
PANEL_DOMAIN=""
PANEL_PATH=""
SCREEN_NAME=""
DRY_RUN=0
FORCE=0
SKIP_NAP=0
SKIP_NGINX=0
SKIP_SYSTEMD=0
SKIP_PLUGINS=0
SKIP_PANEL=0
PANEL_PORT=8080

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'; BOLD='\033[1m'
ok()   { echo -e "${GREEN}✓${NC} $1"; }
info() { echo -e "${CYAN}ℹ${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
err()  { echo -e "${RED}✗${NC} $1"; }
step() { echo -e "\n${BOLD}${BLUE}══ $1 ══${NC}"; }
die()  { err "$1"; exit 1; }
run()  { if [ "$DRY_RUN" = 1 ]; then echo "    [dry-run] $*"; else "$@"; fi; }

usage() {
    sed -n '2,32p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    echo "参数："
    echo "  --qq <QQ>                必填，实例标识（目录名/容器名/面板编号都按它派生）"
    echo "  --name <名字>            必填，机器人昵称（如 凛紫）"
    echo "  --source <QQ>            从哪个现有实例复制代码与配置（默认 740979632 依星）"
    echo "  --master <QQ[,QQ]>       主人 QQ（默认沿用源实例）"
    echo "  --napcat-domain <域名>   NapCat WebUI 域名（写进 INST_NAPCAT_WEBUI 并生成 nginx 站点）"
    echo "  --panel-domain <域名>    面板域名（与 NapCat 同域名时改用 --panel-path）"
    echo "  --panel-path <路径>      面板挂在 NapCat 域名的子路径下（如 /panel）"
    echo "  --http-port/--ws-port/--webui-port   覆盖 NapCat 端口（默认自动挑空闲）"
    echo "  --webui-token <字符串>   NapCat WebUI 登录密码（默认沿用源实例的 token）"
    echo "  --napcat-dir <目录>      NapCat 数据目录（默认 /root/napcat<N>）"
    echo "  --container <名字>       容器名（默认 napcat<N>）"
    echo "  --skip-napcat|--skip-nginx|--skip-systemd|--skip-plugins|--skip-panel"
    echo "  --force                  实例目录已存在时也继续（覆盖配置）"
    echo "  --dry-run                只打印将要做什么"
}

while [ $# -gt 0 ]; do
    case "$1" in
        --qq) QQ="${2:-}"; shift 2 ;;
        --name) NAME="${2:-}"; shift 2 ;;
        --source) SOURCE_QQ="${2:-}"; shift 2 ;;
        --master) MASTER_QQ="${2:-}"; shift 2 ;;
        --napcat-domain) NAP_DOMAIN="${2:-}"; shift 2 ;;
        --panel-domain) PANEL_DOMAIN="${2:-}"; shift 2 ;;
        --panel-path) PANEL_PATH="${2:-}"; shift 2 ;;
        --http-port) HTTP_PORT="${2:-}"; shift 2 ;;
        --ws-port) WS_PORT="${2:-}"; shift 2 ;;
        --webui-port) WEBUI_PORT="${2:-}"; shift 2 ;;
        --webui-token) WEBUI_TOKEN="${2:-}"; shift 2 ;;
        --napcat-dir) NAP_DIR="${2:-}"; shift 2 ;;
        --container) NAP_CONTAINER="${2:-}"; shift 2 ;;
        --screen) SCREEN_NAME="${2:-}"; shift 2 ;;
        --skip-napcat) SKIP_NAP=1; shift ;;
        --skip-nginx) SKIP_NGINX=1; shift ;;
        --skip-systemd) SKIP_SYSTEMD=1; shift ;;
        --skip-plugins) SKIP_PLUGINS=1; shift ;;
        --skip-panel) SKIP_PANEL=1; shift ;;
        --force) FORCE=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "未知参数: $1（--help 看用法）" ;;
    esac
done

[ -n "$QQ" ]  || { usage; die "--qq 必填"; }
[ -n "$NAME" ] || { usage; die "--name 必填"; }
case "$QQ" in ''|*[!0-9]*) die "--qq 必须是纯数字" ;; esac
SOURCE_QQ="${SOURCE_QQ:-740979632}"

# ───────────────────────── 主机侧执行（沙箱 → 宿主机） ─────────────────────────
HOST_MODE=""
detect_host_mode() {
    if [ "$(uname -n 2>/dev/null)" = "bwrap" ] || ! systemctl is-system-running >/dev/null 2>&1; then
        HOST_MODE="docker"
    else
        HOST_MODE="local"
    fi
    info "主机侧动作执行方式：$HOST_MODE"
}

# 在宿主机命名空间里跑命令（systemctl / nginx 等）
h_run() {
    if [ "$HOST_MODE" = "local" ]; then
        "$@"
    else
        docker run --rm --privileged --pid=host -v /:/host "$HELPER_IMAGE" \
            chroot /host "$@"
    fi
}

# 把本地文件写到宿主机绝对路径（/etc 等沙箱只读的地方）
h_write() {   # $1=宿主机绝对路径  $2=本地源文件  $3=权限(默认644)
    local dst="$1" src="$2" mode="${3:-644}"
    if [ "$DRY_RUN" = 1 ]; then echo "    [dry-run] 写宿主机 $dst (mode $mode)"; return 0; fi
    if [ "$HOST_MODE" = "local" ]; then
        mkdir -p "$(dirname "$dst")" && install -m "$mode" "$src" "$dst"
    else
        docker run --rm -i -v /:/host "$HELPER_IMAGE" sh -c \
            "mkdir -p \"\$(dirname /host$dst)\" && cat > \"/host$dst\" && chmod $mode \"/host$dst\"" < "$src" \
            || die "写宿主机文件失败: $dst"
    fi
}

h_mkdir() {
    local d="$1"
    if [ "$DRY_RUN" = 1 ]; then echo "    [dry-run] mkdir -p $d"; return 0; fi
    if [ "$HOST_MODE" = "local" ]; then mkdir -p "$d"
    else docker run --rm -v /:/host "$HELPER_IMAGE" mkdir -p "/host$d" || die "建目录失败: $d"; fi
}

port_free() { ! ss -ltn "sport = :$1" 2>/dev/null | grep -q LISTEN; }

pick_port() {   # $1=起始端口
    local p="$1" guard=0
    while ! port_free "$p"; do p=$((p+1)); guard=$((guard+1)); [ "$guard" -gt 50 ] && die "找不到空闲端口（从 $1 起）"; done
    echo "$p"
}

# ───────────────────────── 0. 预检 ─────────────────────────
step "0. 预检"
SRC_DIR="$INSTANCES_ROOT/$SOURCE_QQ"
[ -f "$SRC_DIR/main.py" ] || die "源实例不存在: $SRC_DIR"
[ -d "$SRC_DIR/plugins" ] || die "源实例缺 plugins/: $SRC_DIR"
SRC_NAME="$(python3 -c "import json;print(json.load(open('$SRC_DIR/config.json'))['BOT_NAME'])" 2>/dev/null)"
[ -n "$SRC_NAME" ] || die "读不到源实例 BOT_NAME"
info "源实例：$SOURCE_QQ（$SRC_NAME）"

INST_DIR="$INSTANCES_ROOT/$QQ"
if [ -d "$INST_DIR" ] && [ "$FORCE" != 1 ]; then
    die "实例目录已存在：$INST_DIR（要重做请加 --force）"
fi
[ -f "$SRC_DIR/venv/bin/python" ] || warn "源实例没有 venv/，新实例的 jm 下载会缺依赖"

# 主人 QQ
if [ -z "$MASTER_QQ" ]; then
    MASTER_QQ="$(python3 -c "
import json;d=json.load(open('$SRC_DIR/config.json'));m=d.get('MASTER_QQ')
print(','.join(str(x) for x in m) if isinstance(m,list) else str(m))" 2>/dev/null)"
fi
[ -n "$MASTER_QQ" ] || die "主人 QQ 为空（用 --master 指定）"
info "主人 QQ：$MASTER_QQ"

# NapCat 编号 / 端口
NAP_INDEX=3
while [ -d "/root/napcat$NAP_INDEX" ] || docker ps -a --format '{{.Names}}' | grep -qx "napcat$NAP_INDEX"; do
    NAP_INDEX=$((NAP_INDEX+1)); [ "$NAP_INDEX" -gt 20 ] && break
done
NAP_DIR="${NAP_DIR:-/root/napcat$NAP_INDEX}"
NAP_CONTAINER="${NAP_CONTAINER:-napcat$NAP_INDEX}"
HTTP_PORT="${HTTP_PORT:-$(pick_port 3004)}"
WS_PORT="${WS_PORT:-$(pick_port $((HTTP_PORT+1)))}"
if [ "$WS_PORT" = "$HTTP_PORT" ]; then WS_PORT="$(pick_port $((HTTP_PORT+2)))"; fi
WEBUI_PORT="${WEBUI_PORT:-$(pick_port 6101)}"
ACCESS_TOKEN="$(head -c 16 /dev/urandom | base64 | tr -d '/+=' | head -c 16)"
WS_TOKEN="$(head -c 16 /dev/urandom | base64 | tr -d '/+=' | head -c 16)"
info "NapCat：容器 $NAP_CONTAINER  目录 $NAP_DIR  http=$HTTP_PORT ws=$WS_PORT webui=$WEBUI_PORT"
SCREEN_NAME="${SCREEN_NAME:-bot_$QQ}"

if [ "$SKIP_NAP" != 1 ] && docker ps -a --format '{{.Names}}' | grep -qx "$NAP_CONTAINER"; then
    die "容器名已存在：$NAP_CONTAINER"
fi

detect_host_mode
[ "$SKIP_SYSTEMD" = 1 ] || command -v docker >/dev/null || [ "$HOST_MODE" = local ] || die "没有 docker，无法在沙箱里操作宿主机"

# ───────────────────────── 1. 实例目录 ─────────────────────────
step "1. 实例目录 $INST_DIR"
if [ -d "$INST_DIR" ] && [ "$FORCE" = 1 ]; then
    warn "已存在，保留 data/ 与 venv/，只刷新代码与配置"
fi
run mkdir -p "$INST_DIR"
for item in main.py utils plugins; do
    if [ "$item" = "plugins" ] && [ "$SKIP_PLUGINS" = 1 ] && [ -d "$INST_DIR/plugins" ]; then
        info "保留现有 plugins/"
    else
        run rsync -a --delete --exclude '__pycache__' --exclude '*.bak*' --exclude 'data/' \
            "$SRC_DIR/$item" "$INST_DIR/"
    fi
done
# 源实例的 venv 直接复制（自包含；venv 里的绝对路径改成本实例路径）
if [ ! -x "$INST_DIR/venv/bin/python" ]; then
    info "复制 venv（116MB 左右，稍等）…"
    run cp -a "$SRC_DIR/venv" "$INST_DIR/venv"
fi
if [ "$DRY_RUN" = 0 ] && [ -d "$INST_DIR/venv" ]; then
    grep -rl "$SRC_DIR/venv" "$INST_DIR/venv/bin" 2>/dev/null | while read -r f; do
        sed -i "s#$SRC_DIR/venv#$INST_DIR/venv#g" "$f"
    done
    sed -i "s#$SRC_DIR/venv#$INST_DIR/venv#g" "$INST_DIR/venv/pyvenv.cfg" 2>/dev/null
fi
run mkdir -p "$INST_DIR/data" "$INST_DIR/plugins/data"
ok "代码已就位"

# ───────────────────────── 2. 配置（config.json + data 配置） ─────────────────────────
step "2. 配置"
if [ "$DRY_RUN" = 1 ]; then
    echo "    [dry-run] 生成 config.json / 复制配置类 json / 改写实例名 $SRC_NAME→$NAME"
else
CACHE_HOST=""
[ "$SKIP_NAP" = 1 ] || CACHE_HOST="$NAP_DIR/cache/images"
python3 - "$SRC_DIR" "$INST_DIR" "$QQ" "$NAME" "$MASTER_QQ" "$HTTP_PORT" "$ACCESS_TOKEN" "$WS_TOKEN" "$CACHE_HOST" <<'PY'
import json, os, shutil, sys

src, dst, qq, name, masters, http_port, token, ws_token, cache_host = sys.argv[1:10]
src_cfg = json.load(open(os.path.join(src, 'config.json'), encoding='utf-8'))
master_list = [int(x) if x.strip().isdigit() else x.strip() for x in masters.split(',') if x.strip()]

cfg = {
    "_note": f"{name}(QQ:{qq}) 机器人配置",
    "BOT_NAME": name,
    "MASTER_QQ": master_list,
    "BOT_QQ": int(qq),
    "NAPCAT_HTTP": f"http://127.0.0.1:{http_port}",
    "ACCESS_TOKEN": token,
    "WS_URL": f"ws://127.0.0.1:{int(http_port)+1}/?access_token={ws_token}",
}
for k in ("52api_key", "52api_secret"):          # 沿用源实例（死配置，但保持形状）
    if k in src_cfg:
        cfg[k] = src_cfg[k]
# NapCat 共享目录的单一事实来源（三个插件都读它）：不写死 QQ 分支，
# 新实例（/root/napcat3 …）解析核心写盘的目录才会和发送给容器的路径对上
if cache_host:
    cfg["NAPCAT_CACHE_HOST"] = cache_host
with open(os.path.join(dst, 'config.json'), 'w', encoding='utf-8') as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)
    f.write('\n')

# 只搬"配置类"，不搬运行时数据（签到/婚姻/昵称/缓存）
# ⚠️ plugin_toggle.json **不能搬**：它的键是**群号**，属于源账号自己所在的群。
#    搬过去会让新实例的面板列出另一个账号的群（2026-10-25 线上就踩了：
#    凛紫的群组开关页显示依星的 22 个群，且在面板点保存会把这 22 个群写进本实例的
#    开关文件）。新实例从空表开始，登录后群列表由 NapCat 提供、默认全关。
CONFIGS = ['wordlib_config.json', 'marry_config.json', 'persona_config.json',
           'jm_downloader_config.json', 'video_parser_config.json']
src_name = src_cfg.get('BOT_NAME', '')
for fn in CONFIGS:
    s = os.path.join(src, 'data', fn)
    if not os.path.exists(s):
        continue
    raw = open(s, encoding='utf-8').read()
    if src_name and name != src_name:
        raw = raw.replace(src_name, name)
    open(os.path.join(dst, 'data', fn), 'w', encoding='utf-8').write(raw)
print("    config.json + %d 个配置 json 已生成" % len([f for f in CONFIGS if os.path.exists(os.path.join(src,'data',f))]))

# 插件里的实例名：**只改 __config_schema__ 里的字符串**（触发词 default / 标签 / 说明），
# 保证面板显示的默认值与本实例的配置文件一致；代码里的 `{依星}` 这类通用占位符
# 与注释一律不动（那是跨实例共用的，改了会让占位符失效）。
if src_name and name != src_name:
    import ast
    def _schema_span(text):
        try:
            tree = ast.parse(text)
        except Exception:
            return None
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == '__config_schema__' for t in node.targets):
                lines = text.splitlines(keepends=True)
                st = sum(len(l) for l in lines[:node.lineno - 1])
                en = sum(len(l) for l in lines[:node.end_lineno])
                return st, en
        return None
    total = 0
    for root, dirs, files in os.walk(os.path.join(dst, 'plugins')):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for fn in files:
            if not fn.endswith('.py'):
                continue
            p = os.path.join(root, fn)
            try:
                raw = open(p, encoding='utf-8').read()
            except Exception:
                continue
            span = _schema_span(raw)
            if not span:
                continue
            st, en = span
            seg = raw[st:en]
            if src_name not in seg:
                continue
            total += seg.count(src_name)
            open(p, 'w', encoding='utf-8').write(raw[:st] + seg.replace(src_name, name) + raw[en:])
    print(f"    插件 __config_schema__ 内实例名替换：{src_name}→{name} 共 {total} 处")
PY
fi
ok "配置完成"

# ───────────────────────── 3. 注册文件（面板据此发现） ─────────────────────────
step "3. 实例注册文件"
WEBUI_URL=""
[ -n "$NAP_DOMAIN" ] && WEBUI_URL="https://$NAP_DOMAIN/"
REG_FILE="$REGISTRY_DIR/$QQ.sh"
if [ "$DRY_RUN" = 1 ]; then
    echo "    [dry-run] 写注册文件 $REG_FILE"
else
mkdir -p "$REGISTRY_DIR"
{
    echo "INST_QQ=\"$QQ\""
    echo "INST_CONTAINER=\"$NAP_CONTAINER\""
    echo "INST_PROJECT_DIR=\"$INST_DIR\""
    echo "INST_NAP_DIR=\"$NAP_DIR\""
    echo "INST_SCREEN=\"$SCREEN_NAME\""
    echo "INST_HTTP=\"http://127.0.0.1:$HTTP_PORT\""
    echo "INST_WS=\"ws://127.0.0.1:$WS_PORT\""
    echo "INST_TOKEN=\"$ACCESS_TOKEN\""
    echo "INST_BOT_NAME=\"$NAME\""
    echo "INST_NAPCAT_WEBUI=\"$WEBUI_URL\""
} > "$REG_FILE"
ok "已写 $REG_FILE"
fi

# ───────────────────────── 4. systemd 单元 ─────────────────────────
if [ "$SKIP_SYSTEMD" = 1 ]; then
    step "4. systemd（跳过）"
else
    step "4. systemd 单元"
    UNIT_NAME="mybot-bot-$QQ.service"
    TMP_UNIT="$(mktemp)"
    cat > "$TMP_UNIT" <<EOF
# MyBot $NAME（由 tools/new_instance.sh 生成；systemd 托管，崩溃自动重启）
[Unit]
Description=MyBot $NAME (QQ $QQ)
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INST_DIR
ExecStart=/usr/bin/python3 main.py --bot-name $NAME --bot-qq $QQ
Restart=always
RestartSec=5
KillSignal=SIGINT
TimeoutStopSec=20

[Install]
WantedBy=multi-user.target
EOF
    h_write "/etc/systemd/system/$UNIT_NAME" "$TMP_UNIT" 644
    rm -f "$TMP_UNIT"
    run h_run systemctl daemon-reload
    run h_run systemctl enable --now "$UNIT_NAME" || warn "systemctl enable --now 失败：$UNIT_NAME"
    ok "单元 $UNIT_NAME 已启用"
fi

# ────────────────��──────── 5. NapCat 容器 ─────────────────────────
if [ "$SKIP_NAP" = 1 ]; then
    step "5. NapCat（跳过）"
else
    step "5. NapCat 目录与容器"
    h_mkdir "$NAP_DIR/config"
    h_mkdir "$NAP_DIR/cache/images"
    SRC_NAP="/root/napcat2"
    [ -d "$SRC_NAP/config" ] || SRC_NAP="/root/napcat"
    h_cp() {  # $1=宿主机源  $2=宿主机目标
        if [ "$DRY_RUN" = 1 ]; then echo "    [dry-run] cp $1 -> $2"; return 0; fi
        if [ "$HOST_MODE" = "local" ]; then cp -a "$1" "$2"
        else docker run --rm -v /:/host "$HELPER_IMAGE" sh -c "cp -a /host$1 /host$2" || die "复制失败 $1"; fi
    }
    TMP_CFG="$(mktemp -d)"
    # napcat.json / napcat_<QQ>.json / napcat_protocol_<QQ>.json
    cp "$SRC_NAP/config/napcat.json" "$TMP_CFG/napcat.json"
    src_acc="$(ls "$SRC_NAP/config"/napcat_[0-9]*.json 2>/dev/null | head -1)"
    [ -n "$src_acc" ] && cp "$src_acc" "$TMP_CFG/napcat_$QQ.json"
    src_proto="$(ls "$SRC_NAP/config"/napcat_protocol_*.json 2>/dev/null | head -1)"
    [ -n "$src_proto" ] && cp "$src_proto" "$TMP_CFG/napcat_protocol_$QQ.json"
    echo '{}' > "$TMP_CFG/passkey.json"
    # webui.json：沿用源实例的 token（用户已知），只改账号
    python3 - "$SRC_NAP/config/webui.json" "$TMP_CFG/webui.json" "$QQ" "$WEBUI_PORT" "$WEBUI_TOKEN" <<'PY'
import json, sys
src, dst, qq, port, forced_token = sys.argv[1:6]
try:
    d = json.load(open(src, encoding='utf-8'))
except Exception:
    d = {}
d['host'] = '0.0.0.0'
d['port'] = 6099                       # 容器内部端口固定，宿主侧用映射
d.setdefault('token', '')
if forced_token:
    d['token'] = forced_token        # 指定了就用指定的（如"密码=QQ号"）
d['autoLoginAccount'] = qq
json.dump(d, open(dst, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
PY
    # onebot11_<QQ>.json：HTTP 3000 / WS 3001（容器内），token 与 bot config.json 一致
    python3 - "$TMP_CFG/onebot11_$QQ.json" "$ACCESS_TOKEN" "$WS_TOKEN" <<'PY'
import json, sys
dst, http_token, ws_token = sys.argv[1:4]
cfg = {
  "network": {
    "httpServers": [{
      "enable": True, "name": "插件1", "host": "0.0.0.0", "port": 3000,
      "enableCors": True, "enableWebsocket": False, "messagePostFormat": "array",
      "token": http_token, "debug": False
    }],
    "httpSseServers": [], "httpClients": [],
    "websocketServers": [{
      "enable": True, "name": "插件", "host": "0.0.0.0", "port": 3001,
      "reportSelfMessage": True, "enableForcePushEvent": True,
      "messagePostFormat": "array", "token": ws_token, "debug": False,
      "heartInterval": 30000
    }],
    "websocketClients": [], "plugins": []
  },
  "musicSignUrl": "", "enableLocalFile2Url": False, "parseMultMsg": False,
  "imageDownloadProxy": "",
  "timeout": {"baseTimeout": 10000}
}
json.dump(cfg, open(dst, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
PY
    for f in "$TMP_CFG"/*.json; do
        h_write "$NAP_DIR/config/$(basename "$f")" "$f" 644
    done
    rm -rf "$TMP_CFG"

    if [ "$DRY_RUN" = 1 ]; then
        echo "    [dry-run] docker run -d --name $NAP_CONTAINER ... -p 127.0.0.1:$HTTP_PORT:3000 -p 127.0.0.1:$WS_PORT:3001 -p 127.0.0.1:$WEBUI_PORT:6099"
    else
        docker run -d --name "$NAP_CONTAINER" --restart unless-stopped \
            -e TZ=Asia/Shanghai -e ACCOUNT="$QQ" -e WS_ENABLE=true \
            -e NAPCAT_GID=0 -e NAPCAT_UID=0 \
            -p "127.0.0.1:$HTTP_PORT:3000" \
            -p "127.0.0.1:$WS_PORT:3001" \
            -p "127.0.0.1:$WEBUI_PORT:6099" \
            -v "$NAP_DIR/config:/app/napcat/config" \
            -v "$NAP_DIR/cache/images:/app/cache/images" \
            -v "${NAP_CONTAINER}_qqdata:/app/.config/QQ" \
            "$NAPCAT_IMAGE" >/dev/null || die "容器启动失败"
        ok "容器 $NAP_CONTAINER 已启动"
    fi
fi

# ───────────────────────── 6. nginx 站点 ─────────────────────────
if [ "$SKIP_NGINX" = 1 ] || [ -z "$NAP_DOMAIN" ]; then
    step "6. nginx（跳过/未指定域名）"
else
    step "6. nginx 站点"
    TMP_NG=$(mktemp)
    {
        cat <<EOF
# $NAME（QQ $QQ）NapCat WebUI —— 由 tools/new_instance.sh 生成
server {
    listen 80;
    listen [::]:80;
    server_name $NAP_DOMAIN;
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        default_type "text/plain";
    }
    location / { return 301 https://\$host\$request_uri; }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name $NAP_DOMAIN;

    ssl_certificate     /etc/nginx/certs/origin.crt;
    ssl_certificate_key /etc/nginx/certs/origin.key;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:50m;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        proxy_pass http://127.0.0.1:$WEBUI_PORT;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
    }
EOF
        # 单域名模式：面板挂在同一域名的子路径下
        if [ -z "$PANEL_DOMAIN" ] && [ -n "$PANEL_PATH" ]; then
            PP="${PANEL_PATH#/}"; PP="/${PP%/}"
            cat <<EOF

    # ── bot 面板（同一域名的子路径；/api/ 精确分流：面板接口 vs NapCat 接口）──
    # 页面外壳在 web/index.html；该页里的 panel.css / cfg_form.js 都是相对路径，
    # 在 /panel/ 下会请求 /panel/panel.css —— 正好是 web/panel/ 里的真实文件。
    location = $PP { return 301 $PP/; }
    location = $PP/ { alias /root/mybot2/web/index.html; }
    location ^~ $PP/ {
        root /root/mybot2/web;
        try_files \$uri =404;
        expires 5m;
        add_header Cache-Control "public, max-age=300";
    }
    location ~ ^/api/(bot/|bots\$|status\$|check-auth\$|logout\$|portal-login\$) {
        proxy_pass http://127.0.0.1:$PANEL_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
EOF
        fi
        cat <<EOF
}
EOF
        # 独立面板域名（与 bot.xn--kivt1l.online 同构）
        if [ -n "$PANEL_DOMAIN" ]; then
            cat <<EOF

# $NAME（QQ $QQ）面板 —— 静态面板 + /api 反代，与 bot 站同构
server {
    listen 80;
    listen [::]:80;
    server_name $PANEL_DOMAIN;
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        default_type "text/plain";
    }
    location / { return 301 https://\$host\$request_uri; }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name $PANEL_DOMAIN;

    ssl_certificate     /etc/nginx/certs/origin.crt;
    ssl_certificate_key /etc/nginx/certs/origin.key;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:50m;
    ssl_protocols TLSv1.2 TLSv1.3;

    root /root/mybot2/web;
    index index.html;

    location ~* ^/panel/.*\.(js|css)\$ {
        expires 5m;
        add_header Cache-Control "public, max-age=300";
        try_files \$uri =404;
    }
    location / {
        try_files \$uri \$uri/ /index.html;
    }
    location /api/ {
        proxy_pass http://127.0.0.1:$PANEL_PORT/api/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
        fi
    } > "$TMP_NG"

    SITE_NAME="bot-$QQ"
    h_write "/etc/nginx/sites-enabled/$SITE_NAME" "$TMP_NG" 644
    cp "$TMP_NG" "/tmp/nginx-$QQ.conf" 2>/dev/null || true
    rm -f "$TMP_NG"
    if run h_run nginx -t; then
        run h_run systemctl reload nginx || run h_run nginx -s reload
        ok "nginx 已加载 $SITE_NAME"
    else
        err "nginx -t 未通过，站点已写入但未 reload：/etc/nginx/sites-enabled/$SITE_NAME"
    fi
fi

# ───────────────────────── 7. 面板重载 + 收尾自检 ─────────────────────────
step "7. 面板重载与自检"
if [ "$SKIP_PANEL" = 1 ]; then
    info "跳过面板重载（--skip-panel）"
else
    run h_run systemctl restart mybot-api 2>/dev/null || warn "重启 mybot-api 失败（面板可能没发现新实例）"
fi
sleep 3
if [ "$DRY_RUN" = 0 ]; then
    UNIT_NAME="mybot-bot-$QQ.service"
    [ "$SKIP_SYSTEMD" = 1 ] || echo "  systemd: $(h_run systemctl is-active "$UNIT_NAME" 2>/dev/null)"
    docker ps --filter "name=^${NAP_CONTAINER}$" --format '  napcat : {{.Names}} {{.Status}} {{.Ports}}' 2>/dev/null
    echo "  端口   : http=$HTTP_PORT ws=$WS_PORT webui=$WEBUI_PORT"
    if [ -n "$NAP_DOMAIN" ]; then
        echo "  HTTPS  : $(curl -sk -o /dev/null -w '%{http_code}' -H "Host: $NAP_DOMAIN" https://127.0.0.1/ --max-time 5)"
    fi
    echo "  注册   : $(ls "$REG_FILE" 2>/dev/null)"
    echo "  日志   : tail -f $INST_DIR/runtime.log"
fi
step "完成"
echo "  实例：$NAME（QQ $QQ）→ $INST_DIR"
[ -n "$NAP_DOMAIN" ] && echo "  WebUI：https://$NAP_DOMAIN/（首次需扫码登录）"
[ -n "$PANEL_DOMAIN" ] && echo "  面板 ：https://$PANEL_DOMAIN/?bot=$QQ"
[ -z "$PANEL_DOMAIN" ] && [ -n "$PANEL_PATH" ] && echo "  面板 ：https://$NAP_DOMAIN${PANEL_PATH}/?bot=$QQ"
echo "  NapCat：容器 $NAP_CONTAINER，目录 $NAP_DIR，HTTP 127.0.0.1:$HTTP_PORT，WS 127.0.0.1:$WS_PORT"
echo "  管理 ：systemctl {status|restart} mybot-bot-$QQ.service"

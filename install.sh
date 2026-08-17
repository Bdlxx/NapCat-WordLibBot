#!/bin/bash
# ===============================================================
# NapCat WordLib Bot — 一键安装部署 & 运行管理脚本
# 仓库: https://github.com/Bdlxx/NapCat-WordLibBot
# 用法: bash install.sh  或安装后执行  napbot
# ===============================================================

# ───────────────────────── 配置区 ─────────────────────────
SCRIPT_NAME="NapCat-WordLibBot"
SCRIPT_VERSION="1.1.0"
NAPCAT_IMAGE="docker.xuanyuan.me/mlikiowa/napcat-docker:latest"
GIT_REPO="https://github.com/Bdlxx/NapCat-WordLibBot.git"
PLUGIN_REPO="https://github.com/Bdlxx/NapCat-WordLibBot-Plugins.git"

# 用户目录下新建目录存储脚本（napbot 命令的稳定指向）
NAPBOT_HOME="$HOME/napbot"
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATES_DIR="$BASE_DIR/templates"
SCRIPT_PATH="$BASE_DIR/install.sh"
# 实例统一放在脚本目录下的 instances/ 中，注册文件在 instances/registry/
INSTANCES_ROOT="$BASE_DIR/instances"
INSTANCES_DIR="$INSTANCES_ROOT/registry"

mkdir -p "$INSTANCES_DIR"

# 自保存：把当前脚本复制到用户目录 ~/napbot/install.sh
# （curl 管道运行时 $0 为 /dev/fd/*，无法复制，post_setup 会提示手动保存；
#   从副本本身运行时跳过，避免 cp 到同一文件）
if [[ -f "$0" && "$0" != /dev/fd/* && "$(readlink -f "$0")" != "$NAPBOT_HOME/install.sh" ]]; then
    mkdir -p "$NAPBOT_HOME"
    cp "$0" "$NAPBOT_HOME/install.sh" 2>/dev/null && chmod +x "$NAPBOT_HOME/install.sh"
    # 同步使用教程到用户目录（脚本菜单「查看使用教程」可离线打开）
    [ -f "$BASE_DIR/USAGE.md" ] && cp "$BASE_DIR/USAGE.md" "$NAPBOT_HOME/USAGE.md" 2>/dev/null
fi

# ───────────────────────── 颜色 ─────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'; BOLD='\033[1m'

ok()   { echo -e "${GREEN}✓${NC} $1"; }
err()  { echo -e "${RED}✗${NC} $1"; }
info() { echo -e "${CYAN}ℹ${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
title(){ echo -e "\n${BOLD}${BLUE}══ $1 ══${NC}\n"; }
sep()  { echo -e "${BLUE}────────────────────────────────────────${NC}"; }

# ───────────────────────── TUI 函数 ─────────────────────────
tui_menu() {
    local title="$1"; shift; local text="$1"; shift
    whiptail --clear --backtitle "$SCRIPT_NAME v$SCRIPT_VERSION" \
        --title "$title" --menu "$text" 0 0 0 "$@" 3>&1 1>&2 2>&3
}
tui_input() {
    local title="$1" text="$2" init="$3"
    whiptail --clear --backtitle "$SCRIPT_NAME v$SCRIPT_VERSION" \
        --title "$title" --inputbox "$text" 0 0 "$init" 3>&1 1>&2 2>&3
}
tui_password() {
    local title="$1" text="$2"
    whiptail --clear --backtitle "$SCRIPT_NAME v$SCRIPT_VERSION" \
        --title "$title" --passwordbox "$text" 8 40 3>&1 1>&2 2>&3
}
tui_yesno() {
    local title="$1" text="$2"
    whiptail --clear --backtitle "$SCRIPT_NAME v$SCRIPT_VERSION" \
        --title "$title" --yesno "$text" 0 0
}
tui_msg() {
    local title="$1" text="$2"
    whiptail --clear --backtitle "$SCRIPT_NAME v$SCRIPT_VERSION" \
        --title "$title" --msgbox "$text" 0 0
}
tui_infobox() {
    whiptail --clear --backtitle "$SCRIPT_NAME v$SCRIPT_VERSION" \
        --title "$1" --infobox "$2" 0 0
}

# ───────────────────────── 工具函数 ─────────────────────────

gen_token() {
    openssl rand -base64 12 2>/dev/null | tr -dc 'a-zA-Z0-9~!@#$%^&*_+' | head -c 16
    if [[ $? -ne 0 || -z "$(openssl rand -base64 12 2>/dev/null)" ]]; then
        date +%s%N | md5sum | head -c 16
    fi
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        err "此脚本需要 root 权限运行（sudo bash install.sh）"
        exit 1
    fi
}

# 扫描已部署实例
scan_instances() {
    local qqs=()
    # 从 docker 容器扫描
    for c in $(docker ps -a --format '{{.Names}}' 2>/dev/null | grep '^napcat_' | sed 's/^napcat_//'); do
        qqs+=("$c")
    done
    # 从实例记录文件补充
    for f in "$INSTANCES_DIR"/*.sh; do
        [ -f "$f" ] || continue
        local qq=$(basename "$f" .sh)
        # 去重
        local found=false
        for q in "${qqs[@]}"; do [[ "$q" == "$qq" ]] && found=true && break; done
        $found || qqs+=("$qq")
    done
    # 从项目目录补充（新布局 instances/<QQ>；兼容旧布局 /root/mybot_<QQ>）
    for d in "$INSTANCES_ROOT"/*/ /root/mybot_*; do
        [ -d "$d" ] || continue
        local qq
        if [[ "$d" == "$INSTANCES_ROOT"/* ]]; then
            qq="$(basename "$d")"
        else
            qq="${d#/root/mybot_}"
        fi
        [[ "$qq" =~ ^[0-9]+$ ]] || continue
        local found=false
        for q in "${qqs[@]}"; do [[ "$q" == "$qq" ]] && found=true && break; done
        $found || qqs+=("$qq")
    done
    echo "${qqs[@]}"
}

# 加载实例信息
load_instance() {
    local qq=$1 f="$INSTANCES_DIR/${qq}.sh"
    if [ -f "$f" ]; then
        source "$f"
        return 0
    fi
    # 默认值
    INST_QQ="$qq"
    INST_CONTAINER="napcat_${qq}"
    INST_PROJECT_DIR="$INSTANCES_ROOT/${qq}"
    INST_NAP_DIR="/root/napcat_${qq}"
    INST_SCREEN="bot_${qq}"
    INST_HTTP="http://127.0.0.1:3000"
    INST_WS="ws://127.0.0.1:3001/?access_token="
    INST_TOKEN=""
    INST_BOT_NAME="Bot_${qq}"
    return 1
}

# 保存实例信息
save_instance() {
    local qq=$1 f="$INSTANCES_DIR/${qq}.sh"
    cat > "$f" <<-EOF
INST_QQ="$INST_QQ"
INST_CONTAINER="$INST_CONTAINER"
INST_PROJECT_DIR="$INST_PROJECT_DIR"
INST_NAP_DIR="$INST_NAP_DIR"
INST_SCREEN="$INST_SCREEN"
INST_HTTP="$INST_HTTP"
INST_WS="$INST_WS"
INST_TOKEN="$INST_TOKEN"
INST_BOT_NAME="$INST_BOT_NAME"
EOF
}

# ───────────────────────── 1. 部署新实例 ─────────────────────────

deploy_new_instance() {
    title "📦 部署新实例"

    local qq
    qq=$(tui_input "实例标识" "请输入机器人 QQ 号作为实例标识\n（将用于创建独立目录和容器名）" "") || return
    while [[ -z "$qq" || ! "$qq" =~ ^[0-9]+$ ]]; do
        tui_msg "输入错误" "QQ 号必须为纯数字"
        qq=$(tui_input "实例标识" "请输入机器人 QQ 号" "") || return
    done

    # 检查是否已存在
    load_instance "$qq"
    local container_exists=false; local dir_exists=false
    docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^${INST_CONTAINER}$" && container_exists=true
    [ -d "$INST_PROJECT_DIR" ] && dir_exists=true

    if $container_exists || $dir_exists; then
        local msg="实例 $qq 已存在：\n"
        $container_exists && msg+="● 容器: $INST_CONTAINER\n"
        $dir_exists && msg+="● 项目目录: $INST_PROJECT_DIR\n"
        msg+="\n是否重新部署？旧数据将备份保留。"
        tui_yesno "实例已存在" "$msg" || return 0
    fi

    # ─── 环境检测 ───
    title "🔍 环境检测"
    local all_ok=true
    command -v docker >/dev/null 2>&1 || { err "Docker 未安装"; all_ok=false; }
    command -v python3 >/dev/null 2>&1 || { err "Python3 未安装"; all_ok=false; }
    command -v screen >/dev/null 2>&1 || { err "screen 未安装"; all_ok=false; }
    command -v git >/dev/null 2>&1 || { err "git 未安装"; all_ok=false; }
    $all_ok && ok "环境检测通过" || { tui_msg "环境缺失" "请先安装缺失组件"; return 1; }

    # ─── 安装依赖 ───
    info "安装 Python 依赖..."
    pip3 install -q websocket-client requests flask 2>/dev/null && ok "Python 依赖就绪" || warn "pip3 install 失败，可稍后手动安装"

    # ─── 部署 NapCat ───
    deploy_napcat_for_instance "$qq" || return 1

    # ─── 部署项目 ───
    deploy_project_for_instance "$qq" || return 1

    # ─── 创建管理脚本 ───
    generate_bot_script "$qq"

    # ─── Web 面板（可选） ───
    setup_webpanel_for_instance "$qq"

    # ─── 保存实例信息 ───
    save_instance "$qq"

    sep
    ok "实例 $qq 部署完成！"
    info "容器: $INST_CONTAINER"
    info "项目目录: $INST_PROJECT_DIR"
    info "NapCat 配置: ${INST_NAP_DIR}/config/"
    info "\n下一步："
    info "1. 启动 NapCat 容器 → 扫码登录 QQ"
    info "2. 启动 Bot → bot start ${qq}"
    tui_msg "部署完成" "实例 $qq 部署成功！\n\n容器: $INST_CONTAINER\n项目: $INST_PROJECT_DIR\n\n可在「实例管理」中管理此实例。"
}

# 为某个实例部署 NapCat
deploy_napcat_for_instance() {
    local qq=$1
    load_instance "$qq"

    title "🐱 部署 NapCat — $qq"

    if tui_yesno "部署 NapCat" "是否为实例 $qq 部署独立的 NapCat 容器？\n（如已有 NapCat 容器或想跳过请选「否」）"; then
        # 拉取镜像
        if ! docker image inspect "${NAPCAT_IMAGE%%:*}" &>/dev/null 2>&1; then
            tui_infobox "拉取镜像" "正在拉取 NapCat 镜像（约 200MB）..."
            docker pull "$NAPCAT_IMAGE" || { err "镜像拉取失败"; return 1; }
        fi
        ok "NapCat 镜像已就绪"

        # 容器名 + 目录
        local cname="napcat_${qq}"
        local nap_dir="/root/napcat_${qq}"
        local config_dir="$nap_dir/config"
        local cache_dir="$nap_dir/cache/images"
        mkdir -p "$config_dir" "$cache_dir"

        # 网络模式
        local network_mode
        local nm_choice
        nm_choice=$(tui_menu "网络模式" "选择 $qq 的 NapCat 网络模式：" \
            "host" "Host 模式 — 端口直通，简单高效" \
            "bridge" "Bridge 模式 — 端口映射，灵活隔离") || nm_choice="host"
        network_mode=$nm_choice

        # 端口
        local http_port=3000 ws_port=3001 webui_port=6099
        if [[ "$network_mode" == "bridge" ]]; then
            http_port=$(tui_input "HTTP端口" "HTTP API 端口" "$http_port")
            ws_port=$(tui_input "WS端口" "WebSocket 端口" "$ws_port")
            webui_port=$(tui_input "WebUI端口" "NapCat 管理面板端口" "$webui_port")
        fi

        # Token
        local http_token ws_token
        tui_yesno "Token" "是否自动生成安全 Token？" && {
            http_token=$(gen_token); ws_token=$(gen_token)
        } || {
            http_token=$(tui_password "HTTP Token" "输入 HTTP Token（留空自动生成）")
            [[ -z "$http_token" ]] && http_token=$(gen_token)
            ws_token=$(tui_password "WS Token" "输入 WS Token（留空自动生成）")
            [[ -z "$ws_token" ]] && ws_token=$(gen_token)
        }

        # 写入配置
        local host_val="127.0.0.1"
        [[ "$network_mode" == "bridge" ]] && host_val="0.0.0.0"
        sed -e "s/__HTTP_PORT__/$http_port/g" \
            -e "s/__WS_PORT__/$ws_port/g" \
            -e "s/__HTTP_TOKEN__/$http_token/g" \
            -e "s/__WS_TOKEN__/$ws_token/g" \
            -e "s/__HOST__/$host_val/g" \
            "$TEMPLATES_DIR/napcat-onebot.json" > "$config_dir/onebot11_${qq}.json"
        cp "$TEMPLATES_DIR/napcat.json" "$config_dir/napcat.json"
        ok "NapCat 配置已写入 $config_dir"

        # 停止旧容器
        docker stop "$cname" 2>/dev/null; docker rm "$cname" 2>/dev/null

        # 创建容器
        local cmd="docker run -d --name $cname --restart unless-stopped"
        if [[ "$network_mode" == "host" ]]; then
            cmd+=" --network host"
        else
            cmd+=" -p 127.0.0.1:${http_port}:3000 -p 127.0.0.1:${ws_port}:3001 -p 127.0.0.1:${webui_port}:6099"
        fi
        cmd+=" -v $config_dir:/app/napcat/config -v $cache_dir:/app/cache/images $NAPCAT_IMAGE"

        info "执行: $cmd"
        eval "$cmd" && ok "容器 $cname 创建成功" || { err "创建失败"; return 1; }

        # 更新实例信息
        INST_CONTAINER="$cname"
        INST_NAP_DIR="$nap_dir"
        INST_HTTP="http://127.0.0.1:$http_port"
        INST_WS="ws://127.0.0.1:$ws_port/?access_token=$ws_token"
        INST_TOKEN="$http_token"

        tui_msg "NapCat 就绪" "实例 $qq 的 NapCat 容器已创建。\n\n启动后需扫码登录 QQ，可在「实例管理」中查看二维码。"
    else
        # 手动配置 NapCat 连接信息
        info "跳过 NapCat 部署，请输入已有 NapCat 连接信息"
        INST_HTTP=$(tui_input "HTTP 地址" "NapCat HTTP API 地址" "${INST_HTTP:-http://127.0.0.1:3000}")
        INST_WS=$(tui_input "WS 地址" "NapCat WebSocket 地址" "${INST_WS:-ws://127.0.0.1:3001/?access_token=}")
        INST_TOKEN=$(tui_input "HTTP Token" "NapCat HTTP Token" "${INST_TOKEN:-}")
    fi

    save_instance "$qq"
    return 0
}

# 从插件仓库拉取/更新插件到项目 plugins/ 目录
# 插件已独立到 NapCat-WordLibBot-Plugins 仓库，词库插件（wordlib.py）保留在主仓库
# 模式：ask（询问+勾选，默认）/ select（直接勾选）/ all（全部安装）
install_plugins() {
    local project_dir="${1:-$INST_PROJECT_DIR}"
    local mode="${2:-ask}"
    local plugins_dir="$project_dir/plugins"
    local cache_dir="/tmp/napbot_plugin_repo"

    if [ ! -d "$project_dir" ]; then
        err "项目目录不存在: $project_dir"
        return 1
    fi
    mkdir -p "$plugins_dir"

    info "从插件仓库获取插件: $PLUGIN_REPO"
    if [ -d "$cache_dir/.git" ]; then
        (cd "$cache_dir" && git pull --quiet) 2>/dev/null \
            && ok "插件仓库已更新" \
            || warn "插件仓库更新失败，使用本地缓存"
    else
        git clone --depth 1 "$PLUGIN_REPO" "$cache_dir" >/dev/null 2>&1 \
            || { err "插件仓库克隆失败: $PLUGIN_REPO"; return 1; }
        ok "插件仓库已克隆"
    fi

    # 询问是否拉取插件
    if [ "$mode" == "ask" ]; then
        if ! tui_yesno "拉取插件" "是否从插件仓库拉取插件？\n\n插件仓库: $PLUGIN_REPO"; then
            warn "已跳过插件安装（后续可在实例管理 → 更新插件 中安装）"
            return 0
        fi
    fi

    # 收集插件清单（排除非独立插件 jm_worker.py，它随 jm_downloader 自动安装）
    local py_files=()
    local f
    for f in "$cache_dir"/*.py; do
        [ -f "$f" ] || continue
        local bn=$(basename "$f" .py)
        [ "$bn" == "jm_worker" ] && continue
        py_files+=("$f")
    done
    if [ ${#py_files[@]} -eq 0 ]; then
        warn "插件仓库中没有可用插件"
        return 0
    fi

    # 选择要安装的插件
    local selected=()
    if [ "$mode" == "all" ]; then
        for f in "${py_files[@]}"; do selected+=("$(basename "$f" .py)"); done
    else
        local items=()
        local f
        for f in "${py_files[@]}"; do
            local bn=$(basename "$f" .py)
            local desc=$(_extract_plugin_desc "$f")
            items+=("$bn" "$desc" "ON")
        done
        local sel
        sel=$(whiptail --clear --backtitle "$SCRIPT_NAME v$SCRIPT_VERSION" \
            --title "选择插件" --checklist "勾选要安装的插件（空格选中，Tab 切换）" \
            0 0 0 "${items[@]}" 3>&1 1>&2 2>&3) || return 0
        # whiptail 输出为带引号列表，如 "marry" "jm_downloader"
        selected=()
        local name
        for name in $sel; do
            name=$(echo "$name" | tr -d '"')
            [ -n "$name" ] && selected+=("$name")
        done
    fi

    # 选中 jm_downloader 时自动附带其工作进程 jm_worker.py
    local add_worker=false
    local name
    for name in "${selected[@]}"; do
        [ "$name" == "jm_downloader" ] && add_worker=true
    done

    local installed=""
    for name in "${selected[@]}"; do
        if [ -f "$cache_dir/$name.py" ]; then
            cp "$cache_dir/$name.py" "$plugins_dir/" || { err "复制插件失败: $name"; return 1; }
            installed+="$name "
        fi
    done
    if $add_worker && [ -f "$cache_dir/jm_worker.py" ]; then
        cp "$cache_dir/jm_worker.py" "$plugins_dir/"
        installed+="jm_worker "
    fi

    if [ -n "$installed" ]; then
        ok "插件已安装: ${installed}"
        warn "新插件需重启 Bot（或发送「重启」命令）后生效"
    else
        warn "未安装任何插件"
    fi
    return 0
}

# 提取插件文件中的 __plugin_desc__ 元数据（用于勾选列表展示）
_extract_plugin_desc() {
    local f="$1"
    grep -m1 '^__plugin_desc__\s*=\s*"' "$f" 2>/dev/null \
        | sed 's/^__plugin_desc__\s*=\s*"//; s/"\s*$//' || echo "无描述"
}

# 为某个实例部署项目
deploy_project_for_instance() {
    local qq=$1
    load_instance "$qq"

    title "📁 部署项目 — $qq"

    local deploy_mode
    deploy_mode=$(tui_menu "部署方式" "选择项目部署方式：" \
        "clone" "从 GitHub 克隆新项目" \
        "local" "使用本地已有项目") || deploy_mode="clone"

    local project_dir="${INST_PROJECT_DIR}"
    if [[ "$deploy_mode" == "clone" ]]; then
        project_dir=$(tui_input "项目目录" "安装到哪个目录？（默认脚本目录下 instances/<QQ>）" "${INSTANCES_ROOT}/${qq}")
        if [ -d "$project_dir/.git" ]; then
            tui_yesno "更新" "目录已存在，是否 git pull 更新？" && {
                cd "$project_dir" && git pull && ok "已更新"
            }
        else
            mkdir -p "$(dirname "$project_dir")"
            info "克隆项目到 $project_dir ..."
            git clone "$GIT_REPO" "$project_dir" || { err "克隆失败"; return 1; }
            ok "项目已克隆"
        fi
    else
        project_dir=$(tui_input "项目路径" "输入已有项目目录的完整路径" "${INSTANCES_ROOT}/${qq}")
        while [ ! -f "$project_dir/main.py" ]; do
            tui_msg "路径错误" "目录中未找到 main.py"
            project_dir=$(tui_input "项目路径" "输入正确路径" "$project_dir") || return 1
        done
        ok "有效项目: $project_dir"
    fi

    cd "$project_dir"
    INST_PROJECT_DIR="$project_dir"

    # 从插件仓库获取插件（主仓库仅保留词库插件）
    install_plugins "$project_dir" || warn "插件安装失败，请稍后手动安装"

    # ─── 配置向导 ───
    title "⚙️  配置向导 — $qq"

    local bot_name master_qq
    bot_name=$(tui_input "机器人昵称" "输入机器人昵称" "Bot_${qq}")
    # 主人 QQ 必填（拥有全部管理权限），支持逗号分隔多个
    while :; do
        master_qq=$(tui_input "主人 QQ" "输入主人 QQ 号（可多个，逗号分隔，必填）" "")
        if [ -n "$master_qq" ]; then
            break
        fi
        tui_msg "提示" "主人 QQ 不能为空，请重新输入"
    done

    # 处理主人 QQ 列表
    local master_qq_list
    if echo "$master_qq" | grep -q ","; then
        master_qq_list="["
        local first=true
        for q in $(echo "$master_qq" | tr ',' ' '); do
            q=$(echo "$q" | xargs)
            $first && master_qq_list+="\"$q\"" && first=false || master_qq_list+=", \"$q\""
        done
        master_qq_list+="]"
    else
        master_qq_list="[\"$master_qq\"]"
    fi

    # 生成 config.json
    cat > "$project_dir/config.json" <<-EOF
{
  "_note": "${bot_name}(QQ:${qq}) 机器人配置",
  "BOT_NAME": "${bot_name}",
  "MASTER_QQ": ${master_qq_list},
  "BOT_QQ": ${qq},
  "NAPCAT_HTTP": "${INST_HTTP}",
  "ACCESS_TOKEN": "${INST_TOKEN}",
  "WS_URL": "${INST_WS}"
}
EOF
    ok "config.json 已生成"

    # 生成 wordlib_config.json
    mkdir -p "$project_dir/data"
    if [ ! -f "$project_dir/data/wordlib_config.json" ]; then
        cat > "$project_dir/data/wordlib_config.json" <<-EOF
{
  "_note": "词库插件配置",
  "commands": {
    "add": "${bot_name}跟我学",
    "delete": "${bot_name}忘掉",
    "query": "${bot_name}回忆一下",
    "encode": "转码",
    "sign1": "签到",
    "sign2": "${bot_name}签到",
    "nickname": "${bot_name}以后叫我",
    "rank": "签到排行",
    "praise1": "${bot_name}赞我",
    "add_fuzzy": "添加模糊词条",
    "enable": "开启词库",
    "disable": "关闭词库"
  },
  "settings": { "enabled": true, "favor_add_max": 3, "favor_minus_max": 2, "nickname_need_favor": 10, "rank_top_n": 10, "praise_count": 10, "encode_timeout": 300 },
  "admins": []
}
EOF
        ok "wordlib_config.json 已初始化"
    fi

    INST_BOT_NAME="$bot_name"
    save_instance "$qq"

    sep
    ok "项目部署完成 ✅"
    info "目录: $project_dir"
}

# 生成 bot 管理脚本
generate_bot_script() {
    local qq=$1
    load_instance "$qq"

    # 检查 project_dir 是否有 bot 脚本
    if [ -f "$INST_PROJECT_DIR/bot" ]; then
        ln -sf "$INST_PROJECT_DIR/bot" /usr/local/bin/bot_${qq} 2>/dev/null
        ok "管理命令: bot_${qq} start/stop/restart/status"
    else
        # 生成一个独立的 bot 脚本
        cat > "/usr/local/bin/bot_${qq}" <<-EOF
#!/bin/bash
# Bot 管理脚本 — 实例 $qq
DIR="$INST_PROJECT_DIR"
SN="$INST_SCREEN"
BN="$INST_BOT_NAME"
BQ="$qq"
CMD="start|stop|restart|status"

case "\$1" in
    start)
        screen -S "\$SN" -X quit 2>/dev/null; sleep 1
        cd "\$DIR" && screen -dmS "\$SN" python3 main.py --bot-name "\$BN" --bot-qq "\$BQ"
        sleep 1; screen -list | grep -q "\$SN" && echo "✓ \$BN 已启动" || echo "✗ 启动失败"
        ;;
    stop)
        screen -S "\$SN" -X quit 2>/dev/null; echo "✓ \$BN 已停止"
        ;;
    restart)
        screen -S "\$SN" -X quit 2>/dev/null; sleep 1
        cd "\$DIR" && screen -dmS "\$SN" python3 main.py --bot-name "\$BN" --bot-qq "\$BQ"
        sleep 1; screen -list | grep -q "\$SN" && echo "✓ \$BN 已重启" || echo "✗ 重启失败"
        ;;
    status)
        screen -list | grep -q "\$SN" && echo "● \$BN (QQ:\$BQ) 运行中" || echo "○ \$BN (QQ:\$BQ) 未运行"
        ;;
    *)
        echo "用法: bot_${qq} start|stop|restart|status"
        ;;
esac
EOF
        chmod +x "/usr/local/bin/bot_${qq}"
        ok "管理命令: bot_${qq} start/stop/restart/status"
    fi
}

# 为实例创建独立 Web 面板（可选）
setup_webpanel_for_instance() {
    local qq=$1
    load_instance "$qq"

    tui_yesno "Web面板" "是否为实例 $qq 创建独立的 Web 管理面板？\n\n每个实例可以有专属面板，独立管理自己的配置。" || return 0

    local host="127.0.0.1"
    tui_yesno "公网访问" "是否开放公网访问？\n\n选择「是」则绑定 0.0.0.0（公网可访问）\n选择「否」则仅本机访问" && host="0.0.0.0"

    local port=8080
    port=$(tui_input "Web端口" "输入 Web 面板端口\n（不要和其他实例重复）" "$port")

    local screen_name="web_${qq}"

    # 创建启动脚本
    local start_script="$INST_PROJECT_DIR/start_webpanel.sh"
    cat > "$start_script" <<-EOF
#!/bin/bash
cd "$INST_PROJECT_DIR"
exec python3 web/api.py --host ${host} --port ${port} --bot-dir "$INST_PROJECT_DIR" --bot-name "$INST_BOT_NAME" --bot-qq "$qq" --bot-screen "bot_${qq}"
EOF
    chmod +x "$start_script"

    # 用 screen 启动
    screen -S "$screen_name" -X quit 2>/dev/null; sleep 0.5
    screen -dmS "$screen_name" bash "$start_script"
    sleep 1

    if screen -list 2>/dev/null | grep -q "$screen_name"; then
        ok "Web 面板已启动 (端口 $port)"
        local disp="$host"
        [[ "$host" == "0.0.0.0" ]] && disp="<服务器IP>"
        info "访问地址: http://${disp}:${port}/"
        info "Screen: $screen_name"

        # 可选 systemd 服务
        if tui_yesno "systemd" "是否创建 systemd 服务实现开机自启？"; then
            cat > "/etc/systemd/system/mybot-web-${qq}.service" <<-EOF
[Unit]
Description=MyBot Web Panel - Instance $qq
After=network.target

[Service]
Type=simple
WorkingDirectory=${INST_PROJECT_DIR}
ExecStart=/usr/bin/python3 ${INST_PROJECT_DIR}/web/api.py --host ${host} --port ${port} --bot-dir "${INST_PROJECT_DIR}" --bot-name "${INST_BOT_NAME}" --bot-qq "${qq}" --bot-screen "bot_${qq}"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
            systemctl daemon-reload
            systemctl enable "mybot-web-${qq}.service" 2>/dev/null
            systemctl restart "mybot-web-${qq}.service" 2>/dev/null
            ok "systemd 服务已创建: mybot-web-${qq}"
        fi
    else
        err "Web 面板启动失败"
    fi
}

# ───────────────────────── 2. 实例管理 ─────────────────────────

instance_management() {
    while true; do
        # 扫描实例
        local qqs=($(scan_instances))

        if [ ${#qqs[@]} -eq 0 ]; then
            tui_msg "实例管理" "暂无已部署的实例。\n\n请先选择「部署新实例」。"
            return
        fi

        # 构建菜单
        local menu_items=()
        for qq in "${qqs[@]}"; do
            local status="?"
            docker ps --format '{{.Names}}' 2>/dev/null | grep -q "napcat_${qq}" && status="容器✔" || status="容器✗"
            screen -list 2>/dev/null | grep -q "bot_${qq}" && status+=" Bot✔" || status+=" Bot✗"
            menu_items+=("$qq" "QQ:$qq  ${status}")
        done
        menu_items+=("R" "🔙 返回主菜单")

        local choice
        choice=$(tui_menu "🗂  实例管理" \
            "已部署实例（${#qqs[@]}个）:\n选择实例查看/管理：" \
            "${menu_items[@]}") || { return; }

        [[ "$choice" == "R" || -z "$choice" ]] && return

        instance_action "$choice"
    done
}

# 单个实例操作菜单
instance_action() {
    local qq=$1
    load_instance "$qq"

    while true; do
        local container_status="✗ 未创建"; local bot_status="✗ 未运行"
        local container_line=$(docker ps -a --format '{{.Names}} {{.Status}}' 2>/dev/null | grep "^napcat_${qq} " | head -1)
        if [ -n "$container_line" ]; then
            container_status="$(echo "$container_line" | cut -d" " -f2-)"
        fi

        screen -list 2>/dev/null | grep -q "bot_${qq}" && bot_status="● 运行中" || bot_status="○ 已停止"

        local container_running=false
        docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^napcat_${qq}$" && container_running=true

        local choice
        choice=$(tui_menu "实例 $qq" \
            "QQ: $qq  |  容器: $container_status  |  Bot: $bot_status\n\n选择操作：" \
            "1" "📊 完整状态" \
            "2" "▶️  启动 NapCat 容器" \
            "3" "⏹  停止 NapCat 容器" \
            "4" "🔄 重启 NapCat 容器" \
            "5" "📱 查看二维码（扫码登录）" \
            "6" "🤖 Bot 管理" \
            "7" "📋 查看日志" \
            "8" "🔌 更新插件（从插件仓库拉取）" \
            "9" "❌ 卸载实例" \
            "R" "🔙 返回实例列表") || return

        case "$choice" in
            1)
                title "实例 $qq 状态"
                echo "QQ: $qq"
                echo "容器: napcat_${qq}"
                echo "项目: $INST_PROJECT_DIR"
                echo "Screen: $INST_SCREEN"
                echo ""
                docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null | grep "napcat_${qq}\|NAMES" || echo "容器未创建"
                echo ""
                screen -list | grep "bot_${qq}" || echo "Bot 未运行"
                read -p "按回车继续..."
                ;;
            2)
                docker start "napcat_${qq}" 2>/dev/null && ok "容器已启动" || err "启动失败（可能不存在）"
                read -p "按回车继续..."
                ;;
            3)
                docker stop "napcat_${qq}" 2>/dev/null && ok "容器已停止" || true
                read -p "按回车继续..."
                ;;
            4)
                docker restart "napcat_${qq}" 2>/dev/null && ok "容器已重启" || err "重启失败"
                read -p "按回车继续..."
                ;;
            5)
                title "📱 登录二维码 — $qq"
                local qr_file="/tmp/napcat_qr_${qq}.png"
                docker exec "napcat_${qq}" cat /app/napcat/cache/qrcode.png 2>/dev/null > "$qr_file"
                if [ -s "$qr_file" ]; then
                    info "二维码已保存: $qr_file"
                    command -v chafa &>/dev/null && chafa "$qr_file" 2>/dev/null
                    command -v img2txt &>/dev/null && img2txt "$qr_file" 2>/dev/null
                    echo "或用浏览器打开 NapCat WebUI 扫码"
                    echo "  http://<IP>:$(docker port napcat_${qq} 2>/dev/null | grep 6099 | head -1 | grep -oP '\d+$' || echo 6099)"
                else
                    err "暂未生成二维码（NapCat 可能未就绪）"
                    docker logs "napcat_${qq}" --tail 5 2>&1
                fi
                read -p "按回车继续..."
                ;;
            6)
                bot_action_menu "$qq"
                ;;
            7)
                log_menu "$qq"
                ;;
            8)
                title "🔌 更新插件 — $qq"
                install_plugins "$INST_PROJECT_DIR"
                read -p "按回车继续..."
                ;;
            9)
                if tui_yesno "卸载实例" "确定要卸载实例 $qq 吗？\n\n这将删除 NapCat 容器（保留配置目录）。\n项目文件不会被删除。"; then
                    docker stop "napcat_${qq}" 2>/dev/null
                    docker rm "napcat_${qq}" 2>/dev/null
                    rm -f "$INSTANCES_DIR/${qq}.sh"
                    rm -f "/usr/local/bin/bot_${qq}"
                    ok "实例 $qq 已卸载"
                    return
                fi
                ;;
            R|*) return ;;
        esac
    done
}

# Bot 操作菜单
bot_action_menu() {
    local qq=$1
    load_instance "$qq"

    while true; do
        local bot_running=false
        screen -list 2>/dev/null | grep -q "bot_${qq}" && bot_running=true

        local choice
        choice=$(tui_menu "🤖 Bot $qq" \
            "Bot 状态: $(screen -list | grep -q bot_${qq} && echo '● 运行中' || echo '○ 已停止')\n\n选择操作：" \
            "1" "📊 查看状态" \
            "2" "▶️  启动" \
            "3" "⏹  停止" \
            "4" "🔄 重启" \
            "5" "📋 查看日志 (runtime.log)" \
            "R" "🔙 返回") || return

        case "$choice" in
            1)
                if command -v "bot_${qq}" &>/dev/null; then
                    "bot_${qq}" status
                elif [ -f "$INST_PROJECT_DIR/bot" ]; then
                    bash "$INST_PROJECT_DIR/bot" status
                else
                    screen -list | grep -q "bot_${qq}" && ok "运行中" || err "未运行"
                fi
                read -p "按回车继续..."
                ;;
            2)
                local cmd_path="/usr/local/bin/bot_${qq}"
                if [ -x "$cmd_path" ]; then
                    "$cmd_path" start
                else
                    screen -S "bot_${qq}" -X quit 2>/dev/null; sleep 1
                    cd "$INST_PROJECT_DIR" && screen -dmS "bot_${qq}" python3 main.py --bot-name "$INST_BOT_NAME" --bot-qq "$qq"
                    sleep 1; screen -list | grep -q "bot_${qq}" && ok "已启动" || err "启动失败"
                fi
                read -p "按回车继续..."
                ;;
            3)
                screen -S "bot_${qq}" -X quit 2>/dev/null; ok "已停止"; read -p "按回车继续..."
                ;;
            4)
                local cmd_path="/usr/local/bin/bot_${qq}"
                if [ -x "$cmd_path" ]; then
                    "$cmd_path" restart
                else
                    screen -S "bot_${qq}" -X quit 2>/dev/null; sleep 1
                    cd "$INST_PROJECT_DIR" && screen -dmS "bot_${qq}" python3 main.py --bot-name "$INST_BOT_NAME" --bot-qq "$qq"
                    sleep 1; screen -list | grep -q "bot_${qq}" && ok "已重启" || err "重启失败"
                fi
                read -p "按回车继续..."
                ;;
            5)
                local log_file="$INST_PROJECT_DIR/runtime.log"
                [ -f "$log_file" ] && tail -30 "$log_file" || err "暂无日志"
                read -p "按回车继续..."
                ;;
            R|*) return ;;
        esac
    done
}

# 日志菜单
log_menu() {
    local qq=$1
    local choice
    choice=$(tui_menu "📋 日志 — $qq" \
        "选择查看：" \
        "1" "🐱 NapCat 容器日志" \
        "2" "🤖 Bot 运行日志 (runtime.log)" \
        "R" "🔙 返回") || return

    case "$choice" in
        1)
            local lines
            lines=$(tui_input "行数" "显示最近多少行？" "50")
            echo; docker logs "napcat_${qq}" --tail "$lines" 2>&1
            echo; read -p "按回车继续..."
            ;;
        2)
            load_instance "$qq"
            local log_file="$INST_PROJECT_DIR/runtime.log"
            if [ -f "$log_file" ]; then
                local lines
                lines=$(tui_input "行数" "显示最近多少行？" "50")
                echo; info "$qq runtime.log"
                tail -"$lines" "$log_file" 2>/dev/null
            else
                err "未找到 runtime.log"
            fi
            read -p "按回车继续..."
            ;;
    esac
}

# ───────────────────────── 后续设置 ─────────────────────────

post_setup() {
    title "🔗 后续设置"

    # 创建 napbot 命令（指向用户目录 ~/napbot/install.sh 的稳定副本）
    tui_yesno "管理命令" "将 napbot 安装到系统（ln -s → $NAPBOT_HOME/install.sh）？" && {
        local nap_target="$NAPBOT_HOME/install.sh"
        if [ ! -f "$nap_target" ]; then
            # 副本缺失：尝试从当前脚本复制（curl 管道运行时 $0 不可用）
            if [[ -f "$0" && "$0" != /dev/fd/* ]]; then
                mkdir -p "$NAPBOT_HOME"
                cp "$0" "$nap_target" 2>/dev/null
            fi
        fi
        if [ -f "$nap_target" ]; then
            chmod +x "$nap_target"
            ln -sf "$nap_target" /usr/local/bin/napbot
            ok "已创建 napbot 命令 → $nap_target"
            info "脚本已保存到用户目录: $nap_target（实例将创建于 $nap_target 所在目录的 instances/ 下）"
        else
            warn "无法定位脚本实体文件（当前可能通过 curl 管道运行）"
            warn "请手动保存脚本到用户目录后重试："
            warn "  mkdir -p $NAPBOT_HOME"
            warn "  curl -sL $GIT_REPO/raw/master/install.sh -o $nap_target && chmod +x $nap_target"
        fi
    }

    # Web 面板配置
    if tui_yesno "Web面板" "是否为 Web 管理面板配置 systemd 服务？\nWeb 面板用于在浏览器中管理词库配置。"; then
        local web_dir
        web_dir=$(dirname "$SCRIPT_PATH")

        local host="127.0.0.1"
        tui_yesno "公网访问" "是否开放公网访问？\n\n选择「是」则绑定 0.0.0.0（公网可访问）\n选择「否」则仅本机访问" && host="0.0.0.0"

        local port=8080
        port=$(tui_input "端口" "Web 面板监听端口" "8080")

        cat > /etc/systemd/system/mybot-api.service <<-EOF
[Unit]
Description=MyBot Web Panel API
After=network.target

[Service]
Type=simple
WorkingDirectory=${web_dir}
ExecStart=/usr/bin/python3 ${web_dir}/web/api.py --host ${host} --port ${port}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
        systemctl daemon-reload
        systemctl enable mybot-api.service 2>/dev/null
        systemctl restart mybot-api.service 2>/dev/null
        ok "Web 面板已启动"
        info "地址: http://${host}:${port}/"
    fi
}

# ───────────────────────── 主菜单 ─────────────────────────

main_menu() {
    while true; do
        local choice
        choice=$(tui_menu "NapCat WordLib Bot v$SCRIPT_VERSION" \
            "欢迎使用一键安装部署脚本！\n请选择操作：" \
            "1" "📦 部署新实例 — 为某个QQ号部署独立的NapCat+Bot" \
            "2" "🗂  实例管理 — 查看/管理已部署的实例" \
            "3" "🔗 后续设置 — Web面板/napbot命令" \
            "4" "📖 使用教程 — 查看 USAGE.md 完整教程" \
            "Q" "🚪 退出") || { clear; exit 0; }

        case "$choice" in
            1) deploy_new_instance ;;
            2) instance_management ;;
            3) post_setup ;;
            4) show_usage ;;
            Q|q|"") clear; echo "bye~"; exit 0 ;;
        esac
    done
}

# 查看使用教程（USAGE.md）
show_usage() {
    local usage_file=""
    if [ -f "$BASE_DIR/USAGE.md" ]; then
        usage_file="$BASE_DIR/USAGE.md"
    elif [ -f "$NAPBOT_HOME/USAGE.md" ]; then
        usage_file="$NAPBOT_HOME/USAGE.md"
    fi
    if [ -n "$usage_file" ]; then
        if command -v less >/dev/null 2>&1; then
            less "$usage_file"
        else
            cat "$usage_file"
        fi
    else
        warn "未找到本地 USAGE.md，可在线查看："
        warn "  https://github.com/Bdlxx/NapCat-WordLibBot/blob/master/USAGE.md"
        read -p "按回车继续..."
    fi
}

# ───────────────────────── 入口 ─────────────────────────
check_root
clear

tui_infobox "NapCat WordLib Bot v$SCRIPT_VERSION" \
    "🤖 NapCat WordLib Bot — 一键安装部署脚本\n\
仓库: https://github.com/Bdlxx/NapCat-WordLibBot\n\n\
功能：\n\
  1. 部署新实例 — 为每个QQ号独立部署\n\
  2. 实例管理 — 管理已部署的实例\n\n\
加载中..."

sleep 0.5
main_menu

#!/bin/bash
# ===============================================================
# NapCat WordLib Bot — 一键安装部署 & 运行管理脚本
# 仓库: https://github.com/Bdlxx/NapCat-WordLibBot
# 用法: bash install.sh  或安装后执行  napbot
# ===============================================================

# ───────────────────────── 配置区 ─────────────────────────
SCRIPT_NAME="NapCat-WordLibBot"
SCRIPT_VERSION="1.0.0"
NAPCAT_IMAGE="docker.xuanyuan.me/mlikiowa/napcat-docker:latest"
GIT_REPO="https://github.com/Bdlxx/NapCat-WordLibBot.git"
BOT_MANAGER="/usr/local/bin/bot"
TEMPLATES_DIR="$(cd "$(dirname "$0")" && pwd)/templates"
SCRIPT_PATH="$(cd "$(dirname "$0")" && pwd)/install.sh"
NAPCAT_BASE="/root/napcat"

# ───────────────────────── 颜色常量和输出函数 ─────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'; BOLD='\033[1m'

ok()   { echo -e "${GREEN}✓${NC} $1"; }
err()  { echo -e "${RED}✗${NC} $1"; }
info() { echo -e "${CYAN}ℹ${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
title(){ echo -e "\n${BOLD}${BLUE}══ $1 ══${NC}\n"; }
sep()  { echo -e "${BLUE}────────────────────────────────────────${NC}"; }

# ───────────────────────── TUI 辅助函数 ─────────────────────────
# 统一使用 whiptail（dialog 兼容备选）
_whiptail() {
    whiptail --clear --backtitle "$SCRIPT_NAME v$SCRIPT_VERSION" "$@"
}

tui_menu() {
    # 用法: tui_menu title text [tag item]...
    local title="$1"; shift; local text="$1"; shift
    whiptail --clear --backtitle "$SCRIPT_NAME v$SCRIPT_VERSION" \
        --title "$title" --menu "$text" 0 0 0 "$@" 3>&1 1>&2 2>&3
    return $?
}

tui_input() {
    local title="$1" text="$2" init="$3"
    whiptail --clear --backtitle "$SCRIPT_NAME v$SCRIPT_VERSION" \
        --title "$title" --inputbox "$text" 0 0 "$init" 3>&1 1>&2 2>&3
    return $?
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

# ───────────────────────── 核心工具函数 ─────────────────────────

# 生成随机 token
gen_token() {
    openssl rand -base64 12 2>/dev/null | tr -dc 'a-zA-Z0-9~!@#$%^&*_+' | head -c 16
    if [[ $? -ne 0 || -z "$(openssl rand -base64 12 2>/dev/null)" ]]; then
        date +%s%N | md5sum | head -c 16
    fi
}

# 检测 root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        err "此脚本需要 root 权限运行（sudo bash install.sh）"
        exit 1
    fi
}

# ───────────────────────── 页面一：部署与配置 ─────────────────────────

# 1. 环境检测
page1_env_check() {
    title "🔍 环境检测"
    local report=""
    local all_ok=true

    # OS 检测
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        info "系统: $NAME $VERSION_ID ($(uname -m))"
        report+="✔ 系统: $NAME $VERSION_ID\n"
    else
        warn "无法识别操作系统发行版"
        report+="⚠ 系统: 未知\n"
    fi

    # Docker
    if command -v docker &>/dev/null; then
        local dv=$(docker --version 2>/dev/null | grep -oP '\d+\.\d+\.\d+' | head -1)
        ok "Docker: $dv"
        report+="✔ Docker: $dv\n"
    else
        err "Docker: 未安装"
        report+="✗ Docker: 未安装\n"; all_ok=false
    fi

    # Python3
    if command -v python3 &>/dev/null; then
        local pv=$(python3 --version 2>&1 | grep -oP '\d+\.\d+\.\d+')
        local pv_num=$(python3 -c 'import sys; print(1 if sys.version_info >= (3,10) else 0)' 2>/dev/null)
        if [[ "$pv_num" == "1" ]]; then
            ok "Python3: $pv"
            report+="✔ Python3: $pv\n"
        else
            err "Python3: $pv（需 ≥3.10）"
            report+="✗ Python3: $pv（需 ≥3.10）\n"; all_ok=false
        fi
    else
        err "Python3: 未安装"
        report+="✗ Python3: 未安装\n"; all_ok=false
    fi

    # pip3
    if command -v pip3 &>/dev/null; then
        ok "pip3: 已安装"
        report+="✔ pip3: 已安装\n"
    else
        err "pip3: 未安装"
        report+="✗ pip3: 未安装\n"; all_ok=false
    fi

    # screen
    if command -v screen &>/dev/null; then
        ok "screen: 已安装"
        report+="✔ screen: 已安装\n"
    else
        err "screen: 未安装"
        report+="✗ screen: 未安装\n"; all_ok=false
    fi

    # git
    if command -v git &>/dev/null; then
        ok "git: 已安装"
        report+="✔ git: 已安装\n"
    else
        err "git: 未安装"
        report+="✗ git: 未安装\n"; all_ok=false
    fi

    # whiptail
    if command -v whiptail &>/dev/null; then
        ok "whiptail: 已安装"
        report+="✔ whiptail: 已安装\n"
    else
        err "whiptail: 未安装（建议 apt install whiptail）"
        report+="✗ whiptail: 未安装\n"; all_ok=false
    fi

    # NapCat 镜像
    if docker image inspect "${NAPCAT_IMAGE##*[/:]}" &>/dev/null 2>&1; then
        ok "NapCat 镜像: 已拉取"
        report+="✔ NapCat 镜像: 已拉取\n"
    else
        info "NapCat 镜像: 未拉取（部署时自动拉取）"
        report+="ℹ NapCat 镜像: 未拉取\n"
    fi

    sep
    tui_msg "环境检测结果" "$report\n\n$all_ok 全部就绪，可以开始部署" || true
}

# 2. 安装依赖
page1_install_deps() {
    title "📦 安装依赖"

    local missing_pkgs=()
    command -v whiptail >/dev/null 2>&1 || missing_pkgs+=("whiptail")
    command -v docker >/dev/null 2>&1 || missing_pkgs+=("docker.io")
    command -v screen >/dev/null 2>&1 || missing_pkgs+=("screen")
    command -v git >/dev/null 2>&1 || missing_pkgs+=("git")

    if [ ${#missing_pkgs[@]} -gt 0 ]; then
        info "安装系统包: ${missing_pkgs[*]}"
        if command -v apt &>/dev/null; then
            apt update -qq && apt install -y "${missing_pkgs[@]}" && ok "系统包安装完成" || err "系统包安装失败"
        elif command -v yum &>/dev/null; then
            yum install -y "${missing_pkgs[@]}" && ok "系统包安装完成" || err "系统包安装失败"
        else
            err "不支持的包管理器，请手动安装: ${missing_pkgs[*]}"
        fi
    else
        ok "系统包已齐全"
    fi

    # Python 包
    info "安装 Python 依赖包..."
    pip3 install -q websocket-client requests flask 2>/dev/null && {
        ok "Python 依赖安装完成"
    } || err "Python 依赖安装失败，请手动执行: pip3 install websocket-client requests flask"
}

# 3. 部署 NapCat
page1_deploy_napcat() {
    title "🐱 部署 NapCat"

    # 检查是否已有 NapCat 容器
    local existing=()
    for c in napcat napcat2; do
        if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^$c$"; then
            existing+=("$c")
        fi
    done

    if [ ${#existing[@]} -gt 0 ]; then
        info "已有 NapCat 容器: ${existing[*]}"
        tui_yesno "NapCat" "检测到已有 NapCat 容器，是否重新部署？\n（不会删除已有配置数据）" || return 0
    fi

    if ! tui_yesno "部署 NapCat" "即将部署 NapCat Docker 容器。\n需要先拉取镜像（约 200MB），是否继续？"; then
        info "跳过 NapCat 部署"
        return 0
    fi

    # 拉取镜像
    tui_infobox "拉取镜像" "正在拉取 NapCat Docker 镜像，请稍候..."
    echo
    docker pull "$NAPCAT_IMAGE"
    if [ $? -ne 0 ]; then
        err "镜像拉取失败，请检查网络或手动执行: docker pull $NAPCAT_IMAGE"
        read -p "按回车继续..."
        return 1
    fi
    ok "镜像拉取完成"

    # 选择实例数量
    local instance_count=1
    local choice
    choice=$(tui_menu "实例数量" "要部署几个 NapCat 实例？" \
        1 "单实例（1个机器人）" \
        2 "双实例（2个机器人）") || choice=1
    instance_count=$choice

    # 遍历部署每个实例
    for ((i=1; i<=instance_count; i++)); do
        sep
        info "配置第 $i 个 NapCat 实例"

        local container_name="napcat"
        [[ $i -eq 2 ]] && container_name="napcat2"

        local default_http=3000 default_ws=3001 default_webui=6099
        [[ $i -eq 2 ]] && default_http=3002 && default_ws=3003 && default_webui=6100

        local qq
        qq=$(tui_input "实例 $i QQ号" "请输入机器人 QQ 号（数字）" "") || qq=""
        while [[ -z "$qq" || ! "$qq" =~ ^[0-9]+$ ]]; do
            tui_msg "输入错误" "QQ 号必须为数字，不能为空"
            qq=$(tui_input "实例 $i QQ号" "请输入机器人 QQ 号（数字）" "") || qq=""
        done

        local network_mode="host"
        local nm_choice
        nm_choice=$(tui_menu "网络模式" "选择容器网络模式：\n\nhost=主机模式（推荐单实例）\nbridge=桥接模式（推荐多实例）" \
            "host" "Host 模式 — 端口直通，简单高效（推荐单实例）" \
            "bridge" "Bridge 模式 — 端口映射，灵活隔离（推荐多实例）") || nm_choice="host"
        network_mode=$nm_choice

        local http_port=$default_http ws_port=$default_ws webui_port=$default_webui
        if [[ "$network_mode" == "bridge" ]]; then
            http_port=$(tui_input "HTTP端口" "HTTP API 端口（供机器人调用）" "$default_http")
            ws_port=$(tui_input "WS端口" "WebSocket 端口（供机器人连接）" "$default_ws")
            webui_port=$(tui_input "WebUI端口" "NapCat 管理面板端口" "$default_webui")
        fi

        # 生成 token
        local http_token ws_token
        local auto_token
        auto_token=$(tui_yesno "Token" "是否自动生成安全 Token？\n\n选择「否」则手动输入") && auto_token=true || auto_token=false

        if $auto_token; then
            http_token=$(gen_token)
            ws_token=$(gen_token)
            ok "Token 已自动生成"
        else
            http_token=$(tui_password "HTTP Token" "输入 HTTP API Token（留空自动生成）")
            [[ -z "$http_token" ]] && http_token=$(gen_token)
            ws_token=$(tui_password "WS Token" "输入 WebSocket Token（留空自动生成）")
            [[ -z "$ws_token" ]] && ws_token=$(gen_token)
        fi

        # 配置目录
        local config_dir="$NAPCAT_BASE/config"
        local cache_dir="$NAPCAT_BASE/cache/images"
        [[ $i -eq 2 ]] && config_dir="/root/napcat2/config" && cache_dir="/root/napcat2/cache/images"
        mkdir -p "$config_dir" "$cache_dir"

        # 写入 NapCat onebot 配置
        local host_val="127.0.0.1"
        [[ "$network_mode" == "bridge" ]] && host_val="0.0.0.0"

        sed -e "s/__HTTP_PORT__/$http_port/g" \
            -e "s/__WS_PORT__/$ws_port/g" \
            -e "s/__HTTP_TOKEN__/$http_token/g" \
            -e "s/__WS_TOKEN__/$ws_token/g" \
            -e "s/__HOST__/$host_val/g" \
            "$TEMPLATES_DIR/napcat-onebot.json" > "$config_dir/onebot11_${qq}.json"

        # 写入 napcat.json
        cp "$TEMPLATES_DIR/napcat.json" "$config_dir/napcat.json"

        ok "配置已写入 $config_dir"

        # 停止并删除旧容器
        docker stop "$container_name" 2>/dev/null; docker rm "$container_name" 2>/dev/null

        # 构建 docker run 命令
        local docker_cmd="docker run -d"
        docker_cmd+=" --name $container_name"
        docker_cmd+=" --restart unless-stopped"

        if [[ "$network_mode" == "host" ]]; then
            docker_cmd+=" --network host"
        else
            docker_cmd+=" -p 127.0.0.1:$http_port:3000 -p 127.0.0.1:$ws_port:3001 -p 127.0.0.1:$webui_port:6099"
        fi

        docker_cmd+=" -v $config_dir:/app/napcat/config"
        docker_cmd+=" -v $cache_dir:/app/cache/images"
        docker_cmd+=" $NAPCAT_IMAGE"

        info "创建容器: $container_name"
        echo "  $docker_cmd"
        eval "$docker_cmd"

        if [ $? -eq 0 ]; then
            ok "容器 $container_name 创建成功"
            # 保存配置信息供后续使用
            local instance_file="/tmp/napbot_instance_${i}.sh"
            cat > "$instance_file" <<-EOF
NAPCAT_QQ[$i]="$qq"
NAPCAT_NAME[$i]="$container_name"
NAPCAT_HTTP[$i]="http://127.0.0.1:$http_port"
NAPCAT_WS[$i]="ws://127.0.0.1:$ws_port/?access_token=$ws_token"
NAPCAT_TOKEN[$i]="$http_token"
NAPCAT_WEBUI[$i]="http://127.0.0.1:$webui_port"
EOF
        else
            err "容器 $container_name 创建失败"
        fi
    done

    tui_msg "NapCat 部署完成" "NapCat 容器已创建。\n\n下一步：启动后需要扫码登录 QQ。\n可以在「运行管理 → NapCat 管理」中查看二维码。"
}

# 4. 部署项目
page1_deploy_project() {
    title "📁 部署项目"

    local project_dir=""
    local deploy_mode
    deploy_mode=$(tui_menu "项目部署" "选择部署方式：" \
        "clone" "全新安装 — 从 GitHub 克隆项目" \
        "local" "使用本地已有项目目录") || deploy_mode="clone"

    if [[ "$deploy_mode" == "clone" ]]; then
        local default_dir="/root/mybot"
        project_dir=$(tui_input "项目目录" "安装到哪个目录？" "$default_dir")
        if [ -d "$project_dir/.git" ]; then
            if tui_yesno "目录已存在" "目录 $project_dir 已有项目，是否更新？"; then
                info "正在更新项目..."
                cd "$project_dir" && git pull
            fi
        else
            info "正在克隆项目..."
            git clone "$GIT_REPO" "$project_dir"
            if [ $? -ne 0 ]; then
                err "克隆失败，请检查网络或仓库地址"
                read -p "按回车继续..."
                return 1
            fi
            ok "项目已克隆到 $project_dir"
        fi
    else
        project_dir=$(tui_input "项目路径" "输入已有项目目录的完整路径" "/root/mybot2")
        while [ ! -f "$project_dir/main.py" ]; do
            tui_msg "路径错误" "目录中未找到 main.py，请确认路径正确"
            project_dir=$(tui_input "项目路径" "输入已有项目目录的完整路径" "$project_dir")
        done
        ok "检测到有效项目: $project_dir"
    fi

    # 进入项目目录
    cd "$project_dir"

    # 安装 Python 依赖
    info "安装 Python 项目依赖..."
    pip3 install -q websocket-client requests flask
    ok "Python 依赖安装完成"

    # 读取 NapCat 配置信息（如果之前部署过）
    local instance_count=0
    if [ -f /tmp/napbot_instance_1.sh ]; then
        source /tmp/napbot_instance_1.sh 2>/dev/null
        [ -f /tmp/napbot_instance_2.sh ] && source /tmp/napbot_instance_2.sh 2>/dev/null && instance_count=2 || instance_count=1
    fi

    # 配置向导
    title "⚙️  配置向导"
    info "请填写机器人配置（以下信息将写入 config.json）"

    local bot_name master_qq bot_qq
    local http_url="http://127.0.0.1:3000"
    local ws_url="ws://127.0.0.1:3001/?access_token="
    local access_token=""

    if [ $instance_count -gt 0 ]; then
        # 使用 NapCat 部署时的配置
        local bot_name_default=""
        local bot_qq_default="${NAPCAT_QQ[1]:-}"
        local http_default="${NAPCAT_HTTP[1]:-$http_url}"
        local ws_default="${NAPCAT_WS[1]:-$ws_url}"
        local token_default="${NAPCAT_TOKEN[1]:-}"

        bot_name=$(tui_input "机器人名称" "输入机器人昵称" "${bot_name_default:-Bot}")
        bot_qq=$(tui_input "机器人 QQ" "输入机器人 QQ 号" "$bot_qq_default")
        master_qq=$(tui_input "主人 QQ" "输入主人 QQ 号（可多个，逗号分隔）" "")

        if [ $instance_count -ge 2 ]; then
            tui_msg "多实例" "检测到双 NapCat 实例。\n\n实例1 QQ: ${NAPCAT_QQ[1]}\n实例2 QQ: ${NAPCAT_QQ[2]}\n\n需分别为每个实例创建项目目录。\n\n继续配置实例1..."
        fi

        http_url=$(tui_input "HTTP 地址" "NapCat HTTP API 地址" "$http_default")
        ws_url=$(tui_input "WS 地址" "NapCat WebSocket 地址" "$ws_default")
        access_token=$(tui_input "Token" "NapCat HTTP Token" "$token_default")
    else
        # 手动配置
        bot_name=$(tui_input "机器人名称" "输入机器人昵称（如 羽笙、依星）" "Bot")
        bot_qq=$(tui_input "机器人 QQ" "输入机器人 QQ 号" "")
        master_qq=$(tui_input "主人 QQ" "输入主人 QQ 号" "")
        http_url=$(tui_input "HTTP 地址" "NapCat HTTP API 地址" "http://127.0.0.1:3000")
        ws_url=$(tui_input "WS 地址" "NapCat WebSocket 地址（含 token）" "ws://127.0.0.1:3001/?access_token=")
        access_token=$(tui_input "Token" "NapCat HTTP Token" "")
    fi

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
  "_note": "${bot_name} 机器人主配置",
  "BOT_NAME": "${bot_name}",
  "MASTER_QQ": ${master_qq_list},
  "BOT_QQ": ${bot_qq},
  "NAPCAT_HTTP": "${http_url}",
  "ACCESS_TOKEN": "${access_token}",
  "WS_URL": "${ws_url}"
}
EOF
    ok "config.json 已生成"

    # 初始化 wordlib_config.json 如果不存在
    if [ ! -f "$project_dir/data/wordlib_config.json" ]; then
        mkdir -p "$project_dir/data"
        cat > "$project_dir/data/wordlib_config.json" <<-EOF
{
  "_note": "词库插件配置：commands=触发命令，settings=功能参数，messages=回复模板，admins=管理员QQ",
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
  "settings": {
    "enabled": true,
    "favor_add_max": 3,
    "favor_minus_max": 2,
    "nickname_need_favor": 10,
    "rank_top_n": 10,
    "praise_count": 10,
    "encode_timeout": 300
  },
  "admins": []
}
EOF
        ok "wordlib_config.json 已初始化"
    fi

    # 创建 bot 管理脚本链接
    if [ -f "$project_dir/bot" ]; then
        cp "$project_dir/bot" /usr/local/bin/bot 2>/dev/null
        chmod +x /usr/local/bin/bot
        ok "bot 管理脚本已部署到 /usr/local/bin/bot"
    fi

    sep
    ok "项目部署完成 ✅"
    info "项目目录: $project_dir"
    info "管理命令: bot start/stop/restart/status"
    info "下一步: 在「运行管理」中启动 NapCat → 扫码登录 → 启动 Bot"
    read -p "按回车继续..."
}

# 5. 创建软链
page1_post_setup() {
    title "🔗 后续设置"

    # 创建 napbot 软链
    tui_yesno "管理命令" "是否将 napbot 命令安装到系统（ln -s install.sh → /usr/local/bin/napbot）？" && {
        ln -sf "$SCRIPT_PATH" /usr/local/bin/napbot 2>/dev/null
        ok "已创建 napbot 命令，直接执行 napbot 即可打开管理菜单"
    } || info "跳过"

    # systemd 服务
    if tui_yesno "Web面板" "是否为 Web 管理面板配置 systemd 服务（开机自启）？"; then
        local web_dir
        web_dir=$(dirname "$SCRIPT_PATH")
        cat > /etc/systemd/system/mybot-api.service <<-EOF
[Unit]
Description=MyBot Web Panel API
After=network.target

[Service]
Type=simple
WorkingDirectory=${web_dir}
ExecStart=/usr/bin/python3 ${web_dir}/web/api.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
        systemctl daemon-reload
        systemctl enable mybot-api.service 2>/dev/null
        info "mybot-api.service 已配置，可用以下命令管理："
        echo "  systemctl start/stop/restart mybot-api"
        echo "  systemctl status mybot-api"
    fi

    # 后续指引
    tui_msg "后续步骤" "✅ 安装部署完成！\n\n建议操作顺序：\n1. 启动 NapCat 容器 → 2. 扫码登录 QQ → 3. 启动 Bot\n\n这些操作都可以在「运行管理」页面中完成。\n\n管理命令：\n- napbot（交互菜单）\n- bot start/stop/restart/status（快速管理 bot）\n- systemctl start/stop/status mybot-api（Web 面板）"
}

# ───────────────────────── 页面一：主流程 ─────────────────────────

page1_deploy_menu() {
    while true; do
        local choice
        choice=$(tui_menu "📦 部署与配置" \
            "选择要执行的操作：" \
            "1" "🔍 环境检测" \
            "2" "📦 安装依赖" \
            "3" "🐱 部署 NapCat" \
            "4" "📁 部署项目" \
            "5" "🔗 后续设置" \
            "R" "🔙 返回主菜单") || { return; }

        case "$choice" in
            1) page1_env_check ;;
            2) page1_install_deps ;;
            3) page1_deploy_napcat ;;
            4) page1_deploy_project ;;
            5) page1_post_setup ;;
            R|*) return ;;
        esac
    done
}

# ───────────────────────── 页面二：运行管理 ─────────────────────────

# NapCat 管理
page2_napcat_menu() {
    while true; do
        # 获取容器状态
        local containers=$(docker ps -a --format "{{.Names}} ({{.Status}})" 2>/dev/null | grep -E "napcat|napcat2" || echo "暂无 NapCat 容器")
        local choice
        choice=$(tui_menu "🐱 NapCat 管理" \
            "容器列表：\n$(docker ps -a --format '{{.Names}}: {{.Status}}' 2>/dev/null | grep -E 'napcat|napcat2' || echo '(无)')\n\n选择操作：" \
            "1" "查看容器状态" \
            "2" "启动 NapCat" \
            "3" "停止 NapCat" \
            "4" "重启 NapCat" \
            "5" "查看二维码（扫码登录）" \
            "6" "查看登录状态" \
            "7" "查看容器日志" \
            "R" "🔙 返回") || { return; }

        case "$choice" in
            1)
                title "NapCat 状态"
                docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null | grep -E "napcat|NAMES" || echo "暂无容器"
                read -p "按回车继续..."
                ;;
            2)
                local container
                container=$(tui_menu "启动容器" "选择要启动的容器：" \
                    "napcat" "依星 NapCat" \
                    "napcat2" "羽笙 NapCat" \
                    "all" "启动所有") || container=""
                if [[ "$container" == "all" ]]; then
                    docker start napcat napcat2 2>/dev/null; ok "已发送启动指令"
                elif [[ -n "$container" ]]; then
                    docker start "$container" 2>/dev/null && ok "$container 已启动" || err "启动失败"
                fi
                read -p "按回车继续..."
                ;;
            3)
                local container
                container=$(tui_menu "停止容器" "选择要停止的容器：" \
                    "napcat" "依星 NapCat" \
                    "napcat2" "羽笙 NapCat" \
                    "all" "停止所有") || container=""
                if [[ "$container" == "all" ]]; then
                    docker stop napcat napcat2 2>/dev/null; ok "已发送停止指令"
                elif [[ -n "$container" ]]; then
                    docker stop "$container" 2>/dev/null && ok "$container 已停止" || err "停止失败"
                fi
                read -p "按回车继续..."
                ;;
            4)
                local container
                container=$(tui_menu "重启容器" "选择要重启的容器：" \
                    "napcat" "依星 NapCat" \
                    "napcat2" "羽笙 NapCat" \
                    "all" "重启所有") || container=""
                if [[ "$container" == "all" ]]; then
                    docker restart napcat napcat2 2>/dev/null; ok "已发送重启指令"
                elif [[ -n "$container" ]]; then
                    docker restart "$container" 2>/dev/null && ok "$container 已重启" || err "重启失败"
                fi
                read -p "按回车继续..."
                ;;
            5)
                title "📱 NapCat 二维码"
                local container
                container=$(tui_menu "查看二维码" "选择容器：" \
                    "napcat" "依星 NapCat" \
                    "napcat2" "羽笙 NapCat") || container=""
                if [[ -n "$container" ]]; then
                    info "正在获取 $container 的登录二维码..."
                    local qr_file="/tmp/napcat_qr_${container}.png"
                    # 尝试从容器中导出二维码
                    docker exec "$container" cat /app/napcat/cache/qrcode.png 2>/dev/null > "$qr_file"
                    if [ -s "$qr_file" ]; then
                        info "二维码已保存到 $qr_file"
                        # 尝试用终端显示（如安装了 img2txt 或 chafa）
                        if command -v chafa &>/dev/null; then
                            chafa "$qr_file" 2>/dev/null
                        elif command -v img2txt &>/dev/null; then
                            img2txt "$qr_file" 2>/dev/null
                        else
                            echo "  ⚠ 当前终端无法显示图片"
                            echo "  可打开 NapCat WebUI 查看:"
                            echo "    ${container/napcat/} → 浏览器访问 http://<服务器IP>:6099"
                            echo "    napcat2 → http://<服务器IP>:6100"
                            echo "  或使用 Web 面板查看二维码"
                        fi
                        # 检查登录状态
                        echo
                        docker logs "$container" --tail 20 2>&1 | grep -i "登录\|qrcode\|success\|失败" || true
                    else
                        err "未找到二维码，NapCat 可能正在启动或无需扫码"
                        info "查看最近日志："
                        docker logs "$container" --tail 10 2>&1
                    fi
                fi
                read -p "按回车继续..."
                ;;
            6)
                title "登录状态"
                for c in napcat napcat2; do
                    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^$c$"; then
                        echo -n "$c: "
                        local status
                        status=$(docker logs "$c" --tail 5 2>&1 | grep -c "登录\|success\|online\|失败\|断开" || true)
                        if [ "$status" -gt 0 ]; then
                            docker logs "$c" --tail 5 2>&1 | grep -i "登录\|success\|online\|失败\|断开" | tail -3
                        else
                            echo "运行中（登录状态未知，查看日志确认）"
                        fi
                    fi
                done
                read -p "按回车继续..."
                ;;
            7)
                local container
                container=$(tui_menu "查看日志" "选择容器：" \
                    "napcat" "依星 NapCat" \
                    "napcat2" "羽笙 NapCat") || container=""
                if [[ -n "$container" ]]; then
                    local lines
                    lines=$(tui_input "行数" "显示最近多少行？" "50")
                    echo; docker logs "$container" --tail "$lines" 2>&1
                    echo; read -p "按回车继续..."
                fi
                ;;
            R|*) return ;;
        esac
    done
}

# Bot 管理
page2_bot_menu() {
    while true; do
        # 检测 bot 命令是否存在
        local bot_cmd="bot"
        command -v bot &>/dev/null || bot_cmd=""

        local choice
        choice=$(tui_menu "🤖 Bot 管理" \
            "选择操作：" \
            "1" "📊 查看所有 Bot 状态" \
            "2" "▶️  启动 Bot" \
            "3" "⏹  停止 Bot" \
            "4" "🔄 重启 Bot" \
            "5" "📋 查看 Bot 日志" \
            "R" "🔙 返回") || { return; }

        case "$choice" in
            1)
                if command -v bot &>/dev/null; then
                    bot status
                else
                    # 手动检测
                    for sn in bot bot2; do
                        if screen -list 2>/dev/null | grep -q "[0-9]*\.$sn"; then
                            ok "$sn: 运行中"
                        else
                            err "$sn: 未运行"
                        fi
                    done
                fi
                read -p "按回车继续..."
                ;;
            2|3|4)
                local action=""; local action_name=""
                case "$choice" in 2) action="start"; action_name="启动";; 3) action="stop"; action_name="停止";; 4) action="restart"; action_name="重启";; esac

                if ! command -v bot &>/dev/null; then
                    warn "bot 命令不可用，请先在部署页面配置"
                    read -p "按回车继续..."
                    continue
                fi
                local target
                target=$(tui_menu "$action_name Bot" \
                    "选择要${action_name}的 Bot：" \
                    "1" "依星 (bot1)" \
                    "2" "羽笙 (bot2)" \
                    "all" "全部") || target=""
                if [[ "$target" == "all" ]]; then
                    for n in 1 2; do bot $action $n 2>/dev/null; done
                elif [[ -n "$target" ]]; then
                    bot $action $target
                fi
                read -p "按回车继续..."
                ;;
            5)
                if ! command -v bot &>/dev/null; then
                    warn "bot 命令不可用"
                    read -p "按回车继续..."
                    continue
                fi
                local target
                target=$(tui_menu "查看日志" "选择 Bot：" \
                    "runtime" "查看 runtime.log" \
                    "screen" "查看 Screen 日志") || target=""
                if [[ "$target" == "runtime" ]]; then
                    local dirs=("/root/mybot" "/root/mybot2")
                    for d in "${dirs[@]}"; do
                        if [ -f "$d/runtime.log" ]; then
                            echo; info "=== $(basename $d)/runtime.log ==="
                            tail -30 "$d/runtime.log"
                        fi
                    done
                elif [[ "$target" == "screen" ]]; then
                    for sn in bot bot2; do
                        local tmpf="/tmp/${sn}_log.txt"
                        screen -S "$sn" -X hardcopy "$tmpf" 2>/dev/null
                        [ -f "$tmpf" ] && echo "=== $sn ===" && tail -20 "$tmpf" && rm -f "$tmpf"
                    done
                fi
                read -p "按回车继续..."
                ;;
            R|*) return ;;
        esac
    done
}

# 日志查看
page2_log_menu() {
    while true; do
        local choice
        choice=$(tui_menu "📋 日志查看" \
            "选择查看：" \
            "1" "🐱 NapCat 容器日志" \
            "2" "🤖 Bot 运行日志 (runtime.log)" \
            "3" "🌐 Web 面板日志" \
            "4" "📡 实时跟踪 (tail -f)" \
            "R" "🔙 返回") || { return; }

        case "$choice" in
            1)
                local container
                container=$(tui_menu "选择容器" "选择 NapCat 容器：" \
                    "napcat" "依星 NapCat" \
                    "napcat2" "羽笙 NapCat") || container=""
                if [[ -n "$container" ]]; then
                    local lines
                    lines=$(tui_input "行数" "显示最近多少行？" "50")
                    echo; docker logs "$container" --tail "$lines" 2>&1
                    echo; read -p "按回车继续..."
                fi
                ;;
            2)
                local dirs=("/root/mybot" "/root/mybot2")
                local found=false
                for d in "${dirs[@]}"; do
                    if [ -f "$d/runtime.log" ]; then
                        found=true
                        local name=$(basename "$d")
                        local lines
                        lines=$(tui_input "行数" "显示 $name runtime.log 最近多少行？" "50")
                        echo; info "=== $name/runtime.log ==="
                        tail -"$lines" "$d/runtime.log" 2>/dev/null
                        echo
                    fi
                done
                $found || err "未找到 runtime.log"
                read -p "按回车继续..."
                ;;
            3)
                local web_log="/root/mybot2/runtime.log"
                [ -f "$web_log" ] && tail -30 "$web_log" || warn "未找到 Web 面板日志"
                read -p "按回车继续..."
                ;;
            4)
                local target
                target=$(tui_menu "实时跟踪" "选择跟踪目标：" \
                    "napcat" "NapCat 容器日志" \
                    "napcat2" "NapCat2 容器日志" \
                    "bot" "依星 runtime.log" \
                    "bot2" "羽笙 runtime.log") || target=""
                case "$target" in
                    napcat|napcat2) info "实时跟踪 $target （按 Ctrl+C 退出）"; sleep 1; docker logs -f "$target" 2>&1 ;;
                    bot) [ -f /root/mybot/runtime.log ] && tail -f /root/mybot/runtime.log || err "文件不存在" ;;
                    bot2) [ -f /root/mybot2/runtime.log ] && tail -f /root/mybot2/runtime.log || err "文件不存在" ;;
                esac
                ;;
            R|*) return ;;
        esac
    done
}

# Web 面板管理
page2_web_menu() {
    while true; do
        local choice
        choice=$(tui_menu "🌐 Web 面板管理" \
            "选择操作：" \
            "1" "📊 查看面板状态" \
            "2" "▶️  启动面板" \
            "3" "⏹  停止面板" \
            "4" "🔄 重启面板" \
            "R" "🔙 返回") || { return; }

        case "$choice" in
            1)
                if systemctl is-active mybot-api &>/dev/null 2>&1; then
                    ok "systemd 服务: mybot-api 运行中"
                    systemctl status mybot-api --no-pager -l 2>&1 | head -10
                elif screen -list 2>/dev/null | grep -q "[0-9]*\.webpanel"; then
                    ok "screen 会话: webpanel 运行中"
                else
                    err "Web 面板未运行"
                fi
                read -p "按回车继续..."
                ;;
            2)
                if systemctl list-units --type=service 2>/dev/null | grep -q mybot-api; then
                    systemctl start mybot-api && ok "已启动 mybot-api.service"
                else
                    local web_dir="/root/mybot2"
                    screen -S webpanel -X quit 2>/dev/null; sleep 0.5
                    cd "$web_dir" && screen -dmS webpanel python3 web/api.py
                    sleep 1
                    screen -list | grep -q "webpanel" && ok "Web 面板已启动（screen: webpanel）" || err "启动失败"
                fi
                read -p "按回车继续..."
                ;;
            3)
                if systemctl is-active mybot-api &>/dev/null 2>&1; then
                    systemctl stop mybot-api && ok "已停止 mybot-api.service"
                fi
                screen -S webpanel -X quit 2>/dev/null && ok "已停止 screen webpanel" || true
                read -p "按回车继续..."
                ;;
            4)
                info "正在重启 Web 面板..."
                if systemctl list-units --type=service 2>/dev/null | grep -q mybot-api; then
                    systemctl restart mybot-api && ok "mybot-api.service 已重启" || err "重启失败"
                else
                    screen -S webpanel -X quit 2>/dev/null; sleep 0.5
                    local web_dir="/root/mybot2"
                    cd "$web_dir" && screen -dmS webpanel python3 web/api.py
                    sleep 1
                    screen -list | grep -q "webpanel" && ok "Web 面板已重启（screen: webpanel）" || err "重启失败"
                fi
                read -p "按回车继续..."
                ;;
            R|*) return ;;
        esac
    done
}

# 页面二：主流程
page2_manage_menu() {
    while true; do
        local choice
        choice=$(tui_menu "🛠  运行管理" \
            "选择管理模块：" \
            "1" "🐱 NapCat 管理" \
            "2" "🤖 Bot 管理" \
            "3" "📋 日志查看" \
            "4" "🌐 Web 面板管理" \
            "R" "🔙 返回主菜单") || { return; }

        case "$choice" in
            1) page2_napcat_menu ;;
            2) page2_bot_menu ;;
            3) page2_log_menu ;;
            4) page2_web_menu ;;
            R|*) return ;;
        esac
    done
}

# ───────────────────────── 主菜单 ─────────────────────────

main_menu() {
    while true; do
        local choice
        choice=$(tui_menu "NapCat WordLib Bot v$SCRIPT_VERSION" \
            "欢迎使用一键安装部署脚本！\n选择功能页面：" \
            "1" "📦 部署与配置 — 环境检测/安装依赖/部署NapCat/部署项目" \
            "2" "🛠  运行管理 — NapCat管理/Bot管理/日志/Web面板" \
            "Q" "🚪 退出") || { clear; exit 0; }

        case "$choice" in
            1) page1_deploy_menu ;;
            2) page2_manage_menu ;;
            Q|q|"") clear; echo "bye~"; exit 0 ;;
        esac
    done
}

# ───────────────────────── 入口 ─────────────────────────
check_root
clear

# 显示欢迎页
tui_infobox "NapCat WordLib Bot v$SCRIPT_VERSION" \
    "🤖 NapCat WordLib Bot — 一键安装部署脚本\n\
仓库: https://github.com/Bdlxx/NapCat-WordLibBot\n\n\
功能页面：\n\
  1. 部署与配置 — 环境检测/安装依赖/部署NapCat/部署项目\n\
  2. 运行管理 — NapCat管理/Bot管理/日志/Web面板\n\n\
加载中..."

sleep 0.5

main_menu

# ===============================================================
# NapCat WordLib Bot — Windows 一键安装部署 & 管理脚本 (PowerShell)
# 仓库: https://github.com/Bdlxx/NapCat-WordLibBot
# 用法: 右键「使用 PowerShell 运行」，或  powershell -ExecutionPolicy Bypass -File install.ps1
# 依赖: Docker Desktop、Git、Python 3.10+
# ===============================================================
#requires -Version 5.1

$SCRIPT_NAME  = "NapCat-WordLibBot"
$SCRIPT_VERSION = "1.1.0"
$NAPCAT_IMAGE = "docker.xuanyuan.me/mlikiowa/napcat-docker:latest"
$GIT_REPO     = "https://github.com/Bdlxx/NapCat-WordLibBot.git"
$PLUGIN_REPO  = "https://github.com/Bdlxx/NapCat-WordLibBot-Plugins.git"

# ── 目录（与 Linux 版保持一致：实例统一放脚本目录下 instances/<QQ>）──
$BASE_DIR         = $PSScriptRoot
$TEMPLATES_DIR    = Join-Path $BASE_DIR "templates"
$INSTANCES_ROOT   = Join-Path $BASE_DIR "instances"
$INSTANCES_DIR    = Join-Path $INSTANCES_ROOT "registry"
$NAPBOT_HOME      = Join-Path $HOME "napbot"
$NAPCAT_ROOT      = Join-Path $BASE_DIR "napcat_data"   # NapCat 容器配置/缓存（Windows 卷映射用）

# ── 颜色输出 ──
function Write-Ok   { Write-Host "✓ $args" -ForegroundColor Green }
function Write-Err  { Write-Host "✗ $args" -ForegroundColor Red }
function Write-Info { Write-Host "ℹ $args" -ForegroundColor Cyan }
function Write-Warn { Write-Host "⚠ $args" -ForegroundColor Yellow }
function Title      { Write-Host "`n===== $args =====" -ForegroundColor Blue }
function Pause-Msg  { Read-Host "按回车继续..." }

New-Item -ItemType Directory -Force -Path $INSTANCES_DIR, $NAPCAT_ROOT | Out-Null

# ═══════════════════════ 工具函数 ═══════════════════════

function Test-Deps {
    $ok = $true
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Write-Err "未安装 Docker Desktop"; $ok = $false }
    if (-not (Get-Command git    -ErrorAction SilentlyContinue)) { Write-Err "未安装 Git"; $ok = $false }
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) { Write-Err "未安装 Python (python 需在 PATH)"; $ok = $false }
    return $ok
}

function Gen-Token([int]$len = 16) {
    $chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789~!@#$%^&*'
    -join (1..$len | ForEach-Object { $chars[(Get-Random -Maximum $chars.Length)] })
}

function Get-Instances {
    # 返回实例 QQ 列表（注册文件 + instances/<QQ> 目录 + docker 容器）
    $qqs = @()
    if (Test-Path $INSTANCES_DIR) {
        Get-ChildItem $INSTANCES_DIR -Filter *.sh -ErrorAction SilentlyContinue | ForEach-Object {
            $q = $_.BaseName
            if ($q -match '^\d+$' -and $qqs -notcontains $q) { $qqs += $q }
        }
    }
    Get-ChildItem $INSTANCES_ROOT -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.Name -match '^\d+$' -and $qqs -notcontains $_.Name) { $qqs += $_.Name }
    }
    docker ps -a --format '{{.Names}}' 2>$null | ForEach-Object {
        if ($_ -match '^napcat_(\d+)$' -and $qqs -notcontains $Matches[1]) { $qqs += $Matches[1] }
    }
    return ($qqs | Sort-Object)
}

function Load-Instance([string]$qq) {
    # 返回实例信息 hashtable（注册文件优先，否则默认值）
    $f = Join-Path $INSTANCES_DIR "$qq.sh"
    $inst = @{
        QQ = $qq
        Container = "napcat_$qq"
        ProjectDir = Join-Path $INSTANCES_ROOT $qq
        NapDir = Join-Path $NAPCAT_ROOT $qq
        Screen = "bot_$qq"
        HTTP = "http://127.0.0.1:3000"
        WS = "ws://127.0.0.1:3001/?access_token="
        Token = ""
        BotName = "Bot_$qq"
    }
    if (Test-Path $f) {
        Get-Content $f -Encoding UTF8 | ForEach-Object {
            if ($_ -match '^\s*(INST_\w+)\s*=\s*"(.*)"\s*$') {
                switch ($Matches[1]) {
                    'INST_CONTAINER'    { $inst.Container  = $Matches[2] }
                    'INST_PROJECT_DIR'  { $inst.ProjectDir = $Matches[2] }
                    'INST_NAP_DIR'      { $inst.NapDir     = $Matches[2] }
                    'INST_SCREEN'       { $inst.Screen     = $Matches[2] }
                    'INST_HTTP'         { $inst.HTTP       = $Matches[2] }
                    'INST_WS'           { $inst.WS         = $Matches[2] }
                    'INST_TOKEN'        { $inst.Token      = $Matches[2] }
                    'INST_BOT_NAME'     { $inst.BotName    = $Matches[2] }
                }
            }
        }
    }
    return $inst
}

function Save-Instance($inst) {
    $f = Join-Path $INSTANCES_DIR "$($inst.QQ).sh"
    @"
INST_QQ="$($inst.QQ)"
INST_CONTAINER="$($inst.Container)"
INST_PROJECT_DIR="$($inst.ProjectDir)"
INST_NAP_DIR="$($inst.NapDir)"
INST_SCREEN="$($inst.Screen)"
INST_HTTP="$($inst.HTTP)"
INST_WS="$($inst.WS)"
INST_TOKEN="$($inst.Token)"
INST_BOT_NAME="$($inst.BotName)"
"@ | Set-Content $f -Encoding UTF8
}

function Bot-Running([string]$qq) {
    $pidFile = Join-Path (Join-Path $INSTANCES_ROOT $qq) "data\bot.pid"
    if (Test-Path $pidFile) {
        $procId = (Get-Content $pidFile).Trim()
        if ($procId -and (Get-Process -Id $procId -ErrorAction SilentlyContinue)) { return $true }
    }
    return $false
}

function Bot-Start($inst) {
    $dir = $inst.ProjectDir
    if (-not (Test-Path (Join-Path $dir "main.py"))) { Write-Err "项目不存在: $dir（请先部署）"; return }
    New-Item -ItemType Directory -Force -Path (Join-Path $dir "data") | Out-Null
    $outLog = Join-Path $dir "runtime.log"
    $errLog = Join-Path $dir "runtime.err.log"
    Write-Info "启动 Bot ($($inst.BotName)) ..."
    $p = Start-Process python -ArgumentList "main.py --bot-name `"$($inst.BotName)`" --bot-qq $($inst.QQ)" `
        -WorkingDirectory $dir -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
    Set-Content (Join-Path $dir "data\bot.pid") $p.Id
    Write-Ok "Bot 已启动 (PID $($p.Id))，日志: $outLog"
}

function Bot-Stop([string]$qq) {
    $pidFile = Join-Path (Join-Path $INSTANCES_ROOT $qq) "data\bot.pid"
    if (Test-Path $pidFile) {
        $procId = (Get-Content $pidFile).Trim()
        if ($procId) { Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue; Write-Ok "Bot 已停止 (PID $procId)" }
        Remove-Item $pidFile -ErrorAction SilentlyContinue
    } else {
        Write-Warn "未找到运行中的 Bot"
    }
}

function Install-Plugins([string]$projectDir) {
    $pluginsDir = Join-Path $projectDir "plugins"
    New-Item -ItemType Directory -Force -Path $pluginsDir | Out-Null
    $cache = Join-Path $env:TEMP "napbot_plugin_repo"
    Write-Info "从插件仓库获取插件: $PLUGIN_REPO"
    if (Test-Path (Join-Path $cache ".git")) {
        Push-Location $cache; git pull --quiet 2>$null; Pop-Location
    } else {
        git clone --depth 1 $PLUGIN_REPO $cache 2>$null
        if (-not (Test-Path (Join-Path $cache ".git"))) { Write-Err "插件仓库克隆失败"; return }
    }
    $count = 0
    Get-ChildItem $cache -Filter *.py | ForEach-Object {
        Copy-Item $_.FullName $pluginsDir -Force
        $count++
    }
    Write-Ok "插件已安装 ($count 个)，重启 Bot 后生效"
}

# ═══════════════════════ 部署新实例 ═══════════════════════

function Deploy-NewInstance {
    Title "📦 部署新实例"
    if (-not (Test-Deps)) { Pause-Msg; return }

    $qq = Read-Host "请输入机器人 QQ 号作为实例标识"
    while ($qq -notmatch '^\d+$') { $qq = Read-Host "QQ 号必须为纯数字" }

    $inst = Load-Instance $qq
    $projectDir = $inst.ProjectDir

    # 1. 克隆项目
    if (Test-Path (Join-Path $projectDir ".git")) {
        Write-Info "项目已存在，git pull 更新..."
        Push-Location $projectDir; git pull; Pop-Location
    } else {
        New-Item -ItemType Directory -Force -Path (Split-Path $projectDir) | Out-Null
        Write-Info "克隆项目到 $projectDir ..."
        git clone $GIT_REPO $projectDir
        if (-not (Test-Path (Join-Path $projectDir "main.py"))) { Write-Err "克隆失败"; Pause-Msg; return }
        Write-Ok "项目已克隆"
    }

    # 2. 拉取插件
    Install-Plugins $projectDir

    # 2.1 安装 Python 依赖（Bot + Web 面板基础依赖）
    Write-Info "安装 Python 依赖 (websocket-client/requests/flask)..."
    pip install --quiet websocket-client requests flask 2>$null
    Write-Ok "Python 依赖已安装"

    # 2.2 可选：JM 插件依赖（venv + jmcomic，仅使用 JM 下载功能时需要）
    $ans = Read-Host "是否安装 JM下载插件依赖（venv + jmcomic，约几十MB）？[y/N]"
    if ($ans -eq 'y' -or $ans -eq 'Y') {
        $venvPy = Join-Path $projectDir "venv\Scripts\python.exe"
        if (-not (Test-Path $venvPy)) {
            Write-Info "创建 venv ..."
            python -m venv (Join-Path $projectDir "venv")
        }
        & $venvPy -m pip install --quiet jmcomic img2pdf 2>$null
        Write-Ok "JM 插件依赖已安装"
    }

    # 3. 配置 NapCat
    $napDir  = $inst.NapDir
    $cfgDir  = Join-Path $napDir "config"
    $cacheDir = Join-Path $napDir "cache\images"
    New-Item -ItemType Directory -Force -Path $cfgDir, $cacheDir | Out-Null

    $httpPort = 3000; $wsPort = 3001; $webuiPort = 6099
    $nm = Read-Host "网络模式 [bridge/host]（默认 bridge）"
    if ($nm -eq "host") {
        Write-Warn "Host 模式（需 Docker Desktop 支持），端口直通"
    } else {
        $p1 = Read-Host "HTTP API 端口（默认 $httpPort）"; if ($p1 -match '^\d+$') { $httpPort = [int]$p1 }
        $p2 = Read-Host "WebSocket 端口（默认 $wsPort）";   if ($p2 -match '^\d+$') { $wsPort   = [int]$p2 }
        $p3 = Read-Host "NapCat WebUI 端口（默认 $webuiPort）"; if ($p3 -match '^\d+$') { $webuiPort = [int]$p3 }
    }

    $httpToken = Gen-Token; $wsToken = Gen-Token
    $hostVal = if ($nm -eq "host") { "127.0.0.1" } else { "0.0.0.0" }

    # 写入 NapCat 配置（模板占位符替换）
    $tpl = Get-Content (Join-Path $TEMPLATES_DIR "napcat-onebot.json") -Raw -Encoding UTF8
    $tpl = $tpl.Replace("__HTTP_PORT__", "$httpPort").Replace("__WS_PORT__", "$wsPort") `
               .Replace("__HTTP_TOKEN__", $httpToken).Replace("__WS_TOKEN__", $wsToken) `
               .Replace("__HOST__", $hostVal)
    $tpl | Set-Content (Join-Path $cfgDir "onebot11_$qq.json") -Encoding UTF8
    Copy-Item (Join-Path $TEMPLATES_DIR "napcat.json") (Join-Path $cfgDir "napcat.json") -Force
    Write-Ok "NapCat 配置已写入 $cfgDir"

    # 4. 创建容器
    $cname = $inst.Container
    docker stop $cname 2>$null | Out-Null; docker rm $cname 2>$null | Out-Null
    $cmd = @("run","-d","--name",$cname,"--restart","unless-stopped")
    if ($nm -eq "host") {
        $cmd += @("--network","host")
    } else {
        $cmd += @("-p","127.0.0.1:${httpPort}:3000","-p","127.0.0.1:${wsPort}:3001","-p","127.0.0.1:${webuiPort}:6099")
    }
    $cmd += @("-v","$cfgDir:/app/napcat/config","-v","$cacheDir:/app/cache/images",$NAPCAT_IMAGE)
    Write-Info "执行: docker $($cmd -join ' ')"
    & docker @cmd
    if ($LASTEXITCODE -eq 0) { Write-Ok "容器 $cname 创建成功" } else { Write-Err "容器创建失败"; Pause-Msg; return }

    # 5. 保存实例信息
    $inst.Container = $cname
    $inst.NapDir    = $napDir
    $inst.HTTP      = "http://127.0.0.1:$httpPort"
    $inst.WS        = "ws://127.0.0.1:$wsPort/?access_token=$wsToken"
    $inst.Token     = $wsToken
    Save-Instance $inst
    Write-Ok "实例 $qq 部署完成！"
    Write-Host ""
    Write-Info "下一步：启动容器后扫码登录（实例管理 → 查看二维码）"
    Write-Info "然后启动 Bot（实例管理 → Bot 启动）"
    Pause-Msg
}

# ═══════════════════════ 实例管理 ═══════════════════════

function Manage-Instances {
    while ($true) {
        Title "🗂 实例管理"
        $qqs = Get-Instances
        if ($qqs.Count -eq 0) { Write-Warn "暂无实例，请先部署"; Pause-Msg; return }
        for ($i = 0; $i -lt $qqs.Count; $i++) {
            $q = $qqs[$i]
            $cst = (docker ps -a --format '{{.Names}} {{.Status}}' 2>$null | Select-String "^napcat_$q ") -replace '^napcat_\d+ ',''
            $bst = if (Bot-Running $q) { "● 运行中" } else { "○ 已停止" }
            Write-Host "  $($i+1). QQ:$q  [容器: $cst]  [Bot: $bst]"
        }
        Write-Host "  R. 返回主菜单"
        $sel = Read-Host "选择实例"
        if ($sel -eq 'R' -or $sel -eq 'r') { return }
        $idx = [int]$sel - 1
        if ($idx -ge 0 -and $idx -lt $qqs.Count) { Instance-Action $qqs[$idx] }
    }
}

function Instance-Action([string]$qq) {
    $inst = Load-Instance $qq
    while ($true) {
        Title "实例 $qq ($($inst.BotName))"
        $cst = (docker ps -a --format '{{.Names}} {{.Status}}' 2>$null | Select-String "^napcat_$qq ") -replace '^napcat_\d+ ',''
        $bst = if (Bot-Running $qq) { "● 运行中" } else { "○ 已停止" }
        Write-Host "  容器: $cst    Bot: $bst"
        Write-Host ""
        Write-Host "  1. ▶ 启动 NapCat 容器"
        Write-Host "  2. ⏹ 停止 NapCat 容器"
        Write-Host "  3. 📱 查看二维码（扫码登录）"
        Write-Host "  4. 🤖 启动 Bot"
        Write-Host "  5. ⏹ 停止 Bot"
        Write-Host "  6. 🔄 更新插件（从插件仓库拉取）"
        Write-Host "  7. 📋 查看 Bot 日志"
        Write-Host "  8. 🚀 启动 Web 管理面板"
        Write-Host "  9. ❌ 卸载实例"
        Write-Host "  R. 返回实例列表"
        $sel = Read-Host "选择操作"
        switch ($sel) {
            '1' { docker start "napcat_$qq"; Write-Ok "容器已启动"; Pause-Msg }
            '2' { docker stop "napcat_$qq"; Write-Ok "容器已停止"; Pause-Msg }
            '3' {
                $qrPath = Join-Path $env:TEMP "napcat_${qq}_qrcode.png"
                docker cp "napcat_$qq`:/app/napcat/cache/qrcode.png" $qrPath 2>$null
                if (Test-Path $qrPath) {
                    Write-Ok "二维码已保存，正在打开（用手机 QQ 扫码，约 2-3 分钟有效）"
                    Invoke-Item $qrPath
                } else {
                    Write-Warn "未找到二维码（容器未运行、未生成或已登录）"
                }
                Pause-Msg
            }
            '4' { Bot-Start $inst; Pause-Msg }
            '5' { Bot-Stop $qq; Pause-Msg }
            '6' { Install-Plugins $inst.ProjectDir; Pause-Msg }
            '7' {
                $log = Join-Path $inst.ProjectDir "runtime.log"
                if (Test-Path $log) { Get-Content $log -Tail 30 } else { Write-Warn "暂无日志" }
                Pause-Msg
            }
            '8' {
                $webDir = Join-Path $inst.ProjectDir "web"
                if (Test-Path $webDir) {
                    $p = Start-Process python -ArgumentList "web/api.py --bot-dir `"$($inst.ProjectDir)`" --bot-name `"$($inst.BotName)`" --bot-qq $qq" `
                        -WorkingDirectory $inst.ProjectDir -WindowStyle Hidden -PassThru
                    Write-Ok "Web 面板已启动 (PID $($p.Id))，访问 http://127.0.0.1:8080/"
                } else { Write-Err "实例中未找到 web/ 目录" }
                Pause-Msg
            }
            '9' {
                $ans = Read-Host "确定卸载实例 $qq ？(y/N)：删除容器（保留配置目录）"
                if ($ans -eq 'y' -or $ans -eq 'Y') {
                    docker stop "napcat_$qq" 2>$null; docker rm "napcat_$qq" 2>$null
                    Remove-Item (Join-Path $INSTANCES_DIR "$qq.sh") -ErrorAction SilentlyContinue
                    Write-Ok "实例 $qq 已卸载（项目文件保留在 $($inst.ProjectDir)）"
                    Pause-Msg; return
                }
            }
            default { if ($sel -eq 'R' -or $sel -eq 'r') { return } }
        }
    }
}

# ═══════════════════════ 后续设置 ═══════════════════════

function Post-Setup {
    Title "🔧 后续设置"
    Write-Host "  1. 创建 napbot 快捷命令（将脚本复制到 $NAPBOT_HOME 并在桌面创建快捷方式）"
    Write-Host "  2. 启动 Web 管理面板（主面板，管理全部实例）"
    Write-Host "  R. 返回主菜单"
    $sel = Read-Host "选择"
    switch ($sel) {
        '1' {
            New-Item -ItemType Directory -Force -Path $NAPBOT_HOME | Out-Null
            Copy-Item $PSCommandPath (Join-Path $NAPBOT_HOME "install.ps1") -Force
            Write-Ok "脚本已保存到 $NAPBOT_HOME\install.ps1"
            Write-Info "可在桌面创建快捷方式指向: powershell -ExecutionPolicy Bypass -File `"$NAPBOT_HOME\install.ps1`""
            Pause-Msg
        }
        '2' {
            $p = Start-Process python -ArgumentList "web/api.py" -WorkingDirectory $BASE_DIR -WindowStyle Hidden -PassThru
            Write-Ok "Web 主面板已启动 (PID $($p.Id))"
            Write-Info "访问 http://127.0.0.1:8080/ （密码由 set_password.sh 配置）"
            Pause-Msg
        }
    }
}

# ═══════════════════════ 主菜单 ═══════════════════════

Clear-Host
Write-Host ""
Write-Host "  🤖 NapCat WordLib Bot v$SCRIPT_VERSION (Windows)" -ForegroundColor Cyan
Write-Host "  ==========================================" -ForegroundColor DarkGray

while ($true) {
    Write-Host ""
    Write-Host "  1. 📦 部署新实例" -ForegroundColor White
    Write-Host "  2. 🗂 实例管理" -ForegroundColor White
    Write-Host "  3. 🔧 后续设置" -ForegroundColor White
    Write-Host "  Q. 退出" -ForegroundColor White
    $sel = Read-Host "`n请选择"
    switch ($sel) {
        '1' { Deploy-NewInstance }
        '2' { Manage-Instances }
        '3' { Post-Setup }
        default { if ($sel -eq 'Q' -or $sel -eq 'q') { Write-Host "bye~"; exit 0 } }
    }
}

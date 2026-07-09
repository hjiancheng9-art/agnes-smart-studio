<#
╔══════════════════════════════════════════════════════════════╗
║  新烬龙V2 · 启动器 v3.0                                     ║
║  New Jinlong Flow Studio V2 · Cockpit Launcher              ║
║                                                              ║
║  用法: .\launcher.ps1                                        ║
║        .\launcher.ps1 -Mode cockpit    # 启动驾驶舱          ║
║        .\launcher.ps1 -Mode dashboard  # 启动控制台          ║
║        .\launcher.ps1 -Mode info       # 显示系统信息        ║
╚══════════════════════════════════════════════════════════════╝
#>

param(
    [ValidateSet("cockpit", "dashboard", "info", "help")]
    [string]$Mode = ""
)

# ══════════════════════ CONSTANTS ══════════════════════
$ROOT         = "C:\Users\huangjiancheng\CodeBuddy\新烬龙V2"
$WORKSPACE    = "$ROOT\artifacts\product-core-baseline\baseline-files"
$PUBLIC       = "$WORKSPACE\public"
$CONFIG_PATH  = "$ROOT\config\cli-config.json"
$DATA_DIR     = "$ROOT\data\cockpit-projects"
$PORT         = 4366
$DASH_PORT    = 4377

# ══════════════════════ SYSTEM SCAN ══════════════════════
function Get-SystemInfo {
    $info = @{}
    
    # Node
    try { $info.NodeVersion = (node --version 2>$null).Trim() } catch { $info.NodeVersion = "not found" }
    
    # NPM
    try { $info.NpmVersion = (npm --version 2>$null).Trim() } catch { $info.NpmVersion = "not found" }
    
    # Server status
    $info.ServerRunning = $false
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.ConnectAsync("127.0.0.1", $PORT).Wait(500) | Out-Null
        if ($tcp.Connected) { $info.ServerRunning = $true; $tcp.Close() }
    } catch {}

    # Dashboard status
    $info.DashboardRunning = $false
    try {
        $tcp2 = New-Object System.Net.Sockets.TcpClient
        $tcp2.ConnectAsync("127.0.0.1", $DASH_PORT).Wait(500) | Out-Null
        if ($tcp2.Connected) { $info.DashboardRunning = $true; $tcp2.Close() }
    } catch {}

    # Projects
    if (Test-Path $DATA_DIR) {
        $info.ProjectCount = (Get-ChildItem $DATA_DIR -Filter "*.json").Count
    } else { $info.ProjectCount = 0 }

    # File sizes
    $info.IndexSize = if (Test-Path "$PUBLIC\index.html") { (Get-Item "$PUBLIC\index.html").Length / 1KB } else { 0 }
    $info.ServerSize = if (Test-Path "$WORKSPACE\server.js") { (Get-Item "$WORKSPACE\server.js").Length / 1KB } else { 0 }

    # Package version
    $pkgPath = "$WORKSPACE\package.json"
    if (Test-Path $pkgPath) {
        try {
            $pkg = Get-Content $pkgPath -Raw | ConvertFrom-Json
            $info.PkgVersion = $pkg.version
        } catch { $info.PkgVersion = "0.1.0" }
    } else { $info.PkgVersion = "0.1.0" }

    # Uptime
    $info.LauncherUptime = (Get-Date) - (Get-Process -Id $pid).StartTime

    # OS
    $info.OS = (Get-CimInstance Win32_OperatingSystem).Caption

    return $info
}

# ══════════════════════ UI ══════════════════════
function Write-Header {
    param([string]$Title = "驾驶舱启动器")
    
    $info = Get-SystemInfo
    Clear-Host
    Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║  " -NoNewline; Write-Host "🔥 新烬龙V2" -ForegroundColor Yellow -NoNewline; Write-Host " · $Title" -ForegroundColor White
    Write-Host "║  New Jinlong Flow Studio · AI 视频生产引擎" -ForegroundColor DarkCyan
    Write-Host "╠══════════════════════════════════════════════════════════════╣" -ForegroundColor Cyan
    Write-Host "║  " -NoNewline; Write-Host "Node" -ForegroundColor Green -NoNewline
    Write-Host " $($info.NodeVersion)  │  " -NoNewline
    Write-Host "NPM" -ForegroundColor Green -NoNewline
    Write-Host " $($info.NpmVersion)  │  " -NoNewline
    Write-Host "版本" -ForegroundColor Green -NoNewline
    Write-Host " v$($info.PkgVersion)"
    Write-Host "║  " -NoNewline
    Write-Host "📁 项目" -ForegroundColor Yellow -NoNewline
    Write-Host " $($info.ProjectCount)  │  " -NoNewline
    Write-Host "🖥 驾驶舱" -ForegroundColor Yellow -NoNewline
    Write-Host " $($info.IndexSize.ToString('F0'))KB  │  " -NoNewline
    Write-Host "⚙ 旧代码" -ForegroundColor Yellow -NoNewline
    Write-Host " 已清空 ✓"
    Write-Host "╠══════════════════════════════════════════════════════════════╣" -ForegroundColor Cyan
    Write-Host "║  " -NoNewline; Write-Host "服务器状态:" -ForegroundColor White
    if ($info.ServerRunning) {
        Write-Host " ✅ 驾驶舱 (端口 $PORT) 运行中" -ForegroundColor Green
    } else {
        Write-Host " ❌ 驾驶舱 (端口 $PORT) 已停止" -ForegroundColor Red
    }
    if ($info.DashboardRunning) {
        Write-Host " ✅ Dashboard (端口 $DASH_PORT) 运行中" -ForegroundColor Green
    } else {
        Write-Host " ❌ Dashboard (端口 $DASH_PORT) 已停止" -ForegroundColor DarkGray
    }
    Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

function Show-MainMenu {
    do {
        $info = Get-SystemInfo
        Write-Header -Title "主控面板"
        
        Write-Host "  ┌─ " -NoNewline; Write-Host "快速启动" -ForegroundColor Yellow -NoNewline; Write-Host " ──────────────────────────────────────────┐"
        Write-Host "  │" -ForegroundColor DarkGray
        Write-Host "  │  " -NoNewline; Write-Host "[1]" -ForegroundColor Cyan -NoNewline; Write-Host " 🚀 启动驾驶舱" -ForegroundColor White -NoNewline; if ($info.ServerRunning) { Write-Host "   ← 正在运行" -ForegroundColor Green } else { Write-Host "  (端口 $PORT)" -ForegroundColor DarkGray }
        Write-Host "  │  " -NoNewline; Write-Host "[2]" -ForegroundColor Cyan -NoNewline; Write-Host " 📊 启动 Dashboard 控制面板" -ForegroundColor White -NoNewline; if ($info.DashboardRunning) { Write-Host "   ← 正在运行" -ForegroundColor Green } else { Write-Host "  (端口 $DASH_PORT)" -ForegroundColor DarkGray }
        Write-Host "  │  " -NoNewline; Write-Host "[3]" -ForegroundColor Cyan -NoNewline; Write-Host " 🌐 浏览器打开驾驶舱" -ForegroundColor White
        Write-Host "  │" -ForegroundColor DarkGray
        Write-Host "  └──────────────────────────────────────────────────────────┘" -ForegroundColor DarkGray
        Write-Host ""
        Write-Host "  ┌─ " -NoNewline; Write-Host "工具" -ForegroundColor Yellow -NoNewline; Write-Host " ──────────────────────────────────────────────┐"
        Write-Host "  │" -ForegroundColor DarkGray
        Write-Host "  │  " -NoNewline; Write-Host "[4]" -ForegroundColor Cyan -NoNewline; Write-Host " 🧪 运行质量测试 (QA)" -ForegroundColor White
        Write-Host "  │  " -NoNewline; Write-Host "[5]" -ForegroundColor Cyan -NoNewline; Write-Host " 🔧 安装依赖 (npm install)" -ForegroundColor White
        Write-Host "  │  " -NoNewline; Write-Host "[6]" -ForegroundColor Cyan -NoNewline; Write-Host " 📂 打开项目保存目录" -ForegroundColor White
        Write-Host "  │  " -NoNewline; Write-Host "[7]" -ForegroundColor Cyan -NoNewline; Write-Host " 📖 查看生产文档" -ForegroundColor White
        Write-Host "  │  " -NoNewline; Write-Host "[8]" -ForegroundColor Cyan -NoNewline; Write-Host " 🔍 系统信息" -ForegroundColor White
        Write-Host "  │" -ForegroundColor DarkGray
        Write-Host "  └──────────────────────────────────────────────────────────┘" -ForegroundColor DarkGray
        Write-Host ""
        Write-Host "  ┌─ " -NoNewline; Write-Host "管理" -ForegroundColor Yellow -NoNewline; Write-Host " ────────────────────────────────────────────┐"
        Write-Host "  │" -ForegroundColor DarkGray
        Write-Host "  │  " -NoNewline; Write-Host "[S]" -ForegroundColor Red -NoNewline; Write-Host " ⏹ 停止所有服务器" -ForegroundColor White
        Write-Host "  │  " -NoNewline; Write-Host "[D]" -ForegroundColor Red -NoNewline; Write-Host " ⚠ 重置项目数据库" -ForegroundColor White
        Write-Host "  │" -ForegroundColor DarkGray
        Write-Host "  └──────────────────────────────────────────────────────────┘" -ForegroundColor DarkGray
        Write-Host ""
        Write-Host "  [0] 退出" -ForegroundColor DarkGray
        Write-Host ""
        $choice = Read-Host "  ▸ 请输入选项"

        switch ($choice.ToUpper()) {
            "1" { Start-Cockpit; break }
            "2" { Start-Dashboard; break }
            "3" { Open-Browser "http://localhost:$PORT"; break }
            "4" { Start-QA; break }
            "5" { Run-NpmInstall; break }
            "6" { explorer $DATA_DIR; break }
            "7" { notepad "$WORKSPACE\Documentation.md"; break }
            "8" { Show-SystemInfo; break }
            "S" { Stop-AllServers; break }
            "D" { Reset-Database; break }
            "0" { Write-Host "`n新烬龙V2 已退出。烬火不灭。"; exit }
        }
    } while ($true)
}

function Start-Cockpit {
    Write-Header -Title "启动驾驶舱"
    Write-Host "  ▶ 启动生产服务器..." -ForegroundColor Green
    Write-Host "    地址: http://localhost:$PORT" -ForegroundColor Cyan
    Write-Host "    按 Ctrl+C 停止服务器" -ForegroundColor DarkGray
    Write-Host ""
    Start-Process "http://localhost:$PORT"
    Push-Location $WORKSPACE
    node server.js
    Pop-Location
    Write-Host "`n  按任意键返回主菜单..." -ForegroundColor DarkGray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

function Start-Dashboard {
    Write-Header -Title "启动 Dashboard"
    Write-Host "  ▶ 启动控制面板..." -ForegroundColor Green
    Write-Host "    地址: http://localhost:$DASH_PORT" -ForegroundColor Cyan
    Write-Host "    按 Ctrl+C 停止" -ForegroundColor DarkGray
    Write-Host ""
    Start-Process "http://localhost:$DASH_PORT"
    Push-Location $ROOT
    node dashboard.js
    Pop-Location
    Write-Host "`n  按任意键返回主菜单..." -ForegroundColor DarkGray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

function Start-QA {
    Write-Header -Title "质量测试"
    Write-Host "  ▶ 运行 QA 测试套件..." -ForegroundColor Green
    Write-Host ""
    Push-Location $WORKSPACE
    npm test
    Pop-Location
    Write-Host "`n  按任意键返回主菜单..." -ForegroundColor DarkGray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

function Run-NpmInstall {
    Write-Header -Title "安装依赖"
    Write-Host "  ▶ npm install..." -ForegroundColor Green
    Write-Host ""
    Push-Location $WORKSPACE
    npm install
    Pop-Location
    Write-Host "`n  按任意键返回主菜单..." -ForegroundColor DarkGray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

function Open-Browser {
    param([string]$Url)
    Start-Process $Url
}

function Stop-AllServers {
    Write-Header -Title "停止服务器"
    Write-Host "  ▶ 停止所有服务器进程..." -ForegroundColor Yellow
    
    # Kill node processes that are our servers
    Get-Process -Name "node" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -match "server.js|dashboard.js|cockpit"
    } | ForEach-Object {
        Write-Host "    停止: PID $($_.Id)" -ForegroundColor DarkGray
        $_.Kill()
    }
    Write-Host "  ✅ 已停止所有服务器" -ForegroundColor Green
    Write-Host "`n  按任意键返回..." -ForegroundColor DarkGray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

function Reset-Database {
    Write-Header -Title "重置数据库"
    Write-Host "  ⚠ 确认删除所有项目数据?" -ForegroundColor Yellow
    $confirm = Read-Host "  输入 YES 确认或回车取消"
    if ($confirm -eq "YES") {
        if (Test-Path $DATA_DIR) {
            Remove-Item "$DATA_DIR\*.json" -Force
            Write-Host "  ✅ 项目数据已清空" -ForegroundColor Green
        } else {
            Write-Host "  - 无数据需要清理" -ForegroundColor DarkGray
        }
    } else {
        Write-Host "  - 已取消" -ForegroundColor DarkGray
    }
    Write-Host "`n  按任意键返回..." -ForegroundColor DarkGray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

function Show-SystemInfo {
    $info = Get-SystemInfo
    Write-Header -Title "系统信息"
    Write-Host "  ┌─ 环境 ──────────────────────────────────────────────────┐" -ForegroundColor DarkGray
    Write-Host "  │  Node.js:    $($info.NodeVersion)" -ForegroundColor White
    Write-Host "  │  NPM:        $($info.NpmVersion)" -ForegroundColor White
    Write-Host "  │  操作系统:   $($info.OS)" -ForegroundColor White
    Write-Host "  │  项目版本:   v$($info.PkgVersion)" -ForegroundColor White
    Write-Host "  └─────────────────────────────────────────────────────────┘" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  ┌─ 文件 ──────────────────────────────────────────────────┐" -ForegroundColor DarkGray
    Write-Host "  │  驾驶舱界面:  $PUBLIC\index.html  ($($info.IndexSize.ToString('F0'))KB)" -ForegroundColor White
    Write-Host "  │  服务器:      $WORKSPACE\server.js  ($($info.ServerSize.ToString('F0'))KB)" -ForegroundColor White
    Write-Host "  │  项目数据:    $DATA_DIR  ($($info.ProjectCount) 个)" -ForegroundColor White
    Write-Host "  │  启动器:      $ROOT\launcher.ps1" -ForegroundColor White
    Write-Host "  └─────────────────────────────────────────────────────────┘" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  ┌─ 端口 ──────────────────────────────────────────────────┐" -ForegroundColor DarkGray
    if ($info.ServerRunning) {
        Write-Host "  │  ✅ 驾驶舱  http://localhost:$PORT  (运行中)" -ForegroundColor Green
    } else {
        Write-Host "  │  ❌ 驾驶舱  http://localhost:$PORT  (已停止)" -ForegroundColor Red
    }
    if ($info.DashboardRunning) {
        Write-Host "  │  ✅ Dashboard  http://localhost:$DASH_PORT  (运行中)" -ForegroundColor Green
    } else {
        Write-Host "  │  ❌ Dashboard  http://localhost:$DASH_PORT  (已停止)" -ForegroundColor DarkGray
    }
    Write-Host "  └─────────────────────────────────────────────────────────┘" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  [任意键] 返回主菜单" -ForegroundColor DarkGray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

# ══════════════════════ DIRECT MODE ══════════════════════
switch ($Mode.ToLower()) {
    "cockpit"  { Start-Cockpit; exit }
    "dashboard" { Start-Dashboard; exit }
    "info"     { Show-SystemInfo; Show-MainMenu }
    "help" {
        Write-Header -Title "帮助"
        Write-Host "  用法: .\launcher.ps1 [-Mode <cockpit|dashboard|info|help>]" -ForegroundColor White
        Write-Host ""
        Write-Host "  无参数    - 启动交互式主菜单"
        Write-Host "  cockpit   - 直接启动驾驶舱服务器"
        Write-Host "  dashboard - 直接启动 Dashboard"
        Write-Host "  info      - 显示系统信息"
        Write-Host "  help      - 显示此帮助"
        Write-Host ""
        exit
    }
    default { Show-MainMenu }
}

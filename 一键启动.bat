@echo off
rem DouYinSparkFlow 官方本地可视化应用启动器（ANSI/GBK + CRLF）
cd /d "%~dp0"
title DouYinSparkFlow 官方可视化应用

echo.
echo  DouYinSparkFlow v3.3
echo  官方可视化应用：app/web（Vite + Chromium WebView）
echo.

rem 1. 找 Python
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if not defined PY (
    py -3 -c "import sys; print(sys.executable)" > "%TEMP%\dsf-python-path.txt" 2>nul
    if exist "%TEMP%\dsf-python-path.txt" set /p PY=<"%TEMP%\dsf-python-path.txt"
)
if not defined PY (
    where python >nul 2>&1 && for /f "delims=" %%P in ('where python') do if not defined PY set "PY=%%P"
)
if not defined PY (
    echo [错误] 未找到 Python 3.10+，请先安装 Python：
    echo        https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [OK] Python: %PY%

rem 2. 首次自动创建虚拟环境
if not exist ".venv\Scripts\python.exe" (
    echo [准备] 创建虚拟环境 .venv ...
    "%PY%" -m venv .venv
    if errorlevel 1 (
        echo [错误] 虚拟环境创建失败
        pause
        exit /b 1
    )
    set "PY=%~dp0.venv\Scripts\python.exe"
)
set "PY=%~dp0.venv\Scripts\python.exe"
rem 3. 每次启动检查 Python 依赖
echo [检查] 安装/校验 Python 依赖 ...
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [错误] Python 依赖安装失败，请检查网络后重试
    pause
    exit /b 1
)

rem 4. 检查 Node/npm，并构建官方 Web UI
where node >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Node.js 20+，官方 UI 需要 npm 构建
    echo        https://nodejs.org/
    pause
    exit /b 1
)
where npm >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 npm，请重新安装 Node.js
    pause
    exit /b 1
)
pushd app\web\ui
if not exist "node_modules\vite\bin\vite.js" (
    echo [准备] 安装官方 Web UI 依赖 ...
    call npm ci
    if errorlevel 1 (
        popd
        echo [错误] npm 依赖安装失败
        pause
        exit /b 1
    )
)
echo [构建] 构建官方 Web UI ...
call npm run build
if errorlevel 1 (
    popd
    echo [错误] Web UI 构建失败
    pause
    exit /b 1
)
popd

rem 5. 检查官方桌面 WebView 所需的 CloakBrowser 浏览器
"%PY%" -c "from app import paths; import sys; sys.exit(0 if paths.browser_binary().is_file() else 1)"
if errorlevel 1 (
    echo [准备] 未找到 CloakBrowser，开始下载（约 562MB；自动使用系统代理）...
    "%PY%" -m cloakbrowser install
    if errorlevel 1 (
        echo [错误] CloakBrowser 下载失败，请检查网络或设置 HTTP_PROXY/HTTPS_PROXY 后重试
        pause
        exit /b 1
    )
)

rem 6. 启动官方桌面 Web 应用（不是旧 Flask web_app.py）
echo [启动] 正在打开官方可视化应用 ...
"%PY%" main.py app
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" echo [错误] 应用退出，错误码：%EXIT_CODE%
pause
exit /b %EXIT_CODE%

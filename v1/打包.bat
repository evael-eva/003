@echo off
chcp 65001 >nul 2>&1
title 盘口监控邮件提醒 - PyInstaller 打包工具
color 0A

echo ════════════════════════════════════════════════════════════
echo   盘口监控与邮件提醒系统 - 一键打包脚本
echo ════════════════════════════════════════════════════════════
echo.

:: 检查 Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 并添加到 PATH
    pause & exit /b 1
)

:: 显示 Python 版本
python --version

:: 检查 pyinstaller
python -c "import PyInstaller" >nul 2>&1
if %errorlevel% neq 0 (
    echo [提示] 正在安装 pyinstaller ...
    pip install pyinstaller
    if %errorlevel% neq 0 (
        echo [错误] pyinstaller 安装失败！请手动执行: pip install pyinstaller
        pause & exit /b 1
    )
)

echo.
echo [1/3] 清理旧的打包文件...
if exist "build" rmdir /s /q "build"
if exist "dist\盘口监控邮件提醒" rmdir /s /q "dist\盘口监控邮件提醒"

echo.
echo [2/3] 开始打包（可能需要1-3分钟，请耐心等待）...
echo.

pyinstaller --noconfirm --clean 盘口监控邮件提醒.spec

if %errorlevel% equ 0 (
    echo.
    echo ════════════════════════════════════════════════════════════
    echo   ✓ 打包成功！
    echo.
    echo   输出目录: dist\盘口监控邮件提醒\
    echo   可执行文件: dist\盘口监控邮件提醒\盘口监控邮件提醒.exe
    echo.
    echo   分发时需将整个 文件夹 一起发送给别人：
    echo     ┌─ 盘口监控邮件提醒\
    echo     │  ├─ 盘口监控邮件提醒.exe    ← 双击运行这个
    echo     │  ├─ email_config.json        ← 邮件配置文件
    echo     │  └─ ... (其他依赖文件)
    echo ════════════════════════════════════════════════════════════
    
    :: 打开输出文件夹
    explorer "%~dp0dist\盘口监控邮件提醒"
) else (
    echo.
    echo ✗ 打包失败！请检查上方错误信息。
)

echo.
pause

@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==========================================
echo   CBL 互动教程（8 课自学网站）
echo   浏览器会自动打开教程首页
echo   如果没有打开：把 docs\tutorial\index.html 拖进浏览器窗口
echo ==========================================
start "" "docs\tutorial\index.html"
exit /b

@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==========================================
echo   CBL 预算实验台（浏览器会自动打开）
echo   关闭：直接关掉本窗口，或按 Ctrl+C
echo ==========================================
python -m cbl serve
pause

@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo CBL 预算实验台 - 局域网模式
echo 手机连同一 Wi-Fi，打开下面显示的地址；Windows 防火墙弹窗请选"允许"
echo.
python -m cbl serve --lan
pause

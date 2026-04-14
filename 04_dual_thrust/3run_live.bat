@echo off
chcp 65001 >nul
echo ============================================
echo Dual Thrust 策略 - 实盘交易
echo ============================================
python "%~dp0live.py"
pause

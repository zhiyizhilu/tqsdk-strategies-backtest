@echo off
chcp 65001 >nul
echo ============================================
echo Dual Thrust 策略 - 单品种回测
echo ============================================
python "%~dp0tqsim.py"
pause

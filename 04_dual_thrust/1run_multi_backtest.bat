@echo off
chcp 65001 >nul
echo ============================================
echo Dual Thrust 策略 - 多品种回测
echo ============================================
python "%~dp0tqsim_multi_symbol.py" --all
pause

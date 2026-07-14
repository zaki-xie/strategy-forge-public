@chcp 65001 >nul
@echo off

set PRIVATE_DIR=%cd%
set PUBLIC_DIR=%cd%\..\strategy-forge-public

echo 正在从 %PRIVATE_DIR% 复制到 %PUBLIC_DIR% ...
robocopy "%PRIVATE_DIR%" "%PUBLIC_DIR%" /E /XD .git /NFL /NDL

echo 复制完成。
pause
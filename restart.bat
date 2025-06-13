chcp 65001

@echo off
setlocal ENABLEDELAYEDEXPANSION

echo.
echo [ Docker Compose Restart 工具 ]
echo ---------------------------------
echo 1. 正常重啟 (僅重建 py 程式)
echo 2. 資料庫重啟 (刪除 volume)
echo 3. 更動底層代碼 (Dockerfile/套件更新)
echo 4. 完全重啟 (image + volume 全刪)
echo ---------------------------------
set /p mode="請輸入選項 (1-4)："

echo.
set /p bg="是否要在背景模式執行 (y/n)："

set bg_flag=
if /I "%bg%"=="y" (
    set bg_flag=-d
)

if "%mode%"=="1" (
    echo [ 正常重啟中... ]
    docker compose up --build %bg_flag%
)

if "%mode%"=="2" (
    echo [ 資料庫重啟中... ]
    docker compose down -v
    docker compose up --build %bg_flag%
)

if "%mode%"=="3" (
    echo [ 重建底層 image... ]
    docker compose down --rmi all
    docker compose build --no-cache
    docker compose up %bg_flag%
)

if "%mode%"=="4" (
    echo [ 完全重啟中... ]
    docker compose down --rmi all -v --remove-orphans
    docker compose build --no-cache
    docker compose up %bg_flag%
)

echo.
echo 完成。
pause

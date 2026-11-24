chcp 65001

@echo off
setlocal

echo 🛠️ Docker Compose 啟動工具
echo ===========================
echo 請確保已安裝 Docker 和 Docker Compose
echo 0. 檢查docker-compose裡 volumes 的部分是否完成修改

set /p check="(y/n)："
if /I "%check%"=="y" (
    echo [確認] 已完成修改 docker-compose.yaml 中的 volumes 部分
) else (
    echo [警告] 請先修改 docker-compose.yaml 中的 volumes 部分
    pause
    exit /b 1
)

echo 1. 檢查 docker 是否已安裝
docker --version >nul 2>&1
if errorlevel 1 (
    echo [錯誤] Docker 未安裝
    pause
    exit /b 1
)
echo 2. 檢查 docker compose 是否已安裝
docker compose version >nul 2>&1
if errorlevel 1 (
    echo [錯誤] Docker Compose 未安裝
    pause
    exit /b 1
)
echo 3. 檢查 docker 是否正在運行
docker info >nul 2>&1
if errorlevel 1 (
    echo [錯誤] Docker 未啟動
    pause
    exit /b 1
) 

echo 4. 檢查 cert 目錄下的 cookie.txt 和 .crt 檔案
set CERT_DIR=adminapp\backend\certs
if not exist "%CERT_DIR%\cookie.txt" (
    echo [錯誤] 找不到 %CERT_DIR%\cookie.txt
    pause
    exit /b 1
)
if not exist "%CERT_DIR%\se.acsicook.info.crt" (
    echo [錯誤] 找不到 %CERT_DIR%\se.acsicook.info.crt
    pause
    exit /b 1
)


echo 5. 檢查.env 檔案是否存在
if not exist ".env" (
    echo [錯誤] 找不到 .env 檔案
    pause
    exit /b 1
)

echo 6. 檢查 adminapp npm 是否 install
cd adminapp\frontend
if not exist node_modules (
    echo [前端] 執行 npm install...
    call npm install
)
echo 7. adminapp 前端 build
echo [前端] 執行 npm run build...
call npm run build
cd ..\..

@REM echo 8. database 資料夾建立
@REM if not exist "database\db" (
@REM     echo [資料庫] 建立資料夾...
@REM     mkdir data\db
@REM )

echo 8. 啟動 docker-compose.yaml
docker compose up -d
if errorlevel 1 (
    echo [錯誤] 啟動 docker-compose.yaml 失敗
    pause
    exit /b 1
)
echo 啟動完成！
pause
#!/bin/bash

set -e

echo "echo 執行前確認是否給予執行權限 (chmod +x restart.sh)"
echo "------------------------------"
echo "🛠️ Docker Compose 啟動工具"

echo 0. 檢查docker-compose裡， volumes 的路徑是否正確
read -p "(y/n): " check
if [[ "$check" == "y" || "$check" == "Y" ]]; then
    echo "[確認] 已完成修改 docker-compose.yaml 中的 volumes 部分"
else
    echo "[警告] 請先修改 docker-compose.yaml 中的 volumes 部分"
    exit 1
fi

echo "1. 檢查 docker 是否已安裝"
if ! command -v docker &> /dev/null; then
    echo "[錯誤] Docker 未安裝"
    exit 1
fi

echo "2. 檢查 docker compose 是否已安裝"
if ! docker compose version &> /dev/null; then
    echo "[錯誤] Docker Compose 未安裝"
    exit 1
fi

echo "3. 檢查 docker 是否正在運行"
if ! docker info &> /dev/null; then
    echo "[錯誤] Docker 未啟動"
    exit 1
fi

echo "4. 檢查 cert 目錄下的 cookie.txt 和 .crt 檔案"
CERT_DIR="adminapp/app/certs"
if [ ! -f "$CERT_DIR/cookie.txt" ]; then
    echo "[錯誤] 找不到 $CERT_DIR/cookie.txt"
    exit 1
fi
if [ ! -f "$CERT_DIR/se.acsicook.info.crt" ]; then
    echo "[錯誤] 找不到 $CERT_DIR/se.acsicook.info.crt"
    exit 1
fi

echo "5. 檢查 .env 檔案是否存在"
if [ ! -f ".env" ]; then
    echo "[錯誤] 找不到 .env 檔案"
    exit 1
fi

echo "6. 檢查 adminapp npm 是否 install"
cd adminapp/frontend
if [ ! -d "node_modules" ]; then
    echo "[前端] 執行 npm install..."
    npm install
fi

echo "7. adminapp 前端 build"
echo "[前端] 執行 npm run build..."
npm run build
cd ../../

echo "8. database 資料夾建立"
if [ ! -d "data/db" ]; then
    echo "[資料庫] 建立資料夾..."
    mkdir -p data/db
fi

echo "9. 啟動 docker-compose.yaml"
if ! docker compose up -d; then
    echo "[錯誤] 啟動 docker-compose.yaml 失敗"
    exit 1
fi

echo "啟動完成！"
pause
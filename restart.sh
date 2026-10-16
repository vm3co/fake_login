#!/bin/bash

echo ""
echo "🛠️ Docker Compose Restart 工具"
echo "執行前確認是否給予執行權限 (chmod +x restart.sh)"
echo "------------------------------"
echo "1. 正常重啟 (py 檔程式更新)"
echo "2. 資料庫重啟 (刪除 volume)"
echo "3. 更動底層代碼 (Dockerfile/套件更新)"
echo "4. 完全重啟 (image + volume 全清)"
echo "------------------------------"
read -p "請輸入選項 (1-4): " mode

echo ""
read -p "是否需要重建 frontend (y/n): " rebuild_fe

echo ""
read -p "是否要背景執行 (y/n): " bg

if [[ "$rebuild_fe" == "y" || "$rebuild_fe" == "Y" ]]; then
  echo "[ 開始重建 frontend... ]"
  pushd ./adminapp/frontend
  npm run build
  popd
  echo "[ frontend 重建完成 ]"
fi

bg_flag=""
if [[ "$bg" == "y" || "$bg" == "Y" ]]; then
  bg_flag="-d"
fi

case "$mode" in
  1)
    echo "🔁 [正常重啟中...]"
    docker compose up --build $bg_flag
    ;;
  2)
    echo "🧼 [資料庫重啟中...]"
    docker compose down -v
    docker compose up --build $bg_flag
    ;;
  3)
    echo "🔨 [重建底層 image 中...]"
    docker compose down --rmi all
    docker compose build --no-cache
    docker compose up $bg_flag
    ;;
  4)
    echo "🔥 [完全重啟中...]"
    docker compose down --rmi all -v --remove-orphans
    docker compose build --no-cache
    docker compose up $bg_flag
    ;;
  *)
    echo "❌ 無效的選項，請輸入 1-4。"
    ;;
esac

echo ""
echo "✅ 執行完畢"

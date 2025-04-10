# 啟動說明

docker-compose up --build

# 初始網址

- login: http://localhost:8080/
- admin: http://localhost:8081/

# 用途

- login:
  - 進到/login時紀錄一次ip
  - 輸入資料後點擊登入後，紀錄一次ip及資料(目前只有email)

- admin:
  - 顯示紀錄資料列表(資料格式為csv檔)
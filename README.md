# 啟動說明

docker-compose up --build

# 初始網址

- login: http://localhost:8090/
- admin: http://localhost:8091/

# 用途

- login:
  - 進到/login時紀錄一次ip
  - 輸入資料後點擊登入後，紀錄一次ip及資料(目前只有email)

- admin:
  - 顯示紀錄資料列表(資料格式為csv檔)


# 製作login網頁
- clone好一個網頁後設定：
  1. 設置form id="recordingLogin"
  2. 確認input的id="recordingLoginIdentifierId"
  3. 設置js <script src="/static/js/recordingLogin.js"></script>
  4. 拔掉base

# 插入qrcode (20250509更新(branch：create_qrcode))
- 信件中設定：
  1. 插入/編輯 圖片
  2. 設定： 
       - 圖片網址： http://localhost:8090/qrcode/uuid?uuid=99999_99999
       - 替代說明： qrcode
       - 寬度&高度：300(把右邊的鎖頭點開)
       - 送出並儲存
- 寄送後會自動生成qrcode，該qrocde會自動生成，網址為"https://se2.link.cc/a/l/{link_uuid}?reurlreurl=http://localhost:8090/login/{link_uuid}"，
- {link_uuid}的部分為jess系統自動帶入的link_uuid值
  - task_uuid = link_uuid[16:48]
  - email_uuid = link_uuid[48:] + link_uuid[0:16]
- 記錄流程：
  1. 開啟信件：jess系統記錄開啟
  2. 掃描qrcode：jess系統記錄點擊連結，接著導向到login頁面
  3. 導向到login頁面：adminapp記錄visit(記錄網址、ip)
  4. 登入：adminapp記錄login(記錄網址、ip、輸入內容)

# 新增db以及後台紀錄頁面(react)(20250521更新)
- bug：googledrive網頁無法記錄登入login
